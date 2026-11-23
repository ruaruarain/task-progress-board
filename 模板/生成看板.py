# -*- coding: utf-8 -*-
"""生成「项目流程看板」单文件 HTML（手风琴展开版）。

用法：
    python 生成看板.py                 # 读同目录 看板数据.json -> 写 任务看板.html
    python 生成看板.py 数据.json 输出.html

交互：
  * 表格一行 = 一条流程；**点击整行在该行下方展开**，子项按 JSON 顺序一行一条
  * 每条子项显示：序号 / 名称 / 完成度条 / 说明 / 依赖文件 / 说明文档 / 卡点
  * 顶部：状态筛选、关键词搜索（命中子项时自动展开该流程）、展开全部/收起全部
  * 纯静态、无外部依赖、断网可用
"""
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE / "看板数据.json"
DEFAULT_OUT = HERE / "任务看板.html"


def _project_root(data=None) -> Path:
    """推断「项目根」——所有 `文件` / `文档` 路径都相对它。

    优先级：
      1. 数据文件顶层字段 `"项目根"`（相对本目录，如 ".."、"../.."），显式可控；
      2. 从本目录向上找含 `.git` 或 `AGENTS.md` 的目录；
      3. 回退：本目录上两级（默认把看板放在 `<项目>/<任意目录>/看板/`）。
    """
    if data:
        rel = data.get("项目根")
        if isinstance(rel, str) and rel.strip():
            return (HERE / rel).resolve()
    cur = HERE
    for _ in range(8):
        if (cur / ".git").exists() or (cur / "AGENTS.md").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return HERE.parent.parent


PROJECT_ROOT = _project_root()


def rel_url(rel_path: str) -> str:
    """把「相对项目根」的路径转成「相对本 HTML 文件」的相对 URL。

    用相对地址而不是绝对 URL（file:///…） ，是为了整个文件夹打包搬到别的电脑/别的盘后，
    看板里的链接照样点得开。空格、括号、中文由 quote 处理。
    """
    target = (PROJECT_ROOT / rel_path).resolve()
    rel = os.path.relpath(target, HERE).replace("\\", "/")
    return quote(rel, safe="/")


def enrich(data: dict) -> dict:
    for flow in data.get("流程", []):
        parts = flow.get("部分", [])
        for part in parts:
            part["文件链接"] = [{"路径": f, "名": Path(f).name, "url": rel_url(f)} for f in part.get("文件", [])]
            part["文档链接"] = [{"路径": d, "名": Path(d).name, "url": rel_url(d)} for d in part.get("文档", [])]
        flow["子项数"] = len(parts)
        flow["已完成子项"] = sum(1 for p in parts if p.get("完整度", 0) >= 100)
        # 按「阶段」聚合成列，供流程图渲染（同列=并行，列间=先后）
        order, buckets = [], {}
        for idx, p in enumerate(parts):
            st = p.get("阶段") or "全部"
            if st not in buckets:
                buckets[st] = []
                order.append(st)
            buckets[st].append(idx)
        flow["阶段列表"] = [{"阶段": s, "索引": buckets[s]} for s in order]
        wsum = sum(p.get("权重", 1) for p in parts)
        flow["完整度"] = round(sum(p.get("权重", 1) * p.get("完整度", 0) for p in parts) / wsum) if wsum else 0
        flow["开放卡点数"] = sum(1 for p in parts if p.get("卡点")) + len(flow.get("卡点", []))
    flows = data.get("流程", [])
    all_parts = [p for f in flows for p in f.get("部分", [])]
    wtotal = sum(p.get("权重", 1) for p in all_parts)
    data["统计"] = {
        "流程数": len(flows),
        "子项总数": len(all_parts),
        "整体完整度": round(sum(p.get("权重", 1) * p.get("完整度", 0) for p in all_parts) / wtotal) if wtotal else 0,
        "子项已完成": sum(1 for p in all_parts if p.get("完整度", 0) >= 100),
        "子项未开始": sum(1 for p in all_parts if p.get("完整度", 0) == 0),
        "加权口径": "按子项重要度加权（1=普通 / 5=决定能否交付）",
        "可用": sum(1 for f in flows if f.get("状态") == "可用"),
        "部分可用": sum(1 for f in flows if f.get("状态") == "部分可用"),
        "待修": sum(1 for f in flows if f.get("状态") == "待修"),
        "阻塞": sum(1 for f in flows if f.get("状态") == "阻塞"),
        "未开始": sum(1 for f in flows if f.get("状态") == "未开始"),
    }
    return data


HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root{
    --bg:#f5f7fb; --card:#fff; --ink:#1f2937; --muted:#6b7280; --line:#e5e7eb;
    --green:#16a34a; --blue:#2563eb; --amber:#d97706; --red:#dc2626; --gray:#94a3b8; --teal:#0d9488;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:14px/1.55 "Microsoft YaHei","PingFang SC",system-ui,-apple-system,Segoe UI,sans-serif}
  .wrap{max-width:1240px;margin:0 auto;padding:22px 20px 70px}
  h1{margin:0 0 4px;font-size:21px}
  .sub{color:var(--muted);font-size:12.5px}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(112px,1fr));gap:10px;margin:16px 0 14px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:9px 12px}
  .card .k{font-size:11.5px;color:var(--muted)}
  .card .v{font-size:19px;font-weight:700;margin-top:2px;font-variant-numeric:tabular-nums}
  .toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:4px 0 12px}
  .chip{border:1px solid var(--line);background:#fff;border-radius:999px;padding:5px 12px;cursor:pointer;
    font-size:12.5px;color:var(--muted);user-select:none;transition:.15s}
  .chip:hover{border-color:#cbd5e1}
  .chip.on{background:#111827;color:#fff;border-color:#111827}
  .btn{border:1px solid var(--line);background:#fff;border-radius:9px;padding:7px 13px;cursor:pointer;
    font-size:12.5px;color:#334155}
  .btn:hover{background:#f8fafc}
  input[type=search]{flex:1;min-width:190px;border:1px solid var(--line);border-radius:9px;padding:8px 11px;
    font-size:13px;background:#fff;outline:none}
  input[type=search]:focus{border-color:#93c5fd;box-shadow:0 0 0 3px #dbeafe}
  table.main{width:100%;border-collapse:separate;border-spacing:0 6px}
  thead th{font-size:11.5px;color:var(--muted);font-weight:600;text-align:left;padding:0 12px 2px}
  tr.flow{background:var(--card);cursor:pointer}
  tr.flow td{padding:12px;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
  tr.flow td:first-child{border-left:1px solid var(--line);border-radius:10px 0 0 10px}
  tr.flow td:last-child{border-right:1px solid var(--line);border-radius:0 10px 10px 0}
  tr.flow:hover td{background:#fbfdff}
  tr.flow.open td{background:#f8fbff;border-bottom-color:transparent}
  tr.flow.open td:first-child{border-radius:10px 0 0 0}
  tr.flow.open td:last-child{border-radius:0 10px 0 0}
  .arrow{display:inline-block;width:14px;color:#94a3b8;transition:transform .15s;font-size:11px}
  tr.flow.open .arrow{transform:rotate(90deg);color:#2563eb}
  .name{font-weight:700;font-size:14.5px}
  .desc{color:var(--muted);font-size:12px;margin-top:2px}
  .pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11.5px;font-weight:700;white-space:nowrap}
  .bar{position:relative;height:7px;border-radius:999px;background:#eef2f7;overflow:hidden;min-width:80px}
  .bar>i{position:absolute;left:0;top:0;bottom:0;border-radius:999px;display:block}
  .pctwrap{display:flex;align-items:center;gap:8px}
  .pct{font-variant-numeric:tabular-nums;font-weight:700;font-size:12.5px;min-width:38px;text-align:right}
  .num{font-variant-numeric:tabular-nums;color:var(--muted)}
  /* 展开区 */
  tr.exp{background:#f8fbff}
  tr.exp>td{padding:0;border-bottom:1px solid var(--line);border-left:1px solid var(--line);
    border-right:1px solid var(--line);border-radius:0 0 10px 10px}
  tr.exp.hide{display:none}
  .expbox{padding:6px 14px 16px 30px}
  .exphead{display:flex;gap:10px;align-items:center;color:var(--muted);font-size:11.5px;
    padding:4px 0 10px;border-bottom:1px dashed var(--line);margin-bottom:4px}
  .sub{display:grid;grid-template-columns:40px minmax(0,1fr) 148px;gap:12px;
    padding:10px 0 10px 10px;border-bottom:1px dashed #e8edf4;border-left:3px solid transparent}
  .sub:last-child{border-bottom:0}
  .s-no{font-size:11.5px;color:#94a3b8;font-variant-numeric:tabular-nums;padding-top:2px}
  .s-name{font-weight:700;font-size:13.5px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .s-desc{color:#4b5563;font-size:12.3px;margin-top:3px}
  .s-links{margin-top:4px;display:flex;gap:12px;flex-wrap:wrap;font-size:11.5px}
  .s-links a{color:#1d4ed8;text-decoration:none}
  .s-links a:hover{text-decoration:underline}
  .s-links .tag{color:#94a3b8}
  .s-kt{margin-top:5px;font-size:11.5px;color:#b91c1c;background:#fef2f2;border:1px solid #fecaca;
    border-radius:7px;padding:4px 8px;display:inline-block}
  .s-bar{padding-top:2px}
  .s-bar .bar{margin-bottom:3px}
  .s-bar .t{font-size:11px;color:var(--muted);text-align:right;font-variant-numeric:tabular-nums}
  .tagmin{font-size:10.5px;font-weight:700;border-radius:5px;padding:1px 6px;background:#f1f5f9;color:#64748b}
  .hint{color:var(--muted);font-size:12px;margin-top:14px}
  /* 流程图 */
  .legend{font-size:11.5px;color:var(--muted);margin:6px 0 2px}
  .listsep{font-size:11.5px;color:var(--muted);font-weight:700;margin:14px 0 4px;
    border-top:1px dashed var(--line);padding-top:10px}
  .graph{display:flex;gap:6px;overflow-x:auto;padding:8px 0 4px;align-items:stretch}
  .stage{background:#fff;border:1px solid var(--line);border-radius:10px;padding:8px;
    min-width:146px;max-width:200px;flex:0 0 auto;display:flex;flex-direction:column}
  .stage-head{font-size:10.8px;color:var(--muted);font-weight:700;margin-bottom:7px;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .stage-body{display:flex;flex-direction:column;gap:6px}
  .gcard{border:1px solid #e8edf4;border-left:3px solid var(--gray);border-radius:8px;
    padding:6px 7px;background:#fcfdff;cursor:default}
  .gcard.hide,.sub.hide{display:none}
  .gn{font-size:11.3px;font-weight:600;line-height:1.3;margin-bottom:4px;
    display:flex;gap:4px;align-items:flex-start;justify-content:space-between}
  .gn>span:first-child{flex:1;min-width:0;word-break:break-all}
  /* 权重徽标：1 灰 → 5 红，越重要越显眼 */
  .wchip{display:inline-block;font-size:10.5px;font-weight:700;border-radius:5px;
    padding:1px 6px;white-space:nowrap;margin-left:8px;vertical-align:1px}
  .wmin{font-size:9.5px;font-weight:700;border-radius:4px;padding:1px 4px;flex:0 0 auto;line-height:1.25}
  .w1{background:#f1f5f9;color:#64748b}
  .w2{background:#eff6ff;color:#1d4ed8}
  .w3{background:#fef3c7;color:#92400e}
  .w4{background:#ffedd5;color:#9a3412}
  .w5{background:#fee2e2;color:#991b1b}
  .gbar{height:5px;border-radius:999px;background:#eef2f7;overflow:hidden}
  .gbar>i{display:block;height:100%;border-radius:999px}
  .gp{font-size:10.5px;text-align:right;margin-top:2px;font-variant-numeric:tabular-nums}
  .garrow{align-self:center;color:#94a3b8;font-size:15px;flex:0 0 auto;padding:0 1px}
  .btn.small{padding:3px 9px;font-size:11.5px;border-radius:7px}
  @media (max-width:820px){
    .sub{grid-template-columns:26px minmax(0,1fr);}
    .s-bar{grid-column:2;display:flex;align-items:center;gap:8px}
    .s-bar .bar{flex:1;margin:0}
  }
</style>
</head>
<body>
<div class="wrap">
  <h1 id="title"></h1>
  <div class="sub" id="subtitle"></div>
  <div class="cards" id="cards"></div>

  <div class="toolbar">
    <div class="chip on" data-status="全部">全部</div>
    <div class="chip" data-status="可用">可用</div>
    <div class="chip" data-status="部分可用">部分可用</div>
    <div class="chip" data-status="待修">待修</div>
    <div class="chip" data-status="阻塞">阻塞</div>
    <div class="chip" data-status="未开始">未开始</div>
    <button class="btn" id="expandAll">展开全部</button>
    <button class="btn" id="collapseAll">收起全部</button>
    <input type="search" id="q" placeholder="搜索流程或子项…（例：选型、表头、照度、置信区间）">
  </div>

  <table class="main">
    <thead><tr>
      <th style="width:46%">流程</th>
      <th style="width:86px">状态</th>
      <th style="width:170px">整体完成度</th>
      <th style="width:104px">子项完成</th>
      <th style="width:74px">卡点</th>
      <th style="width:88px">更新</th>
    </tr></thead>
    <tbody id="tb"></tbody>
  </table>

  <div class="hint">点击任意一行 → 在该行下方按流程顺序展开全部子项；再点一次收起。展开后可点链接直接打开文件/文档。</div>
</div>

<script id="board-data" type="application/json">__DATA__</script>
<script>
(function(){
  const DATA = JSON.parse(document.getElementById('board-data').textContent);
  const flows = DATA['流程'] || [];
  const BG = {'可用':'#dcfce7','部分可用':'#ccfbf1','待修':'#fef3c7','阻塞':'#fee2e2','未开始':'#f1f5f9'};
  const FG = {'可用':'#166534','部分可用':'#115e59','待修':'#92400e','阻塞':'#991b1b','未开始':'#475569'};

  function barColor(v){ return v>=100?'var(--green)': v>=70?'var(--blue)': v>=40?'var(--amber)': v>0?'#ea580c':'var(--gray)'; }
  function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

  document.getElementById('title').textContent = DATA['标题'] || '项目流程看板';
  document.getElementById('subtitle').textContent =
    '更新：' + (DATA['更新日期']||'—') + '　·　' + (DATA['更新人']||'') + '　·　' + (DATA['说明']||'');

  const st = DATA['统计'] || {};
  const cards = [
    ['整体完整度（加权）', (st['整体完整度']??'—')+'%'],
    ['子项已完成', st['子项已完成'] ?? '—'],
    ['子项总数', st['子项总数'] ?? '—'],
    ['子项未开始', st['子项未开始'] ?? '—'],
    ['流程数', st['流程数'] ?? '—'],
    ['可用', st['可用'] ?? 0], ['待修', st['待修'] ?? 0], ['阻塞', st['阻塞'] ?? 0]
  ];
  document.getElementById('cards').innerHTML = cards.map(([k,v])=>
    '<div class="card"><div class="k">'+esc(k)+'</div><div class="v">'+esc(v)+'</div></div>').join('');

  let filterStatus = '全部', keyword = '';
  const openSet = new Set();      // 哪些流程处于展开状态
  const hideDone = new Map();     // 流程下标 -> 是否隐藏已完成子项

  function subHTML(p, idx, hide){
    const v = p['完整度'] ?? 0;
    const c = barColor(v);
    let files = (p['文件链接']||[]).map(x=>'<a href="'+x['url']+'" target="_blank" title="'+esc(x['路径'])+'">'+esc(x['名'])+'</a>');
    let docs  = (p['文档链接']||[]).map(x=>'<a href="'+x['url']+'" target="_blank" title="'+esc(x['路径'])+'">'+esc(x['名'])+'</a>');
    let links = '';
    if(files.length) links += '<span><span class="tag">📄 依赖文件：</span>'+files.join('　')+'</span>';
    if(docs.length)  links += '<span><span class="tag">📘 说明文档：</span>'+docs.join('　')+'</span>';
    const hidden = (hide && v >= 100) ? ' hide' : '';
    return '<div class="sub'+hidden+'" style="border-left-color:'+c+'">'
      + '<div class="s-no">'+String(idx).padStart(2,'0')+'</div>'
      + '<div>'
      +   '<div class="s-name">'+esc(p['名称'])
      +     '<span class="wchip w'+(p['权重']||1)+'" title="权重 '+ (p['权重']||1) +'：1=普通，3=重要，5=决定该模块能否交付">权重 '+(p['权重']||1)+'</span>'
      +     (p['作废']?'<span class="wchip w1" style="opacity:.6" title="'+esc(p['作废说明']||'已作废')+'">已作废</span>':'')
      +   '</div>'
      +   (p['说明']?'<div class="s-desc">'+esc(p['说明'])+'</div>':'')
      +   (links?'<div class="s-links">'+links+'</div>':'')
      +   (p['卡点']?'<div class="s-kt">⚠ '+esc(p['卡点'])+'</div>':'')
      + '</div>'
      + '<div class="s-bar"><div class="bar"><i style="width:'+v+'%;background:'+c+'"></i></div>'
      +   '<div class="t" style="color:'+c+'">'+v+'%</div></div>'
      + '</div>';
  }

  function graphHTML(f, i, hide){
    const stages = f['阶段列表']||[];
    const parts = f['部分']||[];
    if(!stages.length) return '';
    let h = '<div class="graph">';
    stages.forEach((s, si)=>{
      if(si) h += '<div class="garrow">→</div>';
      h += '<div class="stage"><div class="stage-head">阶段 '+(si+1)+' · '+esc(s['阶段'])+'</div><div class="stage-body">';
      (s['索引']||[]).forEach(idx=>{
        const p = parts[idx]; if(!p) return;
        const v = p['完整度'] ?? 0, c = barColor(v);
        const hidden = (hide && v >= 100) ? ' hide' : '';
        h += '<div class="gcard'+hidden+'" style="border-left-color:'+c+'" title="权重 '+ (p['权重']||1) +'｜'+esc(p['说明']||'')+'">'
          + '<div class="gn"><span>'+esc(p['名称'])+'</span>'
          +   '<span class="wmin w'+(p['权重']||1)+'">W'+(p['权重']||1)+'</span></div>'
          + '<div class="gbar"><i style="width:'+v+'%;background:'+c+'"></i></div>'
          + '<div class="gp" style="color:'+c+'">'+v+'%</div></div>';
      });
      h += '</div></div>';
    });
    h += '</div>';
    return h;
  }

  function flowHTML(f, i){
    const stt = f['状态']||'未开始', pct = f['完整度']||0, c = barColor(pct);
    const parts = f['部分']||[];
    const hide = !!hideDone.get(i);
    const doneN = parts.filter(p=>(p['完整度']??0)>=100).length;
    const subs = parts.map((p,k)=>subHTML(p,k+1,hide)).join('');
    const kt = (f['卡点']||[]);
    const opened = openSet.has(i) ? ' open' : '';
    const expHide = openSet.has(i) ? '' : ' hide';
    const togLabel = hide ? ('显示已完成 ('+doneN+')') : ('隐藏已完成 ('+doneN+')');
    return '<tr class="flow'+opened+'" data-i="'+i+'">'
      + '<td><div class="name"><span class="arrow">▶</span> '+esc(f['名称'])+'</div>'
      +   '<div class="desc">'+esc(f['一句话'])+'</div></td>'
      + '<td><span class="pill" style="background:'+(BG[stt]||'#f1f5f9')+';color:'+(FG[stt]||'#475569')+'">'+esc(stt)+'</span></td>'
      + '<td><div class="pctwrap"><div class="bar" style="flex:1"><i style="width:'+pct+'%;background:'+c+'"></i></div>'
      +   '<span class="pct" style="color:'+c+'">'+pct+'%</span></div></td>'
      + '<td class="num">'+(f['已完成子项']||0)+' / '+(f['子项数']||0)+'</td>'
      + '<td class="num">'+(f['开放卡点数']?f['开放卡点数']+' 个':'—')+'</td>'
      + '<td class="num">'+esc(f['更新']||'')+'</td></tr>'
      + '<tr class="exp'+expHide+'" data-i="'+i+'"><td colspan="6"><div class="expbox">'
      +   '<div class="exphead"><b>'+parts.length+' 个子项</b>'
      +     '　·　已完成 '+(f['已完成子项']||0)+' 个'
      +     '　·　按流程顺序排列'
      +     (doneN?'　·　<button class="btn small tog" data-i="'+i+'">'+togLabel+'</button>':'')
      +   '</div>'
      +   '<div class="legend">⬆ 流程图：<b>同一列内的子项互不依赖、可并行</b>；列与列之间才是先后顺序。'
      +     '<b>W1~W5 = 权重</b>（1 普通 · 3 重要 · 5 决定该模块能否交付），越重要数字越红。</div>'
      +   graphHTML(f, i, hide)
      +   '<div class="listsep">子项明细（按流程顺序）</div>'
      +   (subs || '<div class="s-desc">（尚未拆分子项）</div>')
      +   (kt.length?'<div style="margin-top:10px;font-size:11.5px;color:#b91c1c"><b>本条链整体卡点：</b>'+kt.map(esc).join('；')+'</div>':'')
      + '</div></td></tr>';
  }

  function match(f){
    if(filterStatus!=='全部' && f['状态']!==filterStatus) return false;
    if(!keyword) return true;
    const k = keyword.toLowerCase();
    if((f['名称']||'').toLowerCase().includes(k)) return true;
    if((f['一句话']||'').toLowerCase().includes(k)) return true;
    return (f['部分']||[]).some(p=>(p['名称']||'').toLowerCase().includes(k)
        || (p['说明']||'').toLowerCase().includes(k));
  }

  const tb = document.getElementById('tb');
  function render(){
    const visible = flows.map((f,i)=>({f,i})).filter(x=>match(x.f));
    tb.innerHTML = visible.length ? visible.map(x=>flowHTML(x.f, x.i)).join('')
      : '<tr><td colspan="6" style="text-align:center;color:#94a3b8;padding:28px">没有匹配的流程</td></tr>';
  }

  tb.addEventListener('click', e=>{
    const tg = e.target.closest('button.tog');       // 一键隐藏/显示已完成子项
    if(tg){
      e.stopPropagation();
      const ti = +tg.dataset.i;
      hideDone.set(ti, !hideDone.get(ti));
      openSet.add(ti);                               // 保持展开，别让它塌回去
      render();
      return;
    }
    if(e.target.closest('a')) return;               // 点链接不触发折叠
    const tr = e.target.closest('tr.flow'); if(!tr) return;
    const i = +tr.dataset.i;
    if(openSet.has(i)) openSet.delete(i); else openSet.add(i);
    const exp = tr.nextElementSibling;
    if(exp && exp.classList.contains('exp')){
      exp.classList.toggle('hide', !openSet.has(i));
      tr.classList.toggle('open', openSet.has(i));
    }
  });

  document.querySelectorAll('.chip').forEach(ch=>{
    ch.addEventListener('click', ()=>{
      document.querySelectorAll('.chip').forEach(c=>c.classList.remove('on'));
      ch.classList.add('on'); filterStatus = ch.dataset.status; render();
    });
  });
  document.getElementById('q').addEventListener('input', e=>{
    keyword = e.target.value.trim();
    if(keyword){ flows.forEach((f,i)=>{ if(match(f)) openSet.add(i); }); }
    render();
  });
  document.getElementById('expandAll').addEventListener('click', ()=>{
    flows.forEach((f,i)=>{ if(match(f)) openSet.add(i); }); render();
  });
  document.getElementById('collapseAll').addEventListener('click', ()=>{ openSet.clear(); render(); });
  document.addEventListener('keydown', e=>{ if(e.key==='Escape'){ openSet.clear(); render(); } });

  render();
})();
</script>
</body>
</html>
"""


def render_ai_md(data: dict) -> str:
    """从同一份 JSON 生成给 AI agent 看的交接文档。"""
    ai = data.get("AI接手", {})
    st = data["统计"]
    L = []
    add = L.append
    add("# AI 交接文档（自动生成，勿手改）")
    add("")
    add(f"> 由 `生成看板.py` 从 `看板数据.json` 生成于 {data.get('更新日期', '—')}。"
        f"要改内容请改 JSON 后重新生成。")
    add(f"> 当前快照：**{st['流程数']} 条流程 / {st['子项总数']} 个子项 / 整体完整度 {st['整体完整度']}%**"
        f"（已完成 {st['子项已完成']} 个，未开始 {st['子项未开始']} 个）")
    add("")
    if ai.get("一句话"):
        add(f"**{ai['一句话']}**")
        add("")

    # 1 读序
    if ai.get("读序"):
        add("## 1. 五分钟上手：按这个顺序读")
        add("")
        for i, x in enumerate(ai["读序"], 1):
            add(f"{i}. {x}")
        add("")
        cmds = ai.get("常用命令", [])
        fast = next((c for c in cmds if "自检" in c.get("用途", "")), None)
        if fast:
            add("然后先跑这一条确认环境没坏：")
            add("")
            add("```powershell")
            add("$env:PYTHONIOENCODING='utf-8'")
            add(fast["命令"])
            add("```")
            add("")
            add(f"期望：{fast['期望']}")
            add("")

    # 2 环境
    env = ai.get("环境", {})
    if env:
        add("## 2. 环境事实（别自己再摸一遍）")
        add("")
        for k in ["工作目录", "解释器", "python版本", "编码要求", "版本控制"]:
            if env.get(k):
                add(f"- **{k}**：`{env[k]}`" if k in ("工作目录", "解释器") else f"- **{k}**：{env[k]}")
        if env.get("已装关键包"):
            add(f"- **已装关键包**：{'、'.join(env['已装关键包'])}")
        if env.get("缺失包及后果"):
            add("- **缺失包及后果**：")
            for pkg, why in env["缺失包及后果"].items():
                add(f"  - `{pkg}`：{why}")
        add("")

    # 3 命令
    if ai.get("常用命令"):
        add("## 3. 常用命令（复制即用，都验证过）")
        add("")
        add("| 用途 | 命令 | 期望输出 |")
        add("|---|---|---|")
        for c in ai["常用命令"]:
            add(f"| {c['用途']} | `{c['命令']}` | {c.get('期望', '')} |")
        add("")

    # 4 禁止
    if ai.get("禁止事项"):
        add("## 4. 禁止事项（这些坑已经踩过，别再踩）")
        add("")
        for i, x in enumerate(ai["禁止事项"], 1):
            add(f"**{i}. {x['事']}**")
            add("")
            add(f"- 原因：{x['原因']}")
            if x.get("证据"):
                add(f"- 证据：`{x['证据']}`")
            add("")

    # 5 既定结论
    if ai.get("既定结论"):
        add("## 5. 既定结论（已核实，别重新推导）")
        add("")
        add("| 结论 | 用途 | 出处 |")
        add("|---|---|---|")
        for x in ai["既定结论"]:
            add(f"| {x['结论']} | {x.get('用途', '')} | `{x.get('文件', '')}` |")
        add("")

    # 6 待办队列（自动生成）
    add("## 6. 待办队列（按「重要度 × 未完成度」降序，自动生成）")
    add("")
    add("> 这是当前最该动的东西。权重 5 = 决定该模块能否交付；权重 1 = 普通环节。")
    add("")
    queue = []
    for f in data["流程"]:
        for p in f.get("部分", []):
            v = p.get("完整度", 0)
            if v >= 100:
                continue
            if p.get("作废"):
                continue          # 已作废的只留在看板上供追溯，不进待办队列
            w = p.get("权重", 1)
            queue.append((w * (100 - v), w, v, f["名称"], f["id"], p))
    queue.sort(key=lambda t: (-t[0], -t[1], t[2]))

    # 判断「能不能现在立刻开工」：卡点里出现这些词 = 卡在外部资源上
    BLOCK_KW = ["需公司", "需装", "需授权", "需图纸", "需确认", "需负责人", "需工艺",
                "需联网", "需拍板", "需懂", "缺 streamlit", "缺 openai", "缺本地模型",
                "缺 xlrd", "无真实", "待确认", "口径待",
                "无 streamlit", "无 openai", "无本地模型", "无 xlrd", "无法启动",
                "无法运行验证", "需 openai", "需本地模型", "需 qwen", "K01", "K02"]

    def label_of(kt):
        return kt if kt else ""

    def can_start(p):
        txt = label_of(p.get("卡点", ""))
        return not any(k in txt for k in BLOCK_KW)

    if not queue:
        add("（当前没有未完成子项）")
        add("")
    else:
        add("| # | 优先级分 | 可开工 | 体量 | 流程 | 子项 | 完成度 | 权重 | 说明 | 依赖文件 | 卡点 |")
        add("|---|---|---|---|---|---|---|---|---|---|---|")
        for i, (score, w, v, fname, fid, p) in enumerate(queue, 1):
            files = "<br>".join(f"`{x}`" for x in p.get("文件", [])) or "—"
            mark = "✅" if can_start(p) else "⛔"
            add(f"| {i} | {score} | {mark} | {p.get('体量', '小')} | {fid} {fname.split(' ', 1)[-1]} | "
                f"{p['名称']} | {v}% | {w} | {p.get('说明', '')} | {files} | {p.get('卡点', '—')} |")
        add("")
        # 立刻能开工 = 不卡外部资源 且 体量为小
        small_ready = [t for t in queue if can_start(t[5]) and t[5].get("体量", "小") == "小"]
        mid_ready = [t for t in queue if can_start(t[5]) and t[5].get("体量", "小") == "中"]
        pick = (small_ready or mid_ready or [t for t in queue if can_start(t[5])])[:6]
        add("### 6.1 建议现在先做（小体量 + 不卡外部资源）")
        add("")
        if pick:
            for t in pick:
                add(f"- [ ] **{t[5]['名称']}**（{t[5].get('完整度', 0)}%，权重 {t[1]}）"
                    f" — {t[5].get('说明', '')}")
                if t[5].get("文件"):
                    add(f"  - 改这里：{'、'.join('`' + x + '`' for x in t[5]['文件'])}")
        else:
            add("（没有满足条件的小活，见下方大活与阻塞项）")
        add("")
        big = [t for t in queue if t[5].get("体量") == "大"]
        if big:
            add("### 6.2 需要专项排期的大活（别顺手干，会烂尾）")
            add("")
            for t in big:
                add(f"- **{t[5]['名称']}**（{t[5].get('完整度', 0)}%）— {t[5].get('说明', '')}")
            add("")
        blocked = [t for t in queue if not can_start(t[5])]
        if blocked:
            add(f"### 6.3 ⛔ 卡在外部资源上（{len(blocked)} 条，先把资源要到手）")
            add("")
            for t in blocked:
                add(f"- {t[5]['名称']}：{t[5].get('卡点', '')}")
            add("")

    # 7 验证归属
    if ai.get("验证归属"):
        add("## 7. 改完怎么证明自己没改坏")
        add("")
        add("| 你动了什么 | 必须跑 | 期望 |")
        add("|---|---|---|")
        for x in ai["验证归属"]:
            add(f"| {x['流程']} | `{x['命令']}` | {x['期望']} |")
        add("")

    # 8 同步协议
    if ai.get("同步协议"):
        add("## 8. 同步规则（永不自动 · 需用户同意）")
        add("")
        for i, x in enumerate(ai["同步协议"], 1):
            add(f"{i}. {x}")
        add("")

    # 9 文件索引
    add("## 9. 文件索引（全部来自看板数据，去重）")
    add("")
    all_files, all_docs = [], []
    for f in data["流程"]:
        for p in f.get("部分", []):
            for x in p.get("文件", []):
                if x not in all_files:
                    all_files.append(x)
            for x in p.get("文档", []):
                if x not in all_docs and x not in all_files:
                    all_docs.append(x)
    code = [x for x in all_files if x.lower().endswith((".py", ".js", ".mjs", ".ps1", ".cmd"))]
    dataf = [x for x in all_files if x.lower().endswith((".xlsx", ".xls", ".csv", ".json", ".docx", ".pdf", ".dwg", ".txt"))]
    other = [x for x in all_files if x not in code and x not in dataf]
    add(f"- **代码/脚本（{len(code)}）**：")
    for x in code:
        add(f"  - `{x}`")
    add(f"- **数据文件（{len(dataf)}）**：")
    for x in dataf:
        add(f"  - `{x}`")
    if other:
        add(f"- **其他（{len(other)}）**：")
        for x in other:
            add(f"  - `{x}`")
    docs = sorted(set(all_docs) | {x for x in all_files if x.lower().endswith(".md")})
    add(f"- **文档（{len(docs)}）**：")
    for x in docs:
        add(f"  - `{x}`")
    add("")

    # 10 进度快照
    add("## 10. 进度快照（与 HTML 看板同源）")
    add("")
    add("| 流程 | 状态 | 加权完成度 | 子项 | 已完成 | 开放卡点 | 更新 |")
    add("|---|---|---|---|---|---|---|")
    for f in data["流程"]:
        add(f"| {f['名称']} | {f['状态']} | {f['完整度']}% | {f['子项数']} | "
            f"{f['已完成子项']} | {f['开放卡点数']} | {f.get('更新', '')} |")
    add("")
    add("---")
    add("")
    read_next = ((data.get("AI接手") or {}).get("延伸阅读") or [])
    if read_next:
        add("需要更细的执行级步骤时，读：")
        add("")
        for item in read_next:
            if isinstance(item, dict):
                add(f"- `{item.get('路径', '')}`：{item.get('说明', '')}")
            else:
                add(f"- `{item}`")
        add("")
    return "\n".join(L)


def main(argv):
    data_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_DATA
    out_path = Path(argv[2]) if len(argv) > 2 else DEFAULT_OUT
    if not data_path.exists():
        raise SystemExit(f"找不到数据文件：{data_path}")
    global PROJECT_ROOT
    raw = json.loads(data_path.read_text(encoding="utf-8"))
    PROJECT_ROOT = _project_root(raw)          # 允许数据文件用 "项目根" 显式指定
    data = enrich(raw)
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = HTML.replace("__TITLE__", data.get("标题", "项目流程看板")).replace("__DATA__", payload)
    out_path.write_text(html, encoding="utf-8")
    ai_path = out_path.with_name("AI交接.md")
    ai_path.write_text(render_ai_md(data), encoding="utf-8")
    st = data["统计"]
    print(f"已生成：{out_path}")
    print(f"已生成：{ai_path}")
    print(f"  {st['流程数']} 条流程 / {st['子项总数']} 个子项 / 整体完整度 {st['整体完整度']}%")
    print(f"  子项已完成 {st['子项已完成']} · 未开始 {st['子项未开始']}")
    print(f"  状态：可用 {st['可用']} · 部分可用 {st['部分可用']} · 待修 {st['待修']} · 阻塞 {st['阻塞']} · 未开始 {st['未开始']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
