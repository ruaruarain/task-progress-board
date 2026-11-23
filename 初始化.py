# -*- coding: utf-8 -*-
"""把「任务进度看板工具包」安装到任意项目的指定目录。

做四件事：
  1. 把 模板/ 复制到 <目标>/<看板子目录>/
  2. 替换占位符：${看板目录} → 看板子目录的相对路径；${PY} → 你给的解释器
  3. 按看板目录深度回推并写入 "项目根"（决定 文件/文档 链接相对谁）
  4. 把 技能模板/ 装进 <目标>/.dsh/skills/（DSH 会自动加载；其他 agent 直接读 SKILL.md）

用法：
  python 初始化.py --目标目录 <你的项目>
  python 初始化.py --目标目录 <你的项目> --看板子目录 docs/看板 --python "<解释器路径>"

安全：目标位置已有 看板数据.json 时默认拒绝覆盖（避免冲掉别人已填的进度），除非加 --强制。
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
TEMPLATE_DIR = HERE / "模板"
SKILLS_DIR = HERE / "技能模板"
DEFAULT_BOARD_SUBDIR = "docs/看板"
TEXT_SUFFIXES = {".py", ".md", ".json", ".txt", ".yml", ".yaml"}


def copy_tree(src: Path, dst: Path) -> int:
    n = 0
    for item in sorted(src.rglob("*")):
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            n += 1
    return n


def fill(text: str, board_rel: str, py: str) -> str:
    return text.replace("${看板目录}", board_rel).replace("${PY}", py)


def substitute_tree(base: Path, board_rel: str, py: str) -> list:
    """替换占位符。

    `.json` 必须走 json 模块：直接把 Windows 路径（含反斜杠）塞进 JSON 文本会让 `\P` 变成非法转义。
    """
    changed = []
    for f in sorted(base.rglob("*")):
        if not f.is_file():
            continue
        suf = f.suffix.lower()
        raw = f.read_text(encoding="utf-8")

        if suf == ".json":
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            new = json.dumps(_fill_json(obj, board_rel, py), ensure_ascii=False, indent=2) + "\n"
            if new != raw:
                f.write_text(new, encoding="utf-8")
                changed.append(str(f.relative_to(base)))
        elif suf in TEXT_SUFFIXES:
            new = fill(raw, board_rel, py)
            if new != raw:
                f.write_text(new, encoding="utf-8")
                changed.append(str(f.relative_to(base)))
    return changed


def _fill_json(obj, board_rel: str, py: str):
    if isinstance(obj, dict):
        return {k: _fill_json(v, board_rel, py) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fill_json(v, board_rel, py) for v in obj]
    if isinstance(obj, str):
        return fill(obj, board_rel, py)
    return obj


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="把任务进度看板安装到目标项目")
    ap.add_argument("--目标目录", required=True, help="项目根目录（必须已存在）")
    ap.add_argument("--看板子目录", default=DEFAULT_BOARD_SUBDIR,
                    help=f"看板放在项目里的哪个子目录，默认 {DEFAULT_BOARD_SUBDIR}")
    ap.add_argument("--python", default="python", help="写进文档里的解释器（默认 python）")
    ap.add_argument("--强制", action="store_true", help="目标已有看板数据时也覆盖")
    args = ap.parse_args(argv)

    target = Path(args.目标目录).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    target = target.resolve()
    if not target.is_dir():
        print(f"✗ 目标目录不存在：{target}")
        print("  请先创建它，再运行本脚本（本脚本不替你新建项目目录）")
        return 1

    board_sub = args.看板子目录.replace("\\", "/").strip("/")
    if not board_sub:
        print("✗ --看板子目录 不能为空")
        return 1
    board = target / board_sub
    data_file = board / "看板数据.json"

    if data_file.exists() and not args.强制:
        print(f"✗ 目标位置已经有看板数据：{data_file}")
        print("  为免覆盖你已经填的进度，本次不做任何改动。确实要覆盖请加 --强制")
        return 2

    # 1+2 复制模板并替换占位符
    board.mkdir(parents=True, exist_ok=True)
    n_files = copy_tree(TEMPLATE_DIR, board)
    changed = substitute_tree(board, board_sub, args.python)

    # 3 项目根：从看板目录回推到目标目录
    depth = len([p for p in board_sub.split("/") if p])
    root_rel = "/".join([".."] * depth) or "."
    data = json.loads(data_file.read_text(encoding="utf-8"))
    data["项目根"] = root_rel
    data["更新日期"] = data.get("更新日期", "")
    data_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 4 技能
    skills_dst = target / ".dsh" / "skills"
    installed = []
    for skill in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()):
        dst = skills_dst / skill.name
        dst.mkdir(parents=True, exist_ok=True)
        for f in skill.rglob("*"):
            if f.is_file():
                rel = f.relative_to(skill)
                out = dst / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(fill(f.read_text(encoding="utf-8"), board_sub, args.python),
                               encoding="utf-8")
        installed.append(skill.name)

    # 残留占位符检查
    leftover = [str(f.relative_to(board)) for f in board.rglob("*")
                if f.is_file() and f.suffix.lower() in TEXT_SUFFIXES
                and "${" in f.read_text(encoding="utf-8")]
    if leftover:
        print("✗ 还有未替换的占位符：")
        for x in leftover:
            print("   ", x)
        return 3

    py = args.python
    print("✅ 安装完成")
    print(f"   看板目录：{board}（{n_files} 个文件，替换占位符 {len(changed)} 个文件）")
    print(f"   项目根  ：{target}（看板数据里的 \"项目根\" = {root_rel}）")
    print(f"   技能    ：{skills_dst}（{'、'.join(installed)}）")
    print()
    print("下一步三件事：")
    print(f"  1) 打开并替换 {board_sub}/看板数据.json 里的示例流程（字段规范见 看板使用说明.md）")
    print(f"  2) 生成：\"{py}\" -X utf8 \"{board_sub}/同步.py\"")
    print(f"  3) 双击 {board_sub}/任务看板.html 看效果")
    print()
    print("提示：技能只在 DSH 里会自动加载；用 Codex / Claude Code / Cursor 的话，")
    print(f"      让 agent 直接读 {skills_dst} 下的 SKILL.md 即可（同一套标准）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
