#!/usr/bin/env python3
"""
把当日REITs日报通过飞书机器人"司小亮"以交互卡片形式发送到"小绵羊之家"群
用法：python3 send_feishu.py [YYYYMMDD]
"""

import json
import sys
import requests
from datetime import date
from pathlib import Path

OUTPUT_DIR = Path("reits_reports")
APP_ID     = "cli_a92ce6680d385cc9"
APP_SECRET = "tRmlrMm8M9Mn9y6YKsiXogyAIaAy2ojO"
CHAT_ID    = "oc_bc1e04ea52b9ca6a712c93a3752fe856"

FEISHU_HOST = "https://open.feishu.cn"

TYPE_EMOJI = {
    "收益分配":     "💰",
    "定期报告":     "📋",
    "临时公告":     "📊",
    "月度经营数据": "📈",
    "发售公告":     "🆕",
    "扩募并购":     "🏗",
    "持有人大会":   "🗳",
    "其他公告":     "📌",
}
TYPE_COLOR = {
    "收益分配":     "lime",
    "定期报告":     "wathet",
    "临时公告":     "yellow",
    "月度经营数据": "yellow",
    "发售公告":     "purple",
    "扩募并购":     "indigo",
    "持有人大会":   "carmine",
    "其他公告":     "grey",
}
LABEL_MAP = {
    # 收益分配
    "dividend_per_unit":      "每份分红",
    "total_dividend":         "分红总额",
    "distribution_ratio":     "分配比例",
    "dividend_yield_ann":     "年化分红率",
    "ex_dividend_date":       "除息日",
    "payment_date":           "派息日",
    "record_date":            "权益登记日",
    "distribution_period":    "分配期间",
    "cumulative_times":       "累计分红",
    # 通用财务
    "report_period":          "报告期",
    "revenue":                "营业收入",
    "net_profit":             "净利润",
    "distributable_income":   "可供分配",
    "distributable_per_unit": "每份可分配",
    "cash_flow":              "经营现金流",
    "nav_per_unit":           "基金净值",
    "special_notes":          "特殊事项",
    # 产业园/仓储/商业/数据中心
    "occupancy_rate":         "出租率",
    "avg_rent":               "平均租金",
    "collection_rate":        "收缴率",
    "top5_tenant_ratio":      "前五大租户占比",
    # 住宅
    "units_rented":           "在租套数",
    # 交通
    "traffic_daily_volume":   "日均通行量",
    "traffic_volume":         "通行量",
    "traffic_yoy":            "通行量同比",
    "traffic_qoq":            "通行量环比",
    "toll_revenue":           "通行费收入",
    "free_passage_impact":    "免费通行影响",
    # 能源
    "power_generation":       "发电量",
    "grid_power":             "上网电量",
    "utilization_hours":      "利用小时数",
    "power_price":            "上网电价(元/度)",
    "power_generation_yoy":   "发电量同比",
    "power_price_change":     "电价同比",
    "equipment_availability": "设备可利用率",
    # 生态环保
    "treatment_volume":       "处理量",
    "unit_price":             "处理单价",
    "capacity_utilization":   "产能利用率",
    "treatment_yoy":          "处理量同比",
    # 发售
    "offering_price":         "发售价(元/份)",
    "offering_shares":        "发行规模",
    "strategic_shares":       "战略配售",
    "institutional_shares":   "网下配售",
    "fee_rate":               "认购费率",
    "asset_value":            "底层资产估值",
    "cap_rate":               "资本化率",
    "subscription_date":      "认购日期",
    "listing_date":           "预计上市日",
    # 扩募并购
    "transaction_price":      "交易对价",
    "expansion_shares":       "扩募份额",
    "new_project":            "收购项目",
    # 持有人大会
    "meeting_date":           "会议日期",
    "resolutions":            "主要议案",
    # 通用
    "brief":                  "摘要",
}
PRIORITY_FIELDS = {
    "收益分配":     ["dividend_per_unit", "total_dividend", "distribution_ratio",
                     "dividend_yield_ann", "ex_dividend_date", "payment_date",
                     "record_date", "distribution_period", "cumulative_times"],
    "定期报告":     ["report_period", "revenue", "net_profit", "distributable_income",
                     "distributable_per_unit", "cash_flow", "nav_per_unit",
                     "occupancy_rate", "avg_rent", "collection_rate", "top5_tenant_ratio",
                     "units_rented",
                     "traffic_daily_volume", "traffic_volume", "traffic_yoy", "traffic_qoq", "toll_revenue",
                     "power_generation", "grid_power", "utilization_hours",
                     "power_price", "power_generation_yoy", "power_price_change", "equipment_availability",
                     "treatment_volume", "unit_price", "capacity_utilization", "treatment_yoy"],
    "临时公告":     ["report_period", "revenue", "net_profit", "distributable_income",
                     "distributable_per_unit",
                     "occupancy_rate", "avg_rent", "units_rented",
                     "traffic_daily_volume", "traffic_volume", "traffic_yoy", "traffic_qoq",
                     "power_generation", "power_price", "power_generation_yoy",
                     "treatment_volume", "capacity_utilization",
                     "special_notes"],
    "月度经营数据": ["report_period",
                     "occupancy_rate", "avg_rent", "units_rented",
                     "traffic_daily_volume", "traffic_volume", "traffic_yoy", "traffic_qoq",
                     "power_generation", "power_price", "power_generation_yoy",
                     "treatment_volume", "capacity_utilization"],
    "发售公告":     ["offering_price", "offering_shares", "strategic_shares",
                     "institutional_shares", "fee_rate", "asset_value", "cap_rate",
                     "subscription_date", "listing_date", "brief"],
    "扩募并购":     ["transaction_price", "expansion_shares", "new_project", "brief"],
    "持有人大会":   ["meeting_date", "resolutions", "brief"],
    "其他公告":     ["brief"],
}


def load_t_signal(date_str: str) -> dict | None:
    """读取对应日期（YYYYMMDD）的 T期货信号 JSON，没有则返回最近一份"""
    p = OUTPUT_DIR / f"t_signal_{date_str}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    # 找最近一份
    files = sorted(OUTPUT_DIR.glob("t_signal_????????.json"))
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def build_t_signal_elements(sig: dict) -> list:
    """把 T信号 dict 转成飞书卡片 elements 列表"""
    if not sig:
        return []

    signal_val = sig.get("signal", 0)
    if signal_val == 1:
        sig_color   = "green"
        sig_emoji   = "▲"
        sig_text    = "做多"
        stop_lv     = sig.get("stop_level")
        action_text = f"建议：持有多头　止损参考 {stop_lv}" if stop_lv else "建议：持有多头"
    else:
        sig_color   = "grey"
        sig_emoji   = "⬜"
        sig_text    = "空仓观望"
        action_text = "建议：空仓，等待做多信号"

    gate_text = "✅ 开放" if sig.get("bull_gate") == 1 else "❌ 关闭"
    factors   = sig.get("factors", {})
    f_labels  = {"macd": "收益率趋势", "boll": "布林带", "rsi": "RSI",
                 "macro": "宏观2Y",    "oi":   "OI动量"}

    factor_lines = []
    for key, label in f_labels.items():
        f   = factors.get(key, {})
        sc  = f.get("score", 0)
        wt  = f.get("weight", 1)
        ct  = f.get("contribution", 0)
        factor_lines.append(
            f"<font color='grey'>{label}</font> {sc:.2f}×{wt} = **{ct:.3f}**"
        )

    # 第1行：信号 + 评分
    line1 = (f"**<font color='{sig_color}'>{sig_emoji} {sig_text}</font>**　　"
             f"多头评分 **{sig.get('long_score', 0):.2f}** / 阈值{sig.get('threshold', 1.0)}")
    # 第2行：触发 + 操作建议
    line2 = (f"<font color='grey'>触发</font> {sig.get('trigger_date','')} "
             f"（持续{sig.get('hold_days', 0)}天）　{action_text}")
    # 第3行：价格 + 收益率
    line3 = (f"<font color='grey'>T收盘</font> {sig.get('close','')}　　"
             f"<font color='grey'>10Y</font> {sig.get('y10','')}%"
             f"（MA40={sig.get('y10_ma40','')}）　"
             f"<font color='grey'>宏观门控</font> {gate_text}　"
             f"<font color='grey'>ADX</font> {sig.get('adx14','')}")

    content = (line1 + "\n" + line2 + "\n" + line3 +
               "\n" + "　".join(factor_lines[:3]) +
               "\n" + "　".join(factor_lines[3:]))

    elements = [
        {"tag": "div", "text": {
            "tag": "lark_md",
            "content": f"**<font color='{sig_color}'>📈 T期货策略信号　{sig.get('date', '')}</font>**",
        }},
        {"tag": "column_set",
         "flex_mode": "none",
         "background_style": "grey",
         "columns": [{"tag": "column", "width": "weighted", "weight": 1,
                      "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": content}}]}]},
        {"tag": "hr"},
    ]
    return elements


def get_token() -> str:
    """获取飞书 tenant_access_token"""
    resp = requests.post(
        f"{FEISHU_HOST}/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET},
        timeout=10,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取 token 失败: {data}")
    return data["tenant_access_token"]


def send_card(card: dict, token: str) -> bool:
    """发送交互卡片到群"""
    resp = requests.post(
        f"{FEISHU_HOST}/open-apis/im/v1/messages",
        params={"receive_id_type": "chat_id"},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "receive_id": CHAT_ID,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        },
        timeout=15,
    )
    data = resp.json()
    if data.get("code") == 0:
        print(f"✓ 卡片已发送，message_id: {data['data']['message_id']}")
        return True
    else:
        print(f"✗ 发送失败: {data}")
        return False


def _render_fields(details: dict, fields: list[str]) -> list[str]:
    """
    把字段列表渲染成若干行文本。
    - brief 单独占一行
    - 其余字段每两个拼一行，label 用灰色小字，value 正常字体
    """
    lines = []
    buf = []
    for key in fields:
        val = details.get(key)
        if not val or str(val) in ("null", "None", ""):
            continue
        label = LABEL_MAP.get(key, key)
        unit  = "%" if key == "occupancy_rate" else ""
        if key == "brief":
            if buf:
                lines.append("　　".join(buf)); buf = []
            brief_val = str(val)[:90] + ("…" if len(str(val)) > 90 else "")
            lines.append(f"<font color='grey'>{brief_val}</font>")
        else:
            buf.append(f"<font color='grey'>{label}</font> {val}{unit}")
            if len(buf) == 2:
                lines.append("　　".join(buf)); buf = []
    if buf:
        lines.append("　　".join(buf))
    return lines


def build_card(data: list[dict], date_display: str, t_sig: dict = None) -> dict:
    """构建飞书交互卡片 JSON"""
    counts = {}
    for r in data:
        t = r["analysis"].get("type", "其他")
        counts[t] = counts.get(t, 0) + 1

    total = len(data)
    type_order = ["收益分配", "定期报告", "月度经营数据", "临时公告", "发售公告", "扩募并购", "持有人大会", "其他公告"]
    elements = build_t_signal_elements(t_sig) if t_sig else []

    # ── 统计概览：单行文字，简洁 ──
    stat_parts = []
    for t in type_order:
        cnt = counts.get(t, 0)
        if cnt == 0:
            continue
        emoji = TYPE_EMOJI.get(t, "📌")
        stat_parts.append(f"{emoji} {t} {cnt}条")
    if stat_parts:
        elements.append({"tag": "div", "text": {
            "tag": "lark_md",
            "content": "<font color='grey'>" + "　　".join(stat_parts) + "</font>",
        }})
        elements.append({"tag": "hr"})

    # ── 按类型分组渲染 ──
    grouped = {t: [] for t in type_order}
    for item in data:
        t = item["analysis"].get("type", "其他公告")
        grouped.setdefault(t, []).append(item)

    for ann_type in type_order:
        items = grouped.get(ann_type, [])
        if not items:
            continue

        emoji = TYPE_EMOJI.get(ann_type, "📌")
        color = TYPE_COLOR.get(ann_type, "grey")

        # 分类标题
        elements.append({"tag": "div", "text": {
            "tag": "lark_md",
            "content": f"**<font color='{color}'>{emoji} {ann_type}（{len(items)}条）</font>**",
        }})

        for item in items:
            details = item["analysis"].get("details") or {}
            fields  = PRIORITY_FIELDS.get(ann_type, [])
            pdf_url = item.get("pdf_url", "")

            # 标题行：REIT名称（代码）
            name_line = f"**{item['name']}**　<font color='grey'>{item['code']}</font>"
            # 公告标题：截短，灰色
            title_short = item["title"][:50] + ("…" if len(item["title"]) > 50 else "")
            title_line  = f"<font color='grey'>{title_short}</font>"
            # 字段行
            field_lines = _render_fields(details, fields)

            content = name_line + "\n" + title_line
            if field_lines:
                content += "\n" + "\n".join(field_lines)

            inner = {"tag": "div", "text": {"tag": "lark_md", "content": content}}
            if pdf_url:
                inner["extra"] = {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "原文"},
                    "type": "default",
                    "url": pdf_url,
                }

            elements.append({
                "tag": "column_set",
                "flex_mode": "none",
                "background_style": "grey",
                "columns": [{"tag": "column", "width": "weighted", "weight": 1, "elements": [inner]}],
            })

        elements.append({"tag": "hr"})

    if elements and elements[-1].get("tag") == "hr":
        elements.pop()

    elements.append({"tag": "div", "text": {
        "tag": "lark_md",
        "content": f"<font color='grey'>数据来源：巨潮资讯 · AKShare　|　{date_display}</font>",
    }})

    elements.append({"tag": "div", "text": {
        "tag": "lark_md",
        "content": "[📊 查看完整趋势 Dashboard](https://lovelifeliuchang.github.io/reits-dashboard/dashboard.html)",
    }})

    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"公募REITs日报　{date_display}　共{total}条公告"},
            "template": "blue",
        },
        "body": {"elements": elements},
    }


def main(date_str: str = None, force: bool = False):
    if date_str is None:
        date_str = date.today().strftime("%Y%m%d")
    date_display = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

    # 防重复发送：已发送则跳过（除非传 --force）
    sent_flag = OUTPUT_DIR / f".sent_{date_str}"
    if sent_flag.exists() and not force:
        print(f"{date_display} 今日已发送过，跳过（如需重发请加 --force）")
        return

    json_file = OUTPUT_DIR / f"reits_{date_str}.json"
    if not json_file.exists():
        print(f"找不到 {json_file}，先运行 python3 reits_daily.py {date_str}")
        sys.exit(1)

    data = json.loads(json_file.read_text(encoding="utf-8"))
    if not data:
        print(f"{date_display} 无公告数据，不发送")
        return

    print(f"准备发送 {date_display} 日报卡片，共 {len(data)} 条公告...")
    t_sig = load_t_signal(date_str)
    if t_sig:
        print(f"  T信号：{t_sig.get('signal_label', '')}  评分：{t_sig.get('long_score', 0)}")
    token = get_token()
    card  = build_card(data, date_display, t_sig=t_sig)
    if send_card(card, token):
        sent_flag.touch()  # 发送成功后打标记


if __name__ == "__main__":
    arg   = sys.argv[1] if len(sys.argv) > 1 else None
    force = "--force" in sys.argv
    main(arg, force=force)
