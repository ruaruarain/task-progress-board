# -*- coding: utf-8 -*-
"""看板自检：内嵌 JSON / DOM / HTML 结构 / JS 语法（配合 node --check）+ 打印各流程加权完成度。"""
import json
import re
import sys
from pathlib import Path
from html.parser import HTMLParser

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
HTML_FILE = HERE / "任务看板.html"
DATA_FILE = HERE / "看板数据.json"
JS_OUT = HERE / "_check.js"

# ---------- 1. 数据源 ----------
d = json.loads(DATA_FILE.read_text(encoding="utf-8"))
parts_all = [p for f in d["流程"] for p in f.get("部分", [])]
print(f"数据源：{len(d['流程'])} 条流程 / {len(parts_all)} 个子项")
print(f"{'流程':28s} {'子项':>4s} {'已完成':>5s} {'加权%':>6s}  状态")
for f in d["流程"]:
    ps = f["部分"]
    w = sum(p.get("权重", 1) for p in ps)
    v = round(sum(p.get("权重", 1) * p["完整度"] for p in ps) / w) if w else 0
    done = sum(1 for p in ps if p["完整度"] >= 100)
    print(f"{f['名称'][:26]:28s} {len(ps):>4d} {done:>5d} {v:>5d}%  {f['状态']}")

# ---------- 2. HTML ----------
s = HTML_FILE.read_text(encoding="utf-8")
print(f"\nHTML：{len(s)} 字符 / {HTML_FILE.stat().st_size} 字节")

marker = '<script id="board-data" type="application/json">'
i = s.find(marker)
if i < 0:
    print("✗ 找不到 board-data")
    raise SystemExit(1)
j = s.find("</script>", i)
data = json.loads(s[i + len(marker):j].replace("<\\/", "</"))
print(f"✓ 内嵌数据可解析：{len(data['流程'])} 条流程 / {sum(len(f['部分']) for f in data['流程'])} 个子项")

blocks = re.findall(r"<script>(.*?)</script>", s, re.S)
if not blocks:
    print("✗ 找不到业务 <script>")
    raise SystemExit(1)
JS_OUT.write_text(blocks[-1], encoding="utf-8")
print(f"✓ 业务 JS 已导出（{len(blocks[-1])} 字符）")

for el in ['id="tb"', 'id="cards"', 'id="q"', 'id="expandAll"', 'id="collapseAll"',
           'class="exp', 'class="sub"', 'class="graph"', 'class="gcard', 'class="garrow"',
           'btn small tog', 'class="wchip', 'class="wmin', 'w5', '权重 ',
           'data-status="全部"']:
    print(("✓" if el in s else "✗") + f" 元素：{el}")

# 折叠逻辑关键函数是否存在
for fn in ["function flowHTML", "function subHTML", "function graphHTML",
           "openSet.add", "nextElementSibling", "e.target.closest('a')",
           "hideDone.set", "hideDone.get"]:
    print(("✓" if fn in s else "✗") + f" 逻辑：{fn}")

# 作废标记：数据里有 `作废: true` 的子项时，HTML 必须把它们标出来（否则读者会把 0% 当成待办）
voided = [p["名称"] for f in data["流程"] for p in f.get("部分", []) if p.get("作废")]
if voided:
    has_badge = "已作废" in s
    print(("✓" if has_badge else "✗") + f" 作废标记：数据里 {len(voided)} 条作废子项"
          f"（{', '.join(voided[:3])}{'…' if len(voided) > 3 else ''}），HTML 里{'有' if has_badge else '没有'}标记")
    VOID_OK = has_badge
else:
    VOID_OK = True

# ---------- 3. 结构 ----------
class P(HTMLParser):
    VOID = {"meta", "br", "hr", "img", "input", "link", "source", "area",
            "base", "col", "embed", "param", "track", "wbr"}

    def __init__(self):
        super().__init__()
        self.stack, self.err = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.err.append((tag, self.stack[-3:]))


p = P()
p.feed(s)
print(f"{'✓' if not p.stack else '✗'} 未闭合标签：{p.stack}")
print(f"{'✓' if not p.err else '✗'} 标签不匹配：{p.err[:5]}")

# 链接可移植性：不许出现绝对 URL（file:///<盘符>/…），且每条相对链接都要落到真实文件。
# 这一条直接保证「整个文件夹搬到别的电脑，看板里的链接照样点得开」。
abs_urls = s.count("file:///")
print(f"{'✓' if abs_urls == 0 else '✗'} 绝对 file:/// URL：{abs_urls} 个（应为 0）")
links = [(x["路径"], x["url"]) for f in data["流程"] for pt in f.get("部分", [])
         for x in (pt.get("文件链接", []) + pt.get("文档链接", []))]
from urllib.parse import unquote
broken = []
for rel_path, url in links:
    if url.startswith(("http://", "https://", "file://", "#")):
        broken.append((rel_path, url, "仍是绝对或外部 URL"))
        continue
    if not (HERE / unquote(url)).exists():
        broken.append((rel_path, url, "相对本目录解析不到"))
print(f"{'✓' if not broken else '✗'} 可点击链接 {len(links)} 条，失效 {len(broken)} 条")
for rel_path, url, why in broken[:5]:
    print(f"    ✗ {why}：{rel_path} -> {url}")

ok = bool(data) and not p.stack and not p.err and abs_urls == 0 and not broken and VOID_OK

# ---------- 4. AI 交接文档一致性 ----------
AI_FILE = HERE / "AI交接.md"
if not AI_FILE.exists():
    print("✗ 缺少 AI交接.md（跑一次 生成看板.py）")
    ok = False
else:
    ai = AI_FILE.read_text(encoding="utf-8")
    print(f"\nAI交接.md：{len(ai)} 字符 / {AI_FILE.stat().st_size} 字节")
    need = ["## 1. 五分钟上手", "## 2. 环境事实", "## 3. 常用命令", "## 4. 禁止事项",
            "## 5. 既定结论", "## 6. 待办队列", "### 6.1 建议现在先做",
            "### 6.2 需要专项排期",
            "## 7. 改完怎么证明自己没改坏", "## 8. 同步规则",
            "## 9. 文件索引", "## 10. 进度快照"]
    for sec in need:
        print(("✓" if sec in ai else "✗") + f" 章节：{sec}")
        if sec not in ai:
            ok = False
    # 6.3 只在确实存在"卡外部资源"的子项时才会生成，缺席不算错
    has_blocked = "### 6.3 ⛔ 卡在外部资源上" in ai
    print(("✓ " if has_blocked else "· ") + "章节 6.3（有卡外部资源的子项时才出现）")
    # 快照数字必须与 JSON 一致，防止改了数据忘了重新生成
    import re as _re
    m = _re.search(r"当前快照：\*\*(\d+) 条流程 / (\d+) 个子项 / 整体完整度 (\d+)%\*\*", ai)
    if not m:
        print("✗ 找不到 AI交接.md 的速度快照行（格式变了？）")
        ok = False
    else:
        nf, np_, pct = int(m.group(1)), int(m.group(2)), int(m.group(3))
        same = (nf == len(d["流程"]) and np_ == len(parts_all))
        print(("✓" if same else "✗") + f" 快照与数据源一致：{nf} 流程 / {np_} 子项 / {pct}%")
        if not same:
            print("   → 数据改了但没重新生成 AI交接.md，请重跑 生成看板.py")
            ok = False
    # AGENTS.md 检查：三档，由数据文件 AI接手.检查项.根目录AGENTS 决定
    #   "fail" → 缺失判失败（默认，适合已经有 AGENTS.md 的项目）
    #   "warn" → 缺失只提示
    #   "off"  → 不检查
    mode = str((((d.get("AI接手") or {}).get("检查项") or {}).get("根目录AGENTS")) or "fail").lower()
    if mode != "off":
        # 与 生成看板.py 的项目根推导保持一致：先看数据里的 "项目根"，再向上找标记
        rel = d.get("项目根")
        if isinstance(rel, str) and rel.strip():
            root = (HERE / rel).resolve()
        else:
            root = HERE
            for _ in range(8):
                if (root / ".git").exists() or (root / "AGENTS.md").exists():
                    break
                if root.parent == root:
                    break
                root = root.parent
        agents = root / "AGENTS.md"
        hit = agents.exists()
        if not hit and mode == "fail":
            print(f"✗ 项目根 AGENTS.md：{agents}（可在数据文件里把 检查项.根目录AGENTS 设为 warn/off）")
            ok = False
        else:
            print(("✓" if hit else "⚠") + f" 项目根 AGENTS.md：{agents}" + ("" if hit else "（未找到，warn 模式不失败）"))

print("\n结论：" + ("✅ 自检通过（JS 语法请再跑 node --check _check.js）" if ok else "❌ 有问题"))
raise SystemExit(0 if ok else 1)
