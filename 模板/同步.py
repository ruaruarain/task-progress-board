# -*- coding: utf-8 -*-
"""同步进度：一条命令完成「数据体检 → 生成两个产物 → 自检」。

这是「进度同步标准」的执行器。规范说明见 .dsh/skills/progress-sync/SKILL.md。

用法：
    python 同步.py            完整流程：lint → 生成 → 自检
    python 同步.py --check    只校验，不生成（收工前/提交前）
    python 同步.py --lint     只做数据质量体检
    python 同步.py --quick    生成 + 自检，跳过体检

退出码：0 = 全部通过；1 = 有问题必须修。
"""
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA_FILE = HERE / "看板数据.json"
GEN_FILE = HERE / "生成看板.py"
CHECK_FILE = HERE / "_自检.py"
HTML_FILE = HERE / "任务看板.html"
AI_FILE = HERE / "AI交接.md"

VALID_STATUS = {"可用", "部分可用", "待修", "阻塞", "未开始"}
VALID_SIZE = {"大", "中", "小"}
REQUIRED_FLOW = ["id", "名称", "一句话", "状态", "部分", "更新"]
REQUIRED_PART = ["名称", "完整度", "说明"]

problems, warnings = [], []


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def lint(data: dict) -> None:
    flows = data.get("流程", [])
    if not flows:
        problems.append("「流程」为空")

    seen_flow_names, seen_part_names = set(), {}
    for fi, f in enumerate(flows, 1):
        tag = f"流程{fi}({f.get('名称', '?')[:18]})"
        for k in REQUIRED_FLOW:
            if k not in f:
                problems.append(f"{tag} 缺字段 `{k}`")
        if f.get("状态") not in VALID_STATUS:
            problems.append(f"{tag} 状态 `{f.get('状态')}` 非法（只能是 {'/'.join(sorted(VALID_STATUS))}）")
        if f.get("名称") in seen_flow_names:
            problems.append(f"{tag} 名称重复")
        seen_flow_names.add(f.get("名称"))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(f.get("更新", ""))):
            warnings.append(f"{tag} 更新日期不是 YYYY-MM-DD：{f.get('更新')}")

        parts = f.get("部分", [])
        if not parts:
            problems.append(f"{tag} 没有子项")
        for pi, p in enumerate(parts, 1):
            ptag = f"{tag} 子项{pi}({p.get('名称', '?')[:20]})"
            for k in REQUIRED_PART:
                if k not in p:
                    problems.append(f"{ptag} 缺字段 `{k}`")
            v = p.get("完整度")
            if not isinstance(v, int) or not (0 <= v <= 100):
                problems.append(f"{ptag} 完整度必须是 0~100 的整数，当前 {v!r}")
            w = p.get("权重", 1)
            if not isinstance(w, int) or not (1 <= w <= 5):
                problems.append(f"{ptag} 权重必须是 1~5 的整数，当前 {w!r}")
            if p.get("体量", "小") not in VALID_SIZE:
                problems.append(f"{ptag} 体量只能是 大/中/小，当前 {p.get('体量')!r}")
            if not str(p.get("阶段", "")).strip():
                problems.append(f"{ptag} 缺 `阶段`（流程图靠它分列，补上该字段）")
            if len(str(p.get("说明", "")).strip()) < 8:
                warnings.append(f"{ptag} 说明过短（少于 8 字），别人/AI 看不懂")

            # 卡点与完成度矛盾
            kt = str(p.get("卡点", "")).strip()
            desc = str(p.get("说明", ""))
            if v >= 100 and kt:
                problems.append(f"{ptag} 完整度 100% 但仍写着卡点：{kt}（要么清掉卡点，要么降完成度）")
            # 未完成的子项，必须能看出「还差什么」：显式卡点字段，或说明里写清还差什么
            says_remaining = any(k in desc for k in ("还差", "未实现", "未验证", "待", "依赖", "缺"))
            if 0 < v < 100 and not kt and not says_remaining:
                problems.append(f"{ptag} 完成度 {v}% 却没写「还差什么」（加 `卡点` 字段，或在说明里写「还差：…」）")

            # 约定：探索类子项永不标 100%（负责人 2026-11-20 决定）
            # 用显式字段 `永不完成: true` 标注，比按名称前缀匹配更稳（改名不会失效）
            never = p.get("永不完成", False)
            if not isinstance(never, bool):
                problems.append(f"{ptag} `永不完成` 必须是 true/false，当前 {never!r}")
            elif never and v >= 100:
                problems.append(f"{ptag} 是探索类子项（永不完成），按约定不得标 100%（当前 {v}%）；"
                                f"做到 90% 即可，剩余用于持续扩展")

            # 约定：`作废: true` = 只留在看板上供追溯，不进待办队列（负责人 2026-11-22 决定）
            # 必须写清为什么作废，否则后来人只会看到一个不动的 0% 却不知道为什么
            voided = p.get("作废", False)
            if not isinstance(voided, bool):
                problems.append(f"{ptag} `作废` 必须是 true/false，当前 {voided!r}")
            elif voided:
                if not str(p.get("作废说明", "")).strip():
                    problems.append(f"{ptag} 标了 `作废: true` 却没写 `作废说明`（要写清被谁接管、为什么留着）")
                if p.get("文件"):
                    warnings.append(f"{ptag} 已作废但仍挂着文件：{p.get('文件')}（确定还需要吗？）")

            # 路径规范 + 存在性
            for key in ("文件", "文档"):
                for path in p.get(key, []):
                    if "\\" in path:
                        problems.append(f"{ptag} {key} 路径用了反斜杠：{path}（规范要求用 /）")
                    if path.startswith(("/", "D:", "C:")):
                        problems.append(f"{ptag} {key} 必须是相对项目根的路径：{path}")
                    target = ROOT / path
                    if not target.exists():
                        problems.append(f"{ptag} {key} 指向的文件不存在：{path}")

            # 子项重名（同一流程内）
            if p.get("名称") in seen_part_names.setdefault(f.get("id"), set()):
                problems.append(f"{ptag} 同流程内子项名重复")
            seen_part_names[f.get("id")].add(p.get("名称"))

        stages = [str(x.get("阶段", "")).strip() for x in parts]
        if len(set(stages)) < 2:
            warnings.append(f"{tag} 只有 {len(set(stages))} 个阶段，流程图会退化成一条线")

    ai = data.get("AI接手")
    if not ai:
        problems.append("缺「AI接手」区块（补一个，或从模板示例里拷）")
    else:
        for k in ("读序", "环境", "常用命令", "禁止事项", "既定结论", "同步协议"):
            if not ai.get(k):
                problems.append(f"「AI接手」缺 `{k}`")
    for cmd in (ai or {}).get("常用命令", []):
        if not cmd.get("期望"):
            warnings.append(f"AI接手 命令「{cmd.get('用途')}」没写期望输出")


def report_lint(data: dict) -> None:
    n_flows = len(data.get("流程", []))
    n_parts = sum(len(f.get("部分", [])) for f in data.get("流程", []))
    print(f"数据体检：{n_flows} 条流程 / {n_parts} 个子项")
    for w in warnings:
        print(f"  ⚠ 警告 {w}")
    for p in problems:
        print(f"  ✗ 错误 {p}")
    if not problems and not warnings:
        print("  ✓ 全部通过（无错误、无警告）")
    elif not problems:
        print(f"  ✓ 无错误（{len(warnings)} 条警告，建议修）")
    else:
        print(f"  ✗ {len(problems)} 个错误、{len(warnings)} 个警告")


def generate() -> None:
    mod = load_module(GEN_FILE, "gen_board")
    # 生成看板.py 的 main(argv) 约定：argv[1]=数据源, argv[2]=HTML 输出；
    # AI交接.md 由它一并写到 HTML 同目录。
    mod.main([str(GEN_FILE), str(DATA_FILE), str(HTML_FILE)])


def run_check() -> bool:
    print("\n— 运行 _自检.py —")
    r = subprocess.run([sys.executable, "-X", "utf8", str(CHECK_FILE)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    tail = [ln for ln in out.splitlines() if ln.strip()]
    print("\n".join(tail[-8:]))
    return r.returncode == 0


def main(argv) -> int:
    mode = "full"
    if "--check" in argv:
        mode = "check"
    elif "--lint" in argv:
        mode = "lint"
    elif "--quick" in argv:
        mode = "quick"

    if not DATA_FILE.exists():
        print(f"✗ 找不到数据源：{DATA_FILE}")
        return 1
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"✗ JSON 解析失败：{e}")
        return 1

    ok = True
    if mode in ("full", "lint", "check"):
        lint(data)
        report_lint(data)
        if problems:
            ok = False

    if mode in ("full", "quick"):
        print("\n— 生成产物 —")
        generate()
    elif mode in ("check", "lint") and ok:
        # 只校验时也要确认产物不落后于数据源
        if not HTML_FILE.exists() or not AI_FILE.exists():
            print("✗ 产物缺失，需要跑一次完整同步")
            ok = False
        elif AI_FILE.stat().st_mtime < DATA_FILE.stat().st_mtime:
            print("⚠ 数据源比 AI交接.md 新 → 产物已过期，需要跑一次完整同步")
            ok = False

    if mode in ("full", "quick"):
        ok = run_check() and ok
    elif mode == "check":
        ok = run_check() and ok

    print("\n" + "=" * 56)
    print("结论：" + ("✅ 同步完成，一切一致" if ok else "❌ 还有问题，按上面的提示修完再跑"))
    print("=" * 56)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
