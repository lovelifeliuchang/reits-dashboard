#!/usr/bin/env python3
"""把所有历史 JSON 生成交互式多日趋势 Dashboard，输出到 reits_reports/dashboard.html"""

import json
from pathlib import Path
from collections import defaultdict

OUTPUT_DIR = Path(__file__).parent / "reits_reports"

TYPE_ORDER = ["收益分配", "定期报告", "月度经营数据", "临时公告", "发售公告", "扩募并购", "持有人大会", "其他公告"]
TYPE_COLORS = {
    "收益分配": "#22c55e", "定期报告": "#3b82f6",
    "月度经营数据": "#f59e0b", "临时公告": "#f59e0b",
    "发售公告": "#a855f7", "扩募并购": "#6366f1",
    "持有人大会": "#ef4444", "其他公告": "#9ca3af",
}
ASSET_TYPES = {
    "transportation": "交通基础设施", "energy": "能源", "data_center": "数据中心",
    "logistics": "仓储物流", "commercial": "消费商业", "industrial_park": "产业园区",
    "residential": "租赁住房", "eco_environmental": "生态环保", "other": "其他",
}
ASSET_COLORS = {
    "transportation": "#0ea5e9", "energy": "#f97316", "data_center": "#8b5cf6",
    "logistics": "#06b6d4", "commercial": "#ec4899", "industrial_park": "#3b82f6",
    "residential": "#22c55e", "eco_environmental": "#10b981", "other": "#9ca3af",
}
LABEL_MAP = {
    "report_type":"报告类型","report_period":"报告期","revenue":"营业收入",
    "net_profit":"净利润","distributable_income":"可供分配金额",
    "distributable_per_unit":"每份可分配(元)","cash_flow":"经营现金流",
    "nav_per_unit":"基金净值(元)","occupancy_rate":"出租率(%)",
    "avg_rent":"平均租金","collection_rate":"收缴率(%)","top5_tenant_ratio":"前五大租户占比(%)",
    "units_rented":"在租套数","traffic_daily_volume":"日均通行量",
    "traffic_volume":"通行量","traffic_yoy":"通行量同比","traffic_qoq":"通行量环比",
    "toll_revenue":"通行费收入","power_generation":"发电量","grid_power":"上网电量",
    "utilization_hours":"利用小时数","power_price":"上网电价(元/度)",
    "power_generation_yoy":"发电量同比","equipment_availability":"设备可利用率(%)",
    "treatment_volume":"处理量","capacity_utilization":"产能利用率(%)",
    "treatment_yoy":"处理量同比","dividend_per_unit":"每份分红(元)",
    "total_dividend":"分红总额","distribution_ratio":"分配比例(%)",
    "dividend_yield_ann":"年化分红率(%)","record_date":"权益登记日",
    "ex_dividend_date":"除权除息日","payment_date":"派息日",
    "distribution_period":"分配所属期","offering_price":"发售价(元/份)",
    "offering_shares":"发行规模","asset_value":"底层资产估值",
    "cap_rate":"资本化率(%)","listing_date":"预计上市日",
    "transaction_price":"交易对价","new_project":"收购项目",
    "meeting_date":"会议日期","resolutions":"主要议案","brief":"摘要",
    "special_notes":"特殊事项",
}

def get_asset_type(name):
    name = name or ""
    if any(k in name for k in ("高速","广河","交控","铁建高速","沪杭甬","越秀高速","深高速","招商高速","交建高速")): return "transportation"
    if any(k in name for k in ("太阳能","清洁能源","新能源","绿能","能源建设","电建","蒙能","首钢绿能","华润燃气","燃气")): return "energy"
    if any(k in name for k in ("数据中心","润泽","铁塔")): return "data_center"
    if any(k in name for k in ("物流","仓储","普洛斯","顺丰","安博","京东仓储","宝湾","盐田港","深国际")): return "logistics"
    if any(k in name for k in ("商业","大悦城","印力","百联","物美","中海商业","绿发商业","华润商业","华威市场")): return "commercial"
    if any(k in name for k in ("产业园","科创","联东","中关村","北交所","临港","高新","光谷","和达高科","广开产园","南京产园","蛇口产园","张江","苏园")): return "industrial_park"
    if any(k in name for k in ("租赁住房","安居","有巢","宽庭","昌保","保障房")): return "residential"
    if any(k in name for k in ("水务","水利","污水","原水","首创","固废","生态")): return "eco_environmental"
    return "other"

def esc(s):
    return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def load_latest_t_signal() -> dict | None:
    """读取最新的 T期货信号 JSON，没有则返回 None"""
    files = sorted(OUTPUT_DIR.glob("t_signal_????????.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


def render_t_signal_card(sig: dict) -> str:
    """把 T信号 dict 渲染成 HTML card 字符串"""
    if sig is None:
        return ""

    signal_val = sig.get("signal", 0)
    if signal_val == 1:
        sig_color = "#16a34a"
        sig_bg    = "#dcfce7"
        sig_icon  = "▲"
        sig_text  = "做多"
        action_html = (f'<span style="color:#16a34a">持有多头　'
                       f'止损参考 <strong>{sig.get("stop_level", "—")}</strong></span>')
    else:
        sig_color = "#6b7280"
        sig_bg    = "#f3f4f6"
        sig_icon  = "⬜"
        sig_text  = "空仓观望"
        action_html = '<span style="color:#6b7280">空仓，等待做多信号</span>'

    gate_html = ('<span style="color:#16a34a">✅ 开放</span>' if sig.get("bull_gate") == 1
                 else '<span style="color:#ef4444">❌ 关闭</span>')

    factors = sig.get("factors", {})
    factor_rows = ""
    labels = {"macd": "收益率趋势", "boll": "布林带", "rsi": "RSI",
               "macro": "宏观2Y", "oi": "OI动量"}
    for key, label in labels.items():
        f = factors.get(key, {})
        sc = f.get("score", 0)
        wt = f.get("weight", 1)
        ct = f.get("contribution", 0)
        bar_w = min(int(ct / max(sig.get("long_score", 1), 1e-6) * 100), 100)
        factor_rows += f"""
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px;font-size:12px">
          <span style="width:72px;color:#6b7280">{label}</span>
          <span style="width:36px;text-align:right">{sc:.2f}</span>
          <span style="color:#9ca3af;width:28px;text-align:center">×{wt}</span>
          <div style="flex:1;background:#e5e7eb;border-radius:4px;height:8px">
            <div style="width:{bar_w}%;background:{sig_color};border-radius:4px;height:8px"></div>
          </div>
          <span style="width:34px;text-align:right;color:{sig_color};font-weight:600">{ct:.3f}</span>
        </div>"""

    score_pct = min(int(sig.get("long_score", 0) / max(sig.get("threshold", 1), 1e-6) * 100), 120)
    score_bar_w = min(score_pct, 100)
    score_color = sig_color if signal_val == 1 else "#9ca3af"

    return f"""
<div class="card" style="border-left:4px solid {sig_color};margin-bottom:16px">
  <h2 style="color:{sig_color}">📈 T期货策略信号　{esc(sig.get('date',''))}</h2>
  <div style="display:grid;grid-template-columns:auto 1fr;gap:12px 24px;align-items:start;margin-top:10px">
    <!-- 左侧：信号状态 -->
    <div style="background:{sig_bg};border-radius:10px;padding:14px 20px;min-width:160px;text-align:center">
      <div style="font-size:36px;font-weight:700;color:{sig_color}">{sig_icon}</div>
      <div style="font-size:18px;font-weight:700;color:{sig_color};margin-top:4px">{sig_text}</div>
      <div style="font-size:11px;color:#6b7280;margin-top:6px">
        触发 {esc(sig.get('trigger_date',''))}（持续{sig.get('hold_days',0)}天）
      </div>
      <div style="margin-top:8px;font-size:12px">{action_html}</div>
    </div>
    <!-- 右侧：详情 -->
    <div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:6px 16px;margin-bottom:10px;font-size:12px">
        <div><span style="color:#9ca3af">T收盘价　</span><strong>{sig.get('close','')}</strong></div>
        <div><span style="color:#9ca3af">10Y收益率　</span><strong>{sig.get('y10','')}%</strong>　<span style="color:#9ca3af">MA40={sig.get('y10_ma40','')}</span></div>
        <div><span style="color:#9ca3af">宏观门控　</span>{gate_html}</div>
        <div><span style="color:#9ca3af">ADX(14)　</span><strong>{sig.get('adx14','')}</strong></div>
      </div>
      <!-- 评分进度条 -->
      <div style="margin-bottom:8px;font-size:12px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
          <span style="color:#6b7280">多头评分</span>
          <strong style="color:{score_color}">{sig.get('long_score',0):.2f}</strong>
          <span style="color:#9ca3af">/ 阈值 {sig.get('threshold',1.0)}</span>
        </div>
        <div style="background:#e5e7eb;border-radius:4px;height:10px;position:relative">
          <div style="width:{score_bar_w}%;background:{score_color};border-radius:4px;height:10px"></div>
          <div style="position:absolute;top:0;left:{min(int(1/max(sig.get('threshold',1),1e-6)*100),100)}%;width:2px;height:10px;background:#ef4444"></div>
        </div>
      </div>
      <!-- 因子明细 -->
      {factor_rows}
    </div>
  </div>
</div>"""


def main():
    data_by_date = {}
    for f in sorted(OUTPUT_DIR.glob("reits_????????.json")):
        d = json.loads(f.read_text())
        data_by_date[f.stem.replace("reits_", "")] = d

    if not data_by_date:
        print("没有找到任何日报 JSON")
        return

    dates = sorted(data_by_date.keys())
    date_labels = [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in dates]

    daily_by_type = {t: [] for t in TYPE_ORDER}
    daily_total = []
    for date_str in dates:
        items = data_by_date[date_str]
        counts = defaultdict(int)
        for item in items:
            t = item["analysis"].get("type", "其他公告")
            counts[t] += 1
        daily_total.append(len(items))
        for t in TYPE_ORDER:
            daily_by_type[t].append(counts.get(t, 0))

    type_totals = {t: sum(daily_by_type[t]) for t in TYPE_ORDER}

    all_rows = []
    for date_str, items in data_by_date.items():
        for item in items:
            details = item["analysis"].get("details", {}) or {}
            asset_type = get_asset_type(item["name"])
            detail_fields = []
            for k, label in LABEL_MAP.items():
                v = details.get(k)
                if v and str(v) not in ("null", "None", ""):
                    detail_fields.append({"label": label, "value": str(v)})
            all_rows.append({
                "date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}",
                "date_str": date_str,
                "name": item["name"],
                "code": item["code"],
                "type": item["analysis"].get("type", "其他公告"),
                "asset_type": asset_type,
                "asset_label": ASSET_TYPES[asset_type],
                "title": item["title"],
                "summary": item["analysis"].get("one_line_summary") or "",
                "pdf": item.get("pdf_url") or "",
                "details": detail_fields,
            })
    all_rows.sort(key=lambda x: x["date"], reverse=True)

    reit_activity = defaultdict(lambda: {"count": 0, "types": defaultdict(int)})
    for row in all_rows:
        reit_activity[row["name"]]["count"] += 1
        reit_activity[row["name"]]["types"][row["type"]] += 1
    top_reits = sorted(reit_activity.items(), key=lambda x: -x[1]["count"])[:15]

    asset_type_counts = defaultdict(int)
    for row in all_rows:
        asset_type_counts[row["asset_type"]] += 1

    js_data = json.dumps({
        "dates": date_labels,
        "daily_by_type": daily_by_type,
        "type_totals": {t: v for t, v in type_totals.items() if v > 0},
        "asset_type_counts": dict(asset_type_counts),
        "rows": all_rows,
    }, ensure_ascii=False)

    t_sig = load_latest_t_signal()
    t_signal_card_html = render_t_signal_card(t_sig)

    reit_cards_html = ""
    for name, info in top_reits:
        tags = "　".join(f'<span style="color:{TYPE_COLORS.get(t,"#9ca3af")}">{t} {cnt}</span>' for t, cnt in info["types"].items())
        reit_cards_html += f"""<div class="reit-card" onclick="filterByReit('{esc(name)}')">
          <div style="font-weight:600">{esc(name)}</div>
          <div style="font-size:12px;color:#6b7280;margin-top:2px">共 {info["count"]} 条　{tags}</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>公募REITs趋势 Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f0f2f5;color:#111;font-size:14px}}
.wrap{{max-width:1140px;margin:0 auto;padding:24px 16px}}
.header{{background:linear-gradient(135deg,#1e3a8a,#2563eb);border-radius:16px;padding:24px 32px;margin-bottom:20px;color:#fff}}
.header h1{{font-size:22px;font-weight:700;margin-bottom:4px}}
.header p{{font-size:13px;opacity:.75}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-bottom:20px}}
.stat-card{{background:#fff;border-radius:12px;padding:16px 18px;box-shadow:0 1px 4px rgba(0,0,0,.07);border-top:3px solid var(--c)}}
.stat-card .num{{font-size:28px;font-weight:700;color:var(--c)}}
.stat-card .lbl{{font-size:12px;color:#6b7280;margin-top:3px}}
.card{{background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.07);margin-bottom:16px}}
.card h2{{font-size:15px;font-weight:700;margin-bottom:14px;color:#1e3a8a}}
.chart-grid{{display:grid;grid-template-columns:2fr 1fr 1fr;gap:16px;margin-bottom:16px}}
.chart-wrap{{position:relative;height:200px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:#f8fafc;font-weight:600;color:#374151;padding:9px 12px;text-align:left;border-bottom:2px solid #e5e7eb;white-space:nowrap;cursor:pointer;user-select:none}}
th:hover{{background:#e5e7eb}}
th .sort-icon{{margin-left:4px;color:#9ca3af;font-size:10px}}
td{{padding:8px 12px;border-bottom:1px solid #f1f5f9;vertical-align:top}}
tr.data-row:hover td{{background:#f0f7ff;cursor:pointer}}
tr.data-row.expanded td{{background:#eff6ff}}
tr.detail-row td{{padding:0;background:#f8fafc}}
.detail-inner{{padding:12px 16px;display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:6px 16px;border-top:2px solid #2563eb}}
.detail-item{{font-size:12px}}.detail-item .dl{{color:#9ca3af}}.detail-item .dv{{color:#111;font-weight:500}}
.badge{{display:inline-block;padding:2px 9px;border-radius:10px;font-size:11px;font-weight:600;color:#fff;white-space:nowrap}}
.pdf-btn{{font-size:11px;color:#6b7280;text-decoration:none;white-space:nowrap}}
.pdf-btn:hover{{color:#2563eb}}
.filter-row{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center}}
.filter-btn{{padding:4px 13px;border-radius:20px;border:1px solid #e5e7eb;background:#fff;font-size:12px;cursor:pointer;color:#374151;transition:.15s;white-space:nowrap}}
.filter-btn.active,.filter-btn:hover{{background:#2563eb;color:#fff;border-color:#2563eb}}
.filter-btn.asset.active{{background:var(--ac);border-color:var(--ac)}}
input[type=text]{{padding:6px 12px;border:1px solid #e5e7eb;border-radius:8px;font-size:13px;width:180px;outline:none}}
input[type=text]:focus{{border-color:#2563eb}}
.active-filters{{font-size:12px;color:#6b7280;margin-left:8px}}
.active-filters span{{background:#dbeafe;color:#1d4ed8;padding:2px 8px;border-radius:10px;margin-right:4px;cursor:pointer}}
.reit-card{{padding:10px 14px;background:#f8fafc;border-radius:8px;border-left:3px solid #2563eb;cursor:pointer;transition:.15s}}
.reit-card:hover{{background:#eff6ff;border-left-color:#1d4ed8}}
.reit-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}}
.no-results{{color:#9ca3af;text-align:center;padding:24px;font-size:13px}}
@media(max-width:700px){{.chart-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="wrap">
<div class="header">
  <h1>公募REITs趋势 Dashboard</h1>
  <p id="headerDesc">加载中...</p>
</div>
{t_signal_card_html}
<div class="stats">
  <div class="stat-card" style="--c:#3b82f6"><div class="num" id="statTotal">—</div><div class="lbl">总公告数</div></div>
  <div class="stat-card" style="--c:#22c55e"><div class="num" id="statDiv">—</div><div class="lbl">收益分配</div></div>
  <div class="stat-card" style="--c:#3b82f6"><div class="num" id="statPeriodic">—</div><div class="lbl">定期报告</div></div>
  <div class="stat-card" style="--c:#f59e0b"><div class="num" id="statOps">—</div><div class="lbl">经营/临时公告</div></div>
  <div class="stat-card" style="--c:#6366f1"><div class="num" id="statReits">—</div><div class="lbl">活跃REIT</div></div>
  <div class="stat-card" style="--c:#9ca3af"><div class="num" id="statFiltered">—</div><div class="lbl">当前筛选结果</div></div>
</div>
<div class="chart-grid">
  <div class="card">
    <h2>每日公告趋势 <span style="font-size:12px;color:#9ca3af;font-weight:400">（点柱子筛选该日）</span></h2>
    <div class="chart-wrap"><canvas id="dailyChart"></canvas></div>
  </div>
  <div class="card">
    <h2>公告类型 <span style="font-size:12px;color:#9ca3af;font-weight:400">（点击筛选）</span></h2>
    <div class="chart-wrap"><canvas id="typeChart"></canvas></div>
  </div>
  <div class="card">
    <h2>资产类型 <span style="font-size:12px;color:#9ca3af;font-weight:400">（点击筛选）</span></h2>
    <div class="chart-wrap"><canvas id="assetChart"></canvas></div>
  </div>
</div>
<div class="card">
  <h2>📑 公告明细</h2>
  <div class="filter-row">
    <input type="text" id="searchBox" placeholder="搜索名称/标题..." oninput="applyFilters()">
    <div id="activeFilters" class="active-filters"></div>
  </div>
  <div class="filter-row" id="typeFilters">
    <span style="font-size:12px;color:#6b7280;white-space:nowrap">公告类型：</span>
  </div>
  <div class="filter-row" id="assetFilters">
    <span style="font-size:12px;color:#6b7280;white-space:nowrap">资产类型：</span>
  </div>
  <div style="overflow-x:auto">
  <table>
    <thead><tr>
      <th onclick="sortBy('date')">日期 <span class="sort-icon" id="sort-date">↓</span></th>
      <th onclick="sortBy('type')">类型 <span class="sort-icon" id="sort-type">↕</span></th>
      <th onclick="sortBy('name')">REIT <span class="sort-icon" id="sort-name">↕</span></th>
      <th>公告标题</th><th>摘要</th><th>原文</th>
    </tr></thead>
    <tbody id="mainBody"></tbody>
  </table>
  </div>
  <div id="noResults" class="no-results" style="display:none">没有符合条件的公告</div>
</div>
<div class="card">
  <h2>🏆 活跃REIT排行 <span style="font-size:12px;color:#9ca3af;font-weight:400">（点击筛选）</span></h2>
  <div class="reit-grid">{reit_cards_html}</div>
</div>
<div style="text-align:center;color:#9ca3af;font-size:12px;margin:16px 0 8px">
  数据来源：巨潮资讯 · AKShare　|　更新时间：{date_labels[-1]}
</div>
</div>
<script>
const RAW = {js_data};
const TYPE_COLORS = {json.dumps(TYPE_COLORS, ensure_ascii=False)};
const ASSET_COLORS = {json.dumps(ASSET_COLORS, ensure_ascii=False)};
const ASSET_LABELS = {json.dumps(ASSET_TYPES, ensure_ascii=False)};
let fType='',fAsset='',fDate='',fReit='',fSearch='';
let sortKey='date',sortDir=1;
function updateStats(rows){{
  const reits=new Set(rows.map(r=>r.name));
  document.getElementById('statTotal').textContent=RAW.rows.length;
  document.getElementById('statDiv').textContent=RAW.rows.filter(r=>r.type==='收益分配').length;
  document.getElementById('statPeriodic').textContent=RAW.rows.filter(r=>r.type==='定期报告').length;
  document.getElementById('statOps').textContent=RAW.rows.filter(r=>r.type==='月度经营数据'||r.type==='临时公告').length;
  document.getElementById('statReits').textContent=new Set(RAW.rows.map(r=>r.name)).size;
  document.getElementById('statFiltered').textContent=rows.length;
  const d0=RAW.dates[0],d1=RAW.dates[RAW.dates.length-1];
  document.getElementById('headerDesc').textContent=`数据范围：${{d0}} ~ ${{d1}}　共 ${{RAW.dates.length}} 个交易日　${{RAW.rows.length}} 条公告`;
}}
const dailyChart=new Chart(document.getElementById('dailyChart').getContext('2d'),{{
  type:'bar',
  data:{{labels:RAW.dates,datasets:Object.keys(RAW.daily_by_type).filter(t=>RAW.daily_by_type[t].some(v=>v>0)).map(t=>({{'label':t,'data':RAW.daily_by_type[t],'backgroundColor':(TYPE_COLORS[t]||'#9ca3af')+'cc','borderColor':TYPE_COLORS[t]||'#9ca3af','borderWidth':1}})) }},
  options:{{responsive:true,maintainAspectRatio:false,
    onClick:(e,els)=>{{if(!els.length){{fDate='';applyFilters();return;}}const idx=els[0].index;const d=RAW.dates[idx];fDate=fDate===d?'':d;applyFilters();}},
    plugins:{{legend:{{position:'bottom',labels:{{font:{{size:10}},boxWidth:10}}}}}},
    scales:{{x:{{stacked:true,ticks:{{font:{{size:10}},maxRotation:45}}}},y:{{stacked:true,beginAtZero:true,ticks:{{stepSize:1}}}}}}
  }}
}});
const typeChart=new Chart(document.getElementById('typeChart').getContext('2d'),{{
  type:'doughnut',
  data:{{labels:Object.keys(RAW.type_totals),datasets:[{{data:Object.values(RAW.type_totals),backgroundColor:Object.keys(RAW.type_totals).map(t=>TYPE_COLORS[t]||'#9ca3af'),borderWidth:2}}]}},
  options:{{responsive:true,maintainAspectRatio:false,
    onClick:(e,els)=>{{if(!els.length){{fType='';applyFilters();return;}}const t=Object.keys(RAW.type_totals)[els[0].index];fType=fType===t?'':t;applyFilters();}},
    plugins:{{legend:{{position:'right',labels:{{font:{{size:11}},boxWidth:12}}}}}}
  }}
}});
const assetChart=new Chart(document.getElementById('assetChart').getContext('2d'),{{
  type:'doughnut',
  data:{{labels:Object.keys(RAW.asset_type_counts).map(k=>ASSET_LABELS[k]||k),datasets:[{{data:Object.values(RAW.asset_type_counts),backgroundColor:Object.keys(RAW.asset_type_counts).map(k=>ASSET_COLORS[k]||'#9ca3af'),borderWidth:2}}]}},
  options:{{responsive:true,maintainAspectRatio:false,
    onClick:(e,els)=>{{if(!els.length){{fAsset='';applyFilters();return;}}const k=Object.keys(RAW.asset_type_counts)[els[0].index];fAsset=fAsset===k?'':k;applyFilters();}},
    plugins:{{legend:{{position:'right',labels:{{font:{{size:11}},boxWidth:12}}}}}}
  }}
}});
function buildFilterBtns(){{
  const tf=document.getElementById('typeFilters');
  const b0=document.createElement('button');b0.className='filter-btn active';b0.textContent='全部';b0.onclick=()=>{{fType='';applyFilters();}};tf.appendChild(b0);
  Object.keys(RAW.type_totals).forEach(t=>{{const b=document.createElement('button');b.className='filter-btn';b.textContent=t;b.onclick=()=>{{fType=fType===t?'':t;applyFilters();}};tf.appendChild(b);}});
  const af=document.getElementById('assetFilters');
  const ab0=document.createElement('button');ab0.className='filter-btn active';ab0.textContent='全部';ab0.onclick=()=>{{fAsset='';applyFilters();}};af.appendChild(ab0);
  Object.keys(RAW.asset_type_counts).forEach(k=>{{const b=document.createElement('button');b.className='filter-btn asset';b.textContent=ASSET_LABELS[k]||k;b.style.setProperty('--ac',ASSET_COLORS[k]||'#9ca3af');b.onclick=()=>{{fAsset=fAsset===k?'':k;applyFilters();}};af.appendChild(b);}});
}}
function sortBy(key){{
  if(sortKey===key)sortDir*=-1;else{{sortKey=key;sortDir=1;}}
  ['date','type','name'].forEach(k=>{{document.getElementById('sort-'+k).textContent=k===key?(sortDir===1?'↓':'↑'):'↕';}});
  applyFilters();
}}
let expandedIdx=null;
function toggleExpand(idx){{expandedIdx=expandedIdx===idx?null:idx;renderTable(getFiltered());}}
function getFiltered(){{
  const q=(document.getElementById('searchBox').value||'').toLowerCase();
  return RAW.rows.filter(r=>{{
    if(fType&&r.type!==fType)return false;
    if(fAsset&&r.asset_type!==fAsset)return false;
    if(fDate&&r.date!==fDate)return false;
    if(fReit&&r.name!==fReit)return false;
    if(q&&!r.name.toLowerCase().includes(q)&&!r.title.toLowerCase().includes(q))return false;
    return true;
  }}).sort((a,b)=>{{let av=a[sortKey]||'',bv=b[sortKey]||'';return av<bv?sortDir:av>bv?-sortDir:0;}});
}}
function renderTable(rows){{
  const tbody=document.getElementById('mainBody');
  let html='';
  rows.forEach((r,i)=>{{
    const isExp=expandedIdx===i;
    const tc=TYPE_COLORS[r.type]||'#9ca3af';
    const ac=ASSET_COLORS[r.asset_type]||'#9ca3af';
    const pdfBtn=r.pdf?`<a class="pdf-btn" href="${{r.pdf}}" target="_blank">📄查看</a>`:'';
    const title=r.title.length>40?r.title.slice(0,40)+'…':r.title;
    const summary=r.summary.length>45?r.summary.slice(0,45)+'…':r.summary;
    html+=`<tr class="data-row${{isExp?' expanded':''}}" onclick="toggleExpand(${{i}})">
      <td style="white-space:nowrap">${{r.date}}</td>
      <td><span class="badge" style="background:${{tc}}">${{r.type}}</span></td>
      <td style="white-space:nowrap"><strong>${{r.name}}</strong><br>
        <span style="font-size:11px;color:#9ca3af">${{r.code}}</span>
        <span class="badge" style="background:${{ac}};font-size:10px;margin-left:4px">${{r.asset_label}}</span></td>
      <td style="max-width:280px;font-size:13px">${{title}}</td>
      <td style="max-width:220px;font-size:12px;color:#6b7280">${{summary}}</td>
      <td>${{pdfBtn}}</td></tr>`;
    if(isExp){{
      const fields=r.details.length>0?r.details.map(f=>`<div class="detail-item"><span class="dl">${{f.label}}：</span><span class="dv">${{f.value}}</span></div>`).join(''):'<div style="color:#9ca3af;font-size:12px">暂无提取到的结构化字段</div>';
      html+=`<tr class="detail-row"><td colspan="6"><div class="detail-inner">${{fields}}</div></td></tr>`;
    }}
  }});
  tbody.innerHTML=html;
  document.getElementById('noResults').style.display=rows.length?'none':'block';
}}
function updateFilterBtns(){{
  document.querySelectorAll('#typeFilters .filter-btn').forEach((b,i)=>{{
    if(i===0)b.classList.toggle('active',!fType);
    else{{const t=Object.keys(RAW.type_totals)[i-1];b.classList.toggle('active',fType===t);}}
  }});
  document.querySelectorAll('#assetFilters .filter-btn').forEach((b,i)=>{{
    if(i===0)b.classList.toggle('active',!fAsset);
    else{{const k=Object.keys(RAW.asset_type_counts)[i-1];b.classList.toggle('active',fAsset===k);}}
  }});
  const tags=[];
  if(fDate)tags.push(`日期：${{fDate}} <span onclick="fDate='';applyFilters()">×</span>`);
  if(fType)tags.push(`类型：${{fType}} <span onclick="fType='';applyFilters()">×</span>`);
  if(fAsset)tags.push(`资产：${{ASSET_LABELS[fAsset]||fAsset}} <span onclick="fAsset='';applyFilters()">×</span>`);
  if(fReit)tags.push(`REIT：${{fReit}} <span onclick="fReit='';applyFilters()">×</span>`);
  document.getElementById('activeFilters').innerHTML=tags.map(t=>`<span>${{t}}</span>`).join('');
}}
function applyFilters(){{expandedIdx=null;const rows=getFiltered();renderTable(rows);updateStats(rows);updateFilterBtns();}}
function filterByReit(name){{fReit=fReit===name?'':name;applyFilters();document.getElementById('mainBody').closest('.card').scrollIntoView({{behavior:'smooth'}});}}
buildFilterBtns();
applyFilters();
</script>
</body>
</html>"""

    out = OUTPUT_DIR / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    print(f"Dashboard 已生成：{out.resolve()}")

if __name__ == "__main__":
    main()
