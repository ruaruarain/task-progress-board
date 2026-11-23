# -*- coding: utf-8 -*-
"""验收测试：故意造 5 个违规，确认 同步.py 的体检真的能拦住（证明标准有牙齿）。

不修改真实数据：全部在内存副本上做。
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent

spec = importlib.util.spec_from_file_location("sync_mod", str(HERE / "同步.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

base = json.loads((HERE / "看板数据.json").read_text(encoding="utf-8"))

CASES = []


def case(name, mutate, expect_kw):
    d = copy.deepcopy(base)
    mutate(d)
    mod.problems.clear()
    mod.warnings.clear()
    mod.lint(d)
    hit = [p for p in mod.problems if expect_kw in p]
    CASES.append((name, bool(hit), hit[0] if hit else "（没抓到）"))


def f0(d):
    return d["流程"][0]["部分"]


def f1(d):
    return d["流程"][1]["部分"]


case("完整度超范围 150", lambda d: f0(d)[0].__setitem__("完整度", 150), "完整度必须是 0~100")
case("权重非法 9", lambda d: f0(d)[0].__setitem__("权重", 9), "权重必须是 1~5")
case("路径用反斜杠 + 不存在",
     lambda d: f0(d)[0].__setitem__("文件", ["不存在目录\\不存在.py"]), "反斜杠")
case("100% 还挂卡点",
     lambda d: f0(d)[0].__setitem__("卡点", "其实还没好"), "完整度 100% 但仍写着卡点")
case("未完成且说不清还差什么",
     lambda d: (f1(d)[3].__setitem__("完整度", 40),
                f1(d)[3].__setitem__("说明", "还在搞"),
                f1(d)[3].pop("卡点", None)), "没写「还差什么」")
case("状态非法", lambda d: d["流程"][0].__setitem__("状态", "差不多好了"), "状态")
case("子项重名",
     lambda d: f0(d).append({**f0(d)[0], "完整度": 0}), "子项名重复")
case("缺 AI接手 区块", lambda d: d.pop("AI接手", None), "AI接手")

print(f"{'违规类型':32s} 结果  说明")
all_ok = True
for name, ok, detail in CASES:
    all_ok = all_ok and ok
    print(f"{name:32s} {'✓ 拦住' if ok else '✗ 漏检'}  {detail[:70]}")

# 反向验证：原始数据必须 0 错误
mod.problems.clear()
mod.lint(base)
print(f"\n原始数据体检：{len(mod.problems)} 个错误（应为 0）")
all_ok = all_ok and not mod.problems

print("\n结论：" + ("✅ 体检机制有效（8 类违规全部拦住，原始数据 0 错误）" if all_ok else "❌ 有漏检"))
raise SystemExit(0 if all_ok else 1)
