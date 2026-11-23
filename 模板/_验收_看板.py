# -*- coding: utf-8 -*-
"""看板版面验收：确认「流程图（阶段分列）」与「一键隐藏已完成」真的生成出来了。

只读产物，不改任何文件。
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
HTML = (HERE / "任务看板.html").read_text(encoding="utf-8")

m = re.search(r'<script id="board-data" type="application/json">(.*?)</script>', HTML, re.S)
if not m:
    print("✗ 找不到内嵌数据")
    raise SystemExit(1)
data = json.loads(m.group(1).replace("<\\/", "</"))

ok = True
print("=== 1. 阶段分列（流程图数据）===")
for f in data["流程"]:
    stages = f.get("阶段列表") or []
    parts = f.get("部分", [])
    total = sum(len(s["索引"]) for s in stages)
    flat = sorted(i for s in stages for i in s["索引"])
    cover_ok = (total == len(parts)) and (flat == list(range(len(parts))))
    ok = ok and cover_ok and len(stages) >= 2
    flag = "✓" if cover_ok and len(stages) >= 2 else "✗"
    print(f"  {flag} {f['id']:3s} 子项{len(parts):3d}  阶段{len(stages)}  "
          + " → ".join(f"{s['阶段']}({len(s['索引'])})" for s in stages))

print("\n=== 2. 渲染钩子是否在 HTML 里 ===")
for needle, label in [
    ('class="graph"', "流程图容器"),
    ('class="stage"', "阶段列"),
    ('class="gcard', "子项方块"),
    ('class="garrow"', "列间箭头"),
    ('btn small tog', "隐藏已完成按钮"),
    ('hideDone.set', "隐藏状态写入"),
    ('hideDone.get', "隐藏状态读取"),
    ('function graphHTML', "graphHTML 函数"),
    ('gcard.hide', "方块隐藏样式"),
    ('.sub.hide', "列表行隐藏样式"),
]:
    hit = needle in HTML
    ok = ok and hit
    print(("✓" if hit else "✗") + f" {label}：{needle}")

print("\n=== 3. 每个流程的「已完成」子项数（供隐藏按钮显示）===")
for f in data["流程"]:
    done = sum(1 for p in f.get("部分", []) if p.get("完整度", 0) >= 100)
    print(f"  {f['id']:3s} 已完成 {done:2d} / {len(f.get('部分', [])):2d}")

print("\n=== 4. 权重是否齐全并可渲染 ===")
from collections import Counter
dist = Counter()
bad = []
for f in data["流程"]:
    for p in f.get("部分", []):
        w = p.get("权重", 1)
        dist[w] += 1
        if not isinstance(w, int) or not (1 <= w <= 5):
            bad.append(f"{f['id']} / {p['名称']} = {w!r}")
for w in sorted(dist):
    print(f"  权重 {w}：{dist[w]:3d} 个子项")
if bad:
    ok = False
    print("  ✗ 非法权重：", "; ".join(bad))
else:
    print("  ✓ 全部子项权重在 1~5 内")
for needle, label in [('class="wchip', "列表里的权重徽标"),
                      ('class="wmin', "流程图方块上的权重"),
                      ('.w5{', "权重 5 的红色样式")]:
    hit = needle in HTML
    ok = ok and hit
    print(("✓" if hit else "✗") + f" {label}：{needle}")

print("\n结论：" + ("✅ 版面验收通过" if ok else "❌ 有问题"))
raise SystemExit(0 if ok else 1)
