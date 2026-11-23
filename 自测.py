# -*- coding: utf-8 -*-
"""工具包自测：在临时目录（故意带中文和空格）里跑一遍 初始化 → 同步 → 自检。

验收六件事：
  1. 初始化能把模板与技能落盘
  2. 同步.py 退出码 0，末行是「✅ 同步完成，一切一致」
  3. 两个产物（任务看板.html / AI交接.md）都生成
  4. 模板里没有未替换的占位符残留
  5. 模板/技能/README 里**没有**任何绝对盘符、也没有项目专有词
  6. 收尾清理临时目录

用法：python 自测.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
TEXT_SUFFIXES = {".py", ".md", ".json", ".txt", ".yml", ".yaml"}

# 专有词黑名单放在**本地文件**里（不入库），避免把内部名称写进公开仓库。
# 文件：本机校验词表.local.txt（一行一个词，# 开头是注释）。没有该文件就跳过这项扫描。
def load_local_words() -> list:
    p = HERE / "本机校验词表.local.txt"
    if not p.exists():
        return []
    words = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            words.append(s)
    return words


FORBIDDEN_WORDS = load_local_words()
DRIVE_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")

results = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(("✓ " if ok else "✗ ") + name + (f"　{detail}" if detail and not ok else ""))
    return ok


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def main() -> int:
    ok = True

    # ---------- 1 静态扫描 ----------
    print("=== 1. 静态扫描（专有词 / 盘符）===")
    # 专有词：连文档一起扫（防止把内部项目信息带进公开仓库）
    # 注意：本文件（自测.py）自己就含有 FORBIDDEN_WORDS 清单，必须排除，否则永远扫自己
    word_targets = [HERE / "README.md", HERE / "AGENTS.md", HERE / "初始化.py"]
    word_targets += sorted((HERE / "docs").glob("*.md"))
    word_targets += sorted((HERE / "模板").rglob("*")) + sorted((HERE / "技能模板").rglob("*"))
    for f in word_targets:
        if not f.is_file() or f.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = f.read_text(encoding="utf-8")
        rel = f.relative_to(HERE)
        for w in FORBIDDEN_WORDS:
            if w in text:
                ok = check(f"{rel} 不含「{w}」", False, f"出现在 {rel}") and ok

    # 盘符：只扫"会被执行/复制"的代码与模板（文档里的示例路径是给人看的，不算）
    code_targets = [HERE / "初始化.py", HERE / "自测.py"]
    code_targets += [f for f in (HERE / "模板").rglob("*") if f.is_file()]
    code_targets += [f for f in (HERE / "技能模板").rglob("*") if f.is_file()]
    for f in code_targets:
        if not f.is_file() or f.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = f.read_text(encoding="utf-8")
        rel = f.relative_to(HERE)
        for m in DRIVE_RE.finditer(text):
            snippet = text[max(0, m.start() - 20):m.start() + 30].replace("\n", " ")
            ok = check(f"{rel} 无绝对盘符", False, f"「{m.group()}」… {snippet}") and ok
    check("扫描完成：专有词 0 处、代码里盘符 0 处", all(r[1] for r in results))

    # ---------- 2 真实跑一遍 ----------
    print("\n=== 2. 临时目录全链路（中文 + 空格路径）===")
    tmp_root = Path(tempfile.gettempdir()) / "看板包自测 2026"
    proj = tmp_root / "示例项目 带空格"
    if tmp_root.exists():
        shutil.rmtree(tmp_root, ignore_errors=True)
    proj.mkdir(parents=True, exist_ok=True)
    check("临时目录已建", proj.is_dir(), str(proj))

    r = run([sys.executable, "-X", "utf8", str(HERE / "初始化.py"),
             "--目标目录", str(proj), "--python", sys.executable])
    ok = check("初始化.py 退出码 0", r.returncode == 0,
               (r.stdout or r.stderr)[-600:]) and ok
    board = proj / "docs" / "看板"
    ok = check("看板目录已生成", (board / "看板数据.json").is_file(), str(board)) and ok
    ok = check("技能已安装", (proj / ".dsh" / "skills" / "progress-sync" / "SKILL.md").is_file()) and ok

    r = run([sys.executable, "-X", "utf8", str(board / "同步.py")])
    out = (r.stdout or "") + (r.stderr or "")
    ok = check("同步.py 退出码 0", r.returncode == 0, out[-800:]) and ok
    ok = check("末行是「✅ 同步完成，一切一致」",
               "✅ 同步完成，一切一致" in out, out[-300:]) and ok
    ok = check("生成 任务看板.html", (board / "任务看板.html").is_file()) and ok
    ok = check("生成 AI交接.md", (board / "AI交接.md").is_file()) and ok

    # ---------- 3 数据体检与快照一致 ----------
    r = run([sys.executable, "-X", "utf8", str(board / "同步.py"), "--lint"])
    ok = check("--lint 通过", r.returncode == 0, ((r.stdout or "") + (r.stderr or ""))[-600:]) and ok

    # 快照数字与数据源一致
    data = json.loads((board / "看板数据.json").read_text(encoding="utf-8"))
    ai = (board / "AI交接.md").read_text(encoding="utf-8")
    m = re.search(r"当前快照：\*\*(\d+) 条流程 / (\d+) 个子项 / 整体完整度 (\d+)%\*\*", ai)
    same = bool(m) and int(m.group(1)) == len(data["流程"])
    ok = check("AI交接.md 快照与数据一致", same, m.group(0) if m else "找不到快照行") and ok

    # ---------- 4 落盘后不允许残留占位符 ----------
    print("\n=== 3. 落盘后的产物检查 ===")
    leftover = [str(f.relative_to(board)) for f in board.rglob("*")
                if f.is_file() and f.suffix.lower() in TEXT_SUFFIXES
                and "${" in f.read_text(encoding="utf-8")]
    ok = check("无未替换占位符", not leftover, "; ".join(leftover[:5])) and ok

    agents_section = [s for s in re.findall(r"^## \d+\. .+$", ai, re.M)]
    ok = check("AI交接.md 有 10 节", len(agents_section) >= 10, f"只有 {len(agents_section)} 节") and ok

    # ---------- 5 清理 ----------
    print("\n=== 4. 清理 ===")
    shutil.rmtree(tmp_root, ignore_errors=True)
    ok = check("临时目录已清理", not tmp_root.exists()) and ok

    # ---------- 汇总 ----------
    bad = [r for r in results if not r[1]]
    print("\n" + "=" * 56)
    print(f"共 {len(results)} 项检查，失败 {len(bad)} 项")
    print("结论：" + ("✅ 自测通过，工具包可用" if not bad else "❌ 自测失败"))
    print("=" * 56)
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
