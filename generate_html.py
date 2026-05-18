#!/usr/bin/env python3
"""把 reits_YYYYMMDD.json 生成一份好看的 HTML 报告"""

import json, sys
from pathlib import Path

OUTPUT_DIR = Path("reits_reports")

def json_to_html(date_str: str) -> Path:
    json_file = OUTPUT_DIR / f"reits_{date_str}.json"
    if not json_file.exists():
        print(f"找不到 {json_file}，请先运行 python3 reits_daily.py {date_str}")
        sys.exit(1)

    data = json.loads(json_file.read_text(encoding="utf-8"))
    date_display = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

    TYPE_COLOR = {
        "分红公告":     "#22c55e",
        "临时业绩公告": "#f59e0b",
        "定期财务报告": "#3b82f6",
        "其他公告":     "#9ca3af",
    }
    LABEL_MAP = {
        "dividend_per_unit":      "每份分红（元）",
        "dividend_yield_ann":     "年化分红率（%）",
        "record_date":            "权益登记日",
        "ex_dividend_date":       "除权除息日",
        "payment_date":           "现金红利发放日",
        "distribution_period":    "分配所属期",
        "report_type":            "报告类型",
        "report_period":          "报告期",
        "revenue":                "营业收入",
        "net_profit":             "净利润",
        "distributable_income":   "可供分配金额",
        "distributable_per_unit": "每份可供分配（元）",
        "nav_per_unit":           "基金净值（元）",
        "occupancy_rate":         "出租率（%）",
        "special_notes":          "特殊事项",
        "brief":                  "公告摘要",
    }

    # 按类型分组统计
    counts = {}
    for r in data:
        t = r["analysis"].get("type", "其他")
        counts[t] = counts.get(t, 0) + 1

    def make_badge(ann_type):
        color = TYPE_COLOR.get(ann_type, "#9ca3af")
        return f'<span style="background:{color};color:#fff;padding:2px 10px;border-radius:12px;font-size:13px;font-weight:600">{ann_type}</span>'

    def make_card(item):
        a = item["analysis"]
        ann_type = a.get("type", "其他公告")
        details = a.get("details") or {}
        color = TYPE_COLOR.get(ann_type, "#9ca3af")

        rows = ""
        for key, label in LABEL_MAP.items():
            val = details.get(key)
            if val and str(val) not in ("null", "None", ""):
                # 高亮重要字段
                highlight = key in ("dividend_per_unit", "distributable_per_unit",
                                    "record_date", "ex_dividend_date", "occupancy_rate")
                val_style = "font-weight:600;color:#111" if highlight else "color:#374151"
                rows += f"""
                <tr>
                  <td style="padding:6px 12px;color:#6b7280;white-space:nowrap;font-size:13px">{label}</td>
                  <td style="padding:6px 12px;{val_style};font-size:14px">{val}</td>
                </tr>"""

        table = f"""<table style="width:100%;border-collapse:collapse;margin-top:8px">
            <tbody>{rows}</tbody></table>""" if rows else ""

        pdf_link = f'<a href="{item["pdf_url"]}" target="_blank" style="font-size:12px;color:#6b7280;text-decoration:none">📄 查看原文PDF</a>' if item.get("pdf_url") else ""

        return f"""
        <div style="background:#fff;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.08);
                    padding:18px 22px;margin-bottom:14px;border-left:4px solid {color}">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
            {make_badge(ann_type)}
            <span style="font-weight:700;font-size:15px">{item['name']}</span>
            <span style="color:#9ca3af;font-size:13px">({item['code']})</span>
            <span style="margin-left:auto">{pdf_link}</span>
          </div>
          <div style="color:#374151;font-size:13px;margin-bottom:4px">{item['title']}</div>
          {table}
        </div>"""

    # 统计栏
    stat_cards = ""
    for t, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        color = TYPE_COLOR.get(t, "#9ca3af")
        stat_cards += f"""
        <div style="background:#fff;border-radius:10px;padding:14px 20px;
                    box-shadow:0 1px 3px rgba(0,0,0,.07);border-top:3px solid {color}">
          <div style="font-size:28px;font-weight:700;color:{color}">{cnt}</div>
          <div style="font-size:13px;color:#6b7280;margin-top:2px">{t}</div>
        </div>"""

    # 按类型分组渲染卡片
    sections = ""
    type_order = ["分红公告", "临时业绩公告", "定期财务报告", "其他公告"]
    grouped = {t: [] for t in type_order}
    for item in data:
        t = item["analysis"].get("type", "其他公告")
        grouped.setdefault(t, []).append(item)

    for t in type_order:
        items = grouped.get(t, [])
        if not items:
            continue
        color = TYPE_COLOR.get(t, "#9ca3af")
        cards = "".join(make_card(i) for i in items)
        sections += f"""
        <div style="margin-bottom:32px">
          <h2 style="font-size:18px;font-weight:700;color:{color};margin-bottom:14px;
                     border-bottom:2px solid {color};padding-bottom:6px">
            {t} <span style="font-size:14px;font-weight:400;color:#9ca3af">（{len(items)} 条）</span>
          </h2>
          {cards}
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>公募REITs日报 {date_display}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
            background: #f3f4f6; color: #111; }}
  </style>
</head>
<body>
  <div style="max-width:860px;margin:0 auto;padding:32px 16px">
    <!-- 标题 -->
    <div style="background:linear-gradient(135deg,#1e40af,#3b82f6);border-radius:14px;
                padding:28px 32px;margin-bottom:24px;color:#fff">
      <div style="font-size:13px;opacity:.8;margin-bottom:4px">公募REITs日报</div>
      <div style="font-size:28px;font-weight:700">{date_display}</div>
      <div style="font-size:14px;opacity:.7;margin-top:6px">共 {len(data)} 条公告</div>
    </div>

    <!-- 统计卡片 -->
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
                gap:12px;margin-bottom:28px">
      {stat_cards}
    </div>

    <!-- 公告列表 -->
    {sections}

    <div style="text-align:center;color:#9ca3af;font-size:12px;margin-top:16px">
      数据来源：巨潮资讯 · AKShare &nbsp;|&nbsp; 生成时间：{date_display}
    </div>
  </div>
</body>
</html>"""

    out_path = OUTPUT_DIR / f"reits_{date_str}.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    date_str = sys.argv[1] if len(sys.argv) > 1 else None
    if not date_str:
        # 找最新的 json
        jsons = sorted(OUTPUT_DIR.glob("reits_????????.json"), reverse=True)
        if not jsons:
            print("没有找到任何日报 JSON，请先运行 reits_daily.py")
            sys.exit(1)
        date_str = jsons[0].stem.replace("reits_", "")
    out = json_to_html(date_str)
    print(f"HTML 报告已生成：{out.resolve()}")
    # 自动用浏览器打开
    import subprocess
    subprocess.run(["open", str(out.resolve())])
