#!/usr/bin/env python3
"""
公募REITs日报系统
每日自动下载并分析中国公募REITs公告（覆盖上交所+深交所全量标的）

数据源（全部免费，无需任何API Key）：
  - 标的列表：AKShare reits_realtime_em()
  - 公告列表：东方财富（eastmoney.com）—— 批量查询，覆盖上交所+深交所
  - PDF下载 ：pdf.dfcfw.com
  - 信息提取：正则规则

使用方式：
  python3 reits_daily.py              # 分析今天
  python3 reits_daily.py 20260428     # 分析指定日期 (YYYYMMDD)
"""

import re
import sys
import json
import time
import requests
import akshare as ak
import pdfplumber
import pandas as pd

from datetime import date
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich import box

# ──────────────────────────────────────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────────────────────────────────────
PDF_MAX_CHARS = 20_000
OUTPUT_DIR    = Path("reits_reports")
EM_ANN_URL    = "https://np-anotice-stock.eastmoney.com/api/security/ann"
DFCFW_PDF     = "https://pdf.dfcfw.com/pdf/H2_{art_code}_1.PDF"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://data.eastmoney.com/",
}

console = Console()


# ──────────────────────────────────────────────────────────────────────────────
# 1. 获取全量公募REITs列表
# ──────────────────────────────────────────────────────────────────────────────
def get_all_reits() -> dict[str, str]:
    """返回 {6位代码: 简称}"""
    try:
        df = ak.reits_realtime_em()
        result = dict(zip(df["代码"].astype(str).str.zfill(6), df["名称"]))
        console.log(f"[green]AKShare 返回 {len(result)} 只公募REITs[/green]")
        return result
    except Exception as e:
        console.log(f"[yellow]AKShare 失败（{e}），使用内置列表[/yellow]")
        return _STATIC_REITS


_STATIC_REITS: dict[str, str] = {
    "508000": "华安张江产业园REIT",    "508002": "华安百联消费REIT",
    "508003": "中金联东科创REIT",      "508006": "富国首创水务REIT",
    "508009": "建信中关村REIT",        "508011": "嘉实物美消费REIT",
    "508018": "华夏中国交建高速REIT",  "508021": "国泰君安城投宽庭REIT",
    "508027": "东吴苏园产业REIT",      "508055": "汇添富上海地产租赁REIT",
    "508056": "中金普洛斯REIT",        "508058": "国泰君安东久新经济REIT",
    "508068": "华夏合肥高新REIT",      "508077": "华夏基金华润有巢REIT",
    "508088": "招商蛇口产业园REIT",    "508098": "华泰江苏交控REIT",
    "508099": "国金中国铁建高速REIT",  "508100": "建信华润有巢租赁REIT",
    "508116": "国泰君安临港创新产业园REIT","508117": "华夏大悦城商业REIT",
    "508119": "嘉实京东仓储物流REIT",  "508120": "华夏北交所产业园REIT",
    "508126": "中金湖北科投光谷REIT",  "508132": "华夏华润燃气REIT",
    "508136": "国泰君安国资资本科技REIT","508139": "中银保险太阳能REIT",
    "508155": "申万菱信深高速REIT",    "508159": "建信中国铁塔REIT",
    "508168": "华夏越秀高速REIT",      "508169": "易方达广开城投REIT",
    "508170": "国泰君安南京产园REIT",  "508177": "银华金租租赁住房REIT",
    "508183": "华夏沪杭甬高速REIT",    "508188": "嘉实中国电建新能源REIT",
    "508192": "银华中国能源建设新能源REIT","508195": "中银中金厦门安居REIT",
    "180101": "博时蛇口产园REIT",      "180102": "华夏合肥高新REIT",
    "180103": "华夏和达高科REIT",      "180105": "易方达广开产园REIT",
    "180106": "广发成都高投产业园REIT", "180201": "平安广州广河REIT",
    "180202": "华夏越秀高速REIT",      "180203": "招商高速公路REIT",
    "180301": "红土盐田港REIT",        "180302": "华夏深国际REIT",
    "180303": "华泰宝湾物流REIT",      "180305": "南方顺丰物流REIT",
    "180306": "华夏安博仓储REIT",      "180401": "鹏华深圳能源REIT",
    "180402": "工银蒙能清洁能源REIT",  "180502": "招商蛇口租赁住房REIT",
    "180503": "中航北京昌保租赁REIT",  "180601": "华夏华润商业REIT",
    "180602": "中金印力消费REIT",      "180603": "华夏大悦城商业REIT",
    "180605": "易方达华威市场REIT",    "180606": "中金中国绿发商业REIT",
    "180607": "华夏中海商业REIT",      "180801": "中航首钢绿能REIT",
    "180901": "南方润泽科技数据中心REIT",
}


# ──────────────────────────────────────────────────────────────────────────────
# 2. 从东方财富获取当日公告列表（覆盖上交所+深交所全量REITs）
# ──────────────────────────────────────────────────────────────────────────────

def fetch_announcements(target_date: str, reit_codes: set[str]) -> list[dict]:
    """target_date 格式 YYYY-MM-DD，批量查询所有REIT代码，不漏任何公告"""
    codes_str = ",".join(sorted(reit_codes))
    anns = []
    page = 1
    while True:
        try:
            r = requests.get(
                EM_ANN_URL,
                params={
                    "sr": -1,
                    "page_size": 200,
                    "page_index": page,
                    "ann_type": "Fund",
                    "client_source": "web",
                    "stock_list": codes_str,
                    "begin_time": target_date,
                    "end_time": target_date,
                },
                headers=HEADERS, timeout=20,
            )
            data  = r.json()
            items = data.get("data", {}).get("list") or []
            total = data.get("data", {}).get("total_hits") or 0
        except Exception as e:
            console.log(f"[red]东方财富第{page}页错误: {e}[/red]")
            break

        for item in items:
            code_info = item.get("codes", [{}])[0]
            art_code  = item.get("art_code", "")
            anns.append({
                "code":     code_info.get("stock_code", ""),
                "name":     code_info.get("short_name", ""),
                "title":    item.get("title", ""),
                "ann_id":   art_code,
                "pdf_url":  DFCFW_PDF.format(art_code=art_code),
            })

        if page * 200 >= total or not items:
            break
        page += 1
        time.sleep(0.3)

    return anns


# ──────────────────────────────────────────────────────────────────────────────
# 3. 下载PDF并提取文本
# ──────────────────────────────────────────────────────────────────────────────
def get_pdf_text(pdf_url: str, save_dir: Path, ann_id: str) -> str:
    if not pdf_url:
        return ""
    pdf_path = save_dir / f"{ann_id}.pdf"

    if not pdf_path.exists():
        try:
            r = requests.get(pdf_url, headers=HEADERS, timeout=40)
            r.raise_for_status()
            if r.content[:4] != b"%PDF":
                return ""
            pdf_path.write_bytes(r.content)
        except Exception as e:
            console.log(f"  [dim]PDF下载失败: {e}[/dim]")
            return ""

    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages[:40]]
        return "\n".join(pages)[:PDF_MAX_CHARS]
    except Exception as e:
        console.log(f"  [dim]PDF解析失败: {e}[/dim]")
        return ""


# ──────────────────────────────────────────────────────────────────────────────
# 4. 分类：公告类型 + 资产类型
# ──────────────────────────────────────────────────────────────────────────────

def classify_type(title: str) -> str:
    """按优先级从高到低识别公告类型"""
    t = title
    # P1: 定期报告（年报/半年报/季报）
    if any(k in t for k in ("年度报告", "半年度报告", "季度报告", "年报", "半年报")):
        return "定期报告"
    # P2: 收益分配（分红）
    if any(k in t for k in ("分红", "收益分配", "派息", "现金红利", "权益登记", "除权除息")):
        return "收益分配"
    # P3: 发售公告（新上市/扩募发行）
    if any(k in t for k in ("发售", "募集", "认购", "询价", "上市公告书", "网下发行", "基金合同生效", "发行公告")):
        return "发售公告"
    # P4: 月度经营数据
    if any(k in t for k in ("月度运营数据", "月度经营", "主要运营数据", "月度数据")):
        return "月度经营数据"
    # P5: 扩募并购
    if any(k in t for k in ("扩募", "购入基础设施", "重大资产重组", "购买资产", "收购基础设施")):
        return "扩募并购"
    # P6: 持有人大会
    if any(k in t for k in ("持有人大会", "基金份额持有人大会", "持有人会议")):
        return "持有人大会"
    # P7: 临时公告（经营情况通报、业绩预告等）
    if any(k in t for k in ("经营情况", "运营情况", "业绩快报", "业绩预告", "临时公告")):
        return "临时公告"
    return "其他公告"


def get_reit_asset_type(name: str) -> str:
    """根据REIT名称判断底层资产类型，决定提取哪些专项指标"""
    if any(k in name for k in ("高速", "广河", "广深", "交控", "铁建高速", "沪杭甬",
                                "越秀高速", "深高速", "招商高速", "高速公路", "交建高速")):
        return "transportation"
    if any(k in name for k in ("太阳能", "清洁能源", "新能源", "绿能", "能源建设",
                                "电建", "蒙能", "首钢绿能", "华润燃气", "燃气")):
        return "energy"
    if any(k in name for k in ("数据中心", "润泽", "铁塔")):
        return "data_center"
    if any(k in name for k in ("物流", "仓储", "普洛斯", "顺丰", "安博", "京东仓储",
                                "宝湾", "盐田港", "深国际")):
        return "logistics"
    if any(k in name for k in ("商业", "大悦城", "印力", "百联", "物美", "中海商业",
                                "绿发商业", "华润商业", "华威市场", "金茂")):
        return "commercial"
    if any(k in name for k in ("产业园", "科创", "联东", "中关村", "北交所", "临港",
                                "高新", "光谷", "科投", "和达高科", "广开产园",
                                "南京产园", "蛇口产园", "张江", "苏园")):
        return "industrial_park"
    if any(k in name for k in ("租赁住房", "安居", "有巢", "宽庭", "昌保", "保障房")):
        return "residential"
    if any(k in name for k in ("水务", "水利", "污水", "原水", "首创", "固废", "生态")):
        return "eco_environmental"
    return "other"


# ──────────────────────────────────────────────────────────────────────────────
# 5. 通用辅助函数
# ──────────────────────────────────────────────────────────────────────────────

def _find(patterns: list[str], text: str) -> Optional[str]:
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return None


def _normalize_amount(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    return re.sub(r"\s+", "", s)


def _extract_yoy(text: str, keywords: list[str]) -> Optional[str]:
    """通用同比增速提取，返回带符号的百分比字符串，如 +16.3% 或 -2.1%"""
    for kw in keywords:
        m = re.search(
            rf"{re.escape(kw)}[^。\n]{{0,80}}?同比(增长|增加|减少|下降)[约]?\s*([\d.]+)\s*%",
            text,
        )
        if m:
            sign = "+" if m.group(1) in ("增长", "增加") else "-"
            return f"{sign}{m.group(2)}%"
    return None


def _extract_qoq(text: str, keywords: list[str]) -> Optional[str]:
    """通用环比增速提取"""
    for kw in keywords:
        m = re.search(
            rf"{re.escape(kw)}[^。\n]{{0,80}}?环比(增长|增加|减少|下降)[约]?\s*([\d.]+)\s*%",
            text,
        )
        if m:
            sign = "+" if m.group(1) in ("增长", "增加") else "-"
            return f"{sign}{m.group(2)}%"
    return None


# ──────────────────────────────────────────────────────────────────────────────
# 6. 资产类型专属字段提取
# ──────────────────────────────────────────────────────────────────────────────

def extract_occupancy_fields(text: str) -> dict:
    """产业园区 / 仓储物流 / 消费商业 / 数据中心 专属经营指标"""
    occ = _find([
        r"(?:加权平均|综合|整体|项目|期末)?出租率[为是：:\s]*([\d.]+)\s*%",
        r"出租率\s+([\d.]+)\s*%",
        r"租用率[：:\s]*([\d.]+)\s*%",
    ], text)

    rent = _find([
        r"平均(?:租金|租赁单价)[为是：:\s]*([\d.]+)\s*(?:元/㎡/月|元/平方米/月|元/平米/月)",
        r"租金单价[为是：:\s]*([\d.]+)\s*元",
    ], text)

    collection = _find([
        r"(?:租金)?收缴率[为是：:\s]*([\d.]+)\s*%",
        r"实收率[为是：:\s]*([\d.]+)\s*%",
    ], text)

    top5 = _find([
        r"前[五5]大?租户[^。\n]{0,20}占比[为是：:\s]*([\d.]+)\s*%",
        r"前[五5]名?租户[^。\n]{0,20}占比[为是：:\s]*([\d.]+)\s*%",
    ], text)

    return {
        "occupancy_rate":    occ,
        "avg_rent":          rent,
        "collection_rate":   collection,
        "top5_tenant_ratio": top5,
    }


def extract_residential_fields(text: str) -> dict:
    """保障性租赁住房专属经营指标"""
    occ = _find([
        r"(?:期末|整体|综合)?出租率[为是：:\s]*([\d.]+)\s*%",
        r"出租率\s+([\d.]+)\s*%",
    ], text)

    units = _find([
        r"在租套数[为是：:\s]*([\d,]+)\s*套",
        r"出租套数[为是：:\s]*([\d,]+)\s*套",
        r"已出租.*?([\d,]+)\s*套",
    ], text)

    rent = _find([
        r"平均租金[为是：:\s]*([\d.]+)\s*(?:元/套/月|元/月/套|元/月)",
        r"租金水平[为是：:\s]*([\d.]+)\s*元",
    ], text)

    collection = _find([
        r"(?:租金)?收缴率[为是：:\s]*([\d.]+)\s*%",
    ], text)

    return {
        "occupancy_rate":  occ,
        "units_rented":    units,
        "avg_rent":        rent,
        "collection_rate": collection,
    }


def extract_traffic(text: str) -> dict:
    """交通基础设施专属指标：车流量、通行费收入等"""
    daily = _find([
        r"日均(?:车辆)?通行量[为是：:\s]*([\d,.]+\s*(?:万辆次|辆次|万辆|辆))",
        r"日均车流量[为是：:\s]*([\d,.]+\s*(?:万辆次|辆次|万辆|辆))",
    ], text)

    total = _find([
        r"(?:本期|本季度|累计)?(?:车辆通行量|车流量|通行量)[为是：:\s]*([\d,.]+\s*(?:万辆次|辆次|万辆|辆))",
        r"交通量[为是：:\s]*([\d,.]+\s*(?:万辆次|辆次|万辆|辆))",
    ], text)

    yoy = _extract_yoy(text, ["车辆通行量", "通行量", "车流量", "交通量"])
    qoq = _extract_qoq(text, ["车辆通行量", "通行量", "车流量", "交通量"])

    toll = _find([
        r"通行费(?:收入)?[为是：:\s]*([\d,.]+\s*(?:万元|亿元|元))",
        r"收费收入[为是：:\s]*([\d,.]+\s*(?:万元|亿元|元))",
    ], text)

    free_impact = _find([
        r"节假日免费[^。\n]{0,40}?(?:减少|影响|损失)收入[约]?\s*([\d,.]+\s*(?:万元|亿元|元))",
        r"免费通行[^。\n]{0,40}?(?:减少|影响|损失)\s*([\d,.]+\s*(?:万元|亿元|元))",
    ], text)

    return {
        "traffic_daily_volume":  daily,
        "traffic_volume":        total,
        "traffic_yoy":           yoy,
        "traffic_qoq":           qoq,
        "toll_revenue":          toll,
        "free_passage_impact":   free_impact,
    }


def extract_energy(text: str) -> dict:
    """能源基础设施专属指标：发电量、电价、利用小时等"""
    generation = _find([
        r"(?:本期|累计|本年)?(?:发电量|总发电量)[为是：:\s]*([\d,.]+\s*(?:亿千瓦时|万千瓦时|千瓦时|GWh|MWh))",
        r"发电量[：:\s]*([\d,.]+\s*(?:亿千瓦时|万千瓦时|GWh|MWh))",
    ], text)

    grid_power = _find([
        r"(?:本期|累计)?上网电量[为是：:\s]*([\d,.]+\s*(?:亿千瓦时|万千瓦时|千瓦时|GWh|MWh))",
    ], text)

    hours = _find([
        r"(?:发电)?利用小时(?:数)?[为是：:\s]*([\d,.]+)\s*(?:小时|h)",
        r"等效利用小时[为是：:\s]*([\d,.]+)\s*小时",
    ], text)

    price = _find([
        r"(?:平均)?(?:含税)?上网电价[为是：:\s]*([\d.]+)\s*(?:元/千瓦时|元/度|元／千瓦时)",
        r"(?:平均)?结算电价[为是：:\s]*([\d.]+)\s*(?:元/千瓦时|元/度)",
        r"电价[为是：:\s]*([\d.]+)\s*元/千瓦时",
    ], text)

    gen_yoy   = _extract_yoy(text, ["发电量", "上网电量"])
    price_yoy = _extract_yoy(text, ["电价", "上网电价", "结算电价"])

    availability = _find([
        r"(?:风机|光伏板|设备)?可利用率[为是：:\s]*([\d.]+)\s*%",
        r"设备(?:平均)?可用率[为是：:\s]*([\d.]+)\s*%",
        r"可利用小时率[为是：:\s]*([\d.]+)\s*%",
    ], text)

    return {
        "power_generation":       generation,
        "grid_power":             grid_power,
        "utilization_hours":      hours,
        "power_price":            price,
        "power_generation_yoy":   gen_yoy,
        "power_price_change":     price_yoy,
        "equipment_availability": availability,
    }


def extract_eco_environmental(text: str) -> dict:
    """生态环保（污水/垃圾/水务）专属指标"""
    volume = _find([
        r"(?:污水|垃圾|废物)?处理量[为是：:\s]*([\d,.]+\s*(?:万吨|吨|万立方米|立方米|万m³))",
        r"(?:供水量|水量)[为是：:\s]*([\d,.]+\s*(?:万吨|吨|万立方米|立方米))",
        r"处理规模[为是：:\s]*([\d,.]+\s*(?:万吨|吨/日|万立方米/日))",
    ], text)

    unit_price = _find([
        r"处理单价[为是：:\s]*([\d.]+)\s*(?:元/吨|元/立方米|元/m³)",
        r"服务单价[为是：:\s]*([\d.]+)\s*元",
        r"污水处理费[为是：:\s]*([\d.]+)\s*元/吨",
    ], text)

    utilization = _find([
        r"产能利用率[为是：:\s]*([\d.]+)\s*%",
        r"负荷率[为是：:\s]*([\d.]+)\s*%",
    ], text)

    volume_yoy = _extract_yoy(text, ["处理量", "供水量"])

    return {
        "treatment_volume":     volume,
        "unit_price":           unit_price,
        "capacity_utilization": utilization,
        "treatment_yoy":        volume_yoy,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 7. 公告类型专属字段提取
# ──────────────────────────────────────────────────────────────────────────────

def _extract_common_financials(text: str) -> dict:
    """提取各类报告通用财务字段"""
    # 营业收入
    revenue = _find([
        r"\n\s*1\s*营业收入\s+([\d,]+(?:\.\d+)?)\s",
        r"营业收入[：:\s]+([\d,]+(?:\.\d+)?)\s*(?:万元|亿元|元)",
        r"本期营业收入[：:\s]+([\d,]+(?:\.\d+)?)\s*(?:万元|亿元|元)",
    ], text)
    if revenue and re.fullmatch(r"[\d,]+(?:\.\d+)?", revenue.replace(",", "")):
        revenue += "元"

    # 净利润
    net_profit = _find([
        r"(?:\d+[\.\、])?本期净利润\s+([-−]?[\d,]+(?:\.\d+)?)\s",
        r"(?:本期)?净利润[：:\s]+([-−]?[\d,，]+(?:\.\d+)?)\s*(?:万元|亿元|元)",
        r"归属.*?净利润[：:\s]+([-−]?[\d,]+(?:\.\d+)?)\s*(?:万元|亿元|元)",
    ], text)
    if net_profit and re.fullmatch(r"-?[\d,]+(?:\.\d+)?", net_profit.replace(",", "").replace("−", "-")):
        net_profit += "元"

    # 可供分配金额
    dist_income = _find([
        r"本期可供分配金额\s*([\d,]+(?:\.\d+)?)\s*[-\s]",
        r"本期\s+([\d,]+(?:\.\d+)?)\s+[\d.]{4,8}\s+[-—]",
        r"(?:本期)?可供分配(?:金额|收益)[：:\s]+([\d,]+(?:\.\d+)?)\s*(?:万元|亿元|元)?",
        r"可分配(?:利润|金额)[：:\s]+([\d,]+(?:\.\d+)?)\s*(?:万元|亿元|元)?",
    ], text)
    if dist_income and re.fullmatch(r"[\d,]+(?:\.\d+)?", dist_income.replace(",", "")):
        dist_income += "元"

    # 每份可供分配
    dist_per_unit = _find([
        r"本期\s+[\d,]+(?:\.\d+)?\s+([\d.]{4,8})\s+[-—]",
        r"单位可供分配金额\s+([\d.]+)",
        r"每份(?:基金)?(?:份额)?可供分配(?:金额|收益)[：:\s]+([\d.]+)\s*元",
        r"每份基金份额可供分配金额为?\s*([\d.]+)\s*元",
    ], text)

    # 经营活动现金流
    cash_flow = _find([
        r"经营活动(?:产生的)?现金流量净额[：:\s]+([-−]?[\d,]+(?:\.\d+)?)\s*(?:万元|亿元|元)?",
        r"经营活动现金流[：:\s]+([-−]?[\d,]+(?:\.\d+)?)\s*(?:万元|亿元|元)?",
    ], text)
    if cash_flow and re.fullmatch(r"-?[\d,]+(?:\.\d+)?", cash_flow.replace(",", "").replace("−", "-")):
        cash_flow += "元"

    # 基金净值
    nav = _find([
        r"(?:期末)?基金份额净值[：:\s]+([\d.]+)\s*元",
        r"每份基金份额净值[为是]?\s*([\d.]+)\s*元",
        r"基金份额净值\s+([\d.]+)",
        r"单位净值\s+([\d.]+)",
    ], text)

    return {
        "revenue":                _normalize_amount(revenue),
        "net_profit":             _normalize_amount(net_profit),
        "distributable_income":   _normalize_amount(dist_income),
        "distributable_per_unit": dist_per_unit,
        "cash_flow":              _normalize_amount(cash_flow),
        "nav_per_unit":           nav,
    }


def extract_periodic(text: str, title: str, asset_type: str = "other") -> dict:
    """定期报告：通用财务 + 资产专属经营字段"""
    rtype = (
        _find([r"(年度报告|半年度报告|第[一二三四]季度报告)"], title) or
        _find([r"(年度报告|半年度报告|第[一二三四]季度报告)"], text[:500])
    )
    period = _find([
        r"本报告期自\s*(\d{4}年\d{1,2}月\d{1,2}日起至\d{4}年\d{1,2}月\d{1,2}日止)",
        r"报告期[：:]\s*(\d{4}年\d{1,2}月\d{1,2}日\s*[-~至]\s*\d{4}年\d{1,2}月\d{1,2}日)",
        r"(\d{4}年\d{1,2}月\d{1,2}日起至\d{4}年\d{1,2}月\d{1,2}日止)",
    ], text)

    result = {"report_type": rtype, "report_period": period}
    result.update(_extract_common_financials(text))

    # 资产类型专属字段
    if asset_type == "transportation":
        result.update(extract_traffic(text))
    elif asset_type == "energy":
        result.update(extract_energy(text))
    elif asset_type == "residential":
        result.update(extract_residential_fields(text))
    elif asset_type == "eco_environmental":
        result.update(extract_eco_environmental(text))
    else:  # industrial_park, logistics, commercial, data_center, other
        result.update(extract_occupancy_fields(text))

    return result


def extract_interim(text: str, asset_type: str = "other") -> dict:
    """临时公告 / 月度经营数据：精简版提取"""
    period = _find([
        r"(\d{4}年第[一二三四]季度)",
        r"(\d{4}年\d{1,2}月(?:份)?)",
        r"(\d{4}年度)",
        r"报告期[为是：:]*\s*(\d{4}年[^\n，。]{2,20})",
    ], text)

    result = {"report_period": period}
    result.update(_extract_common_financials(text))

    # 特殊事项
    special = _find([
        r"((?:重大事项|特别提示|风险提示)[：:][^\n]{10,100})",
    ], text)
    result["special_notes"] = special

    # 资产专属
    if asset_type == "transportation":
        result.update(extract_traffic(text))
    elif asset_type == "energy":
        result.update(extract_energy(text))
    elif asset_type == "residential":
        result.update(extract_residential_fields(text))
    elif asset_type == "eco_environmental":
        result.update(extract_eco_environmental(text))
    else:
        result.update(extract_occupancy_fields(text))

    return result


def extract_dividend(text: str) -> dict:
    """收益分配公告"""
    div = _find([
        r"每份基金份额(?:派发红利|分配收益|现金分红)[：:]*\s*([\d.]+)\s*元",
        r"每份(?:基金)?(?:份额)?(?:分配|派发|派息)[：:]*\s*([\d.]+)\s*元",
        r"派发现金红利.*?每份\s*([\d.]+)\s*元",
    ], text)

    total_div = _find([
        r"本次(?:现金红利|分红|收益分配)(?:总额|总量|金额)?[为是：:\s]*([\d,.]+\s*(?:万元|亿元|元))",
        r"(?:合计|共计)派发(?:现金)?红利[：:\s]*([\d,.]+\s*(?:万元|亿元|元))",
        r"本次分配总额[为是：:\s]*([\d,.]+\s*(?:万元|亿元|元))",
    ], text)

    yield_ann = _find([
        r"年化分红率[：:]\s*([\d.]+)\s*%",
        r"年化(?:收益|分派)率[：:]\s*([\d.]+)\s*%",
        r"本次分配.*?年化.*?([\d.]+)\s*%",
    ], text)

    dist_ratio = _find([
        r"本次分配比例[为是：:\s]*([\d.]+)\s*%",
        r"将可供分配金额的\s*([\d.]+)\s*%",
        r"分配比例[为是：:\s]*([\d.]+)\s*%",
    ], text)

    record = _find([
        r"权益登记日[为是：:]*\s*(\d{4}年\d{1,2}月\d{1,2}日)",
        r"权益登记日[为是：:]*\s*(\d{4}-\d{2}-\d{2})",
    ], text)

    ex_div = _find([
        r"除权除息日[为是：:]*\s*(\d{4}年\d{1,2}月\d{1,2}日)",
        r"除权除息日[为是：:]*\s*(\d{4}-\d{2}-\d{2})",
        r"除息日[为是：:]*\s*(\d{4}年\d{1,2}月\d{1,2}日)",
    ], text)

    payment = _find([
        r"(?:现金红利|红利)发放日[为是：:]*\s*(\d{4}年\d{1,2}月\d{1,2}日)",
        r"派息日[为是：:]*\s*(\d{4}年\d{1,2}月\d{1,2}日)",
    ], text)

    period = _find([
        r"本次分配(?:收益|红利)所属期间[为是：:]*\s*([^\n，。]{4,30})",
        r"(\d{4}年(?:第[一二三四]季度|年度|半年度))",
    ], text)

    cum_times = _find([
        r"第(\d+)次(?:分红|收益分配|派息)",
        r"(?:上市以来|历史)?(?:累计|合计)分红\s*(\d+)\s*次",
    ], text)

    return {
        "dividend_per_unit":   div,
        "total_dividend":      total_div,
        "distribution_ratio":  dist_ratio,
        "dividend_yield_ann":  yield_ann,
        "record_date":         record,
        "ex_dividend_date":    ex_div,
        "payment_date":        payment,
        "distribution_period": period,
        "cumulative_times":    cum_times,
    }


def extract_offering(text: str, title: str) -> dict:
    """发售/募集公告"""
    price = _find([
        r"(?:基金份额)?(?:发行|发售)(?:参考)?价格[为是：:\s]*([\d.]+)\s*元",
        r"每份基金份额(?:认购|发售|发行)价格[为是：:\s]*([\d.]+)\s*元",
        r"认购价格[为是：:\s]*([\d.]+)\s*元[/／]?份?",
    ], text)

    total_shares = _find([
        r"(?:拟)?(?:发行|募集|发售)份额(?:总量|总数)?[为是：:\s]*([\d,.]+\s*(?:亿份|万份))",
        r"基金规模(?:不超过)?[：:\s]*([\d,.]+\s*(?:亿元|万元))",
        r"募集资金(?:总额)?(?:不超过)?[：:\s]*([\d,.]+\s*(?:亿元|万元))",
    ], text)

    strategic = _find([
        r"战略配售(?:份额|数量)?[为是：:\s]*([\d,.]+\s*(?:亿份|万份))",
        r"战略投资者[^。\n]{0,30}?([\d,.]+\s*(?:亿份|万份))",
    ], text)

    institutional = _find([
        r"网下配售(?:份额|数量)?[为是：:\s]*([\d,.]+\s*(?:亿份|万份))",
        r"网下(?:投资者)?认购[^。\n]{0,30}?([\d,.]+\s*(?:亿份|万份))",
    ], text)

    fee_rate = _find([
        r"认购费率[为是：:\s]*([\d.]+)\s*%",
        r"销售手续费[为是：:\s]*([\d.]+)\s*%",
    ], text)

    asset_value = _find([
        r"资产评估(?:价值|价格)[为是：:\s]*([\d,.]+\s*(?:亿元|万元))",
        r"基础设施项目(?:评估|估值)[为是：:\s]*([\d,.]+\s*(?:亿元|万元))",
        r"评估价值[为是：:\s]*([\d,.]+\s*(?:亿元|万元))",
    ], text)

    cap_rate = _find([
        r"资本化率[为是：:\s]*([\d.]+)\s*%",
        r"Cap\s*Rate[为是：:\s]*([\d.]+)\s*%",
    ], text)

    sub_date = _find([
        r"(?:公众投资者)?认购(?:时间|日期)[为是：:\s]*(\d{4}年\d{1,2}月\d{1,2}日)",
        r"发售(?:日期|时间)[为是：:\s]*(\d{4}年\d{1,2}月\d{1,2}日)",
    ], text)

    listing_date = _find([
        r"预计(?:上市交易|上市|挂牌)(?:日期|时间)[为是：:\s]*(\d{4}年\d{1,2}月\d{1,2}日)",
        r"上市交易日[为是：:\s]*(\d{4}年\d{1,2}月\d{1,2}日)",
    ], text)

    brief = re.sub(r"\s+", " ", text[:400]).strip()[:200] if text else title[:80]

    return {
        "offering_price":       price,
        "offering_shares":      total_shares,
        "strategic_shares":     strategic,
        "institutional_shares": institutional,
        "fee_rate":             fee_rate,
        "asset_value":          asset_value,
        "cap_rate":             cap_rate,
        "subscription_date":    sub_date,
        "listing_date":         listing_date,
        "brief":                brief,
    }


def extract_expansion(text: str, title: str) -> dict:
    """扩募 / 并购公告"""
    price = _find([
        r"交易对价[为是：:\s]*([\d,.]+\s*(?:亿元|万元|元))",
        r"购买(?:价格|金额)[为是：:\s]*([\d,.]+\s*(?:亿元|万元|元))",
        r"收购(?:价格|金额)[为是：:\s]*([\d,.]+\s*(?:亿元|万元|元))",
        r"转让价格[为是：:\s]*([\d,.]+\s*(?:亿元|万元|元))",
    ], text)

    new_shares = _find([
        r"扩募(?:份额|数量)?[为是：:\s]*([\d,.]+\s*(?:亿份|万份))",
        r"新发(?:基金)?份额[为是：:\s]*([\d,.]+\s*(?:亿份|万份))",
    ], text)

    new_project = _find([
        r"(?:拟)?(?:购入|收购|购买)(?:的)?(?:基础设施)?项目[：:]\s*([^\n，。]{5,40})",
        r"标的(?:资产|项目)[：:]\s*([^\n，。]{5,40})",
    ], text)

    brief = re.sub(r"\s+", " ", text[:400]).strip()[:200] if text else title[:80]

    return {
        "transaction_price": price,
        "expansion_shares":  new_shares,
        "new_project":       new_project,
        "brief":             brief,
    }


def extract_unitholder_meeting(text: str, title: str) -> dict:
    """持有人大会公告"""
    meeting_date = _find([
        r"(?:会议|大会)(?:召开)?(?:时间|日期)[为是：:\s]*(\d{4}年\d{1,2}月\d{1,2}日)",
        r"定于\s*(\d{4}年\d{1,2}月\d{1,2}日)",
    ], text)

    items = re.findall(r"议案[一二三四五六七八九十\d一二三四五六七八九十]+[：:．.、\s]\s*([^\n。]{10,50})", text)
    resolutions = "；".join(items[:4]) if items else None

    brief = re.sub(r"\s+", " ", text[:300]).strip()[:150] if text else title[:80]

    return {
        "meeting_date": meeting_date,
        "resolutions":  resolutions,
        "brief":        brief,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 7.5 其他公告摘要提取
# ──────────────────────────────────────────────────────────────────────────────

_BOILERPLATE = ("请阅读", "作出投资", "风险提示", "基金托管", "基金合同", "本概要提供",
                "招募说明书", "销售文件", "投资者须知", "编制日期", "送出日期")

def _extract_other_summary(text: str, title: str) -> str:
    """从公告正文中提取关键摘要，优先找变更原因/主要内容/关键数据"""
    if not text:
        return title[:40]

    # P1：明确说明"本次变更/更新/调整内容"的句子
    change_pats = [
        r"本次(?:更新|修订|调整|变更)(?:的)?(?:主要)?内容[为是：:]\s*([^。\n]{10,80})",
        r"主要(?:更新|变化|变更|修改|调整)[为是：:]\s*([^。\n]{10,80})",
        r"本次(?:修订|更新)[^，。\n]{0,10}[，,]\s*([^。\n]{10,60})",
    ]
    for pat in change_pats:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()[:80]

    # P2：含关键数字（金额、比率、增减）的有效句子
    sentences = re.split(r'[。！？\n]+', text)
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 15 or len(sent) > 120:
            continue
        if any(k in sent for k in _BOILERPLATE):
            continue
        if re.search(r'[\d.]+\s*%|[\d,]+\s*(?:万元|亿元|元)|同比|环比|增长|下降|新增|减少', sent):
            return sent[:80]

    # P3：第一个有实质内容的句子（跳过标题行和套话）
    skip_title = True
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 15:
            continue
        if any(k in sent for k in _BOILERPLATE):
            continue
        # 跳过与标题高度重合的首句
        if skip_title and sent[:20] in title:
            skip_title = False
            continue
        skip_title = False
        return sent[:80]

    return title[:40]


# ──────────────────────────────────────────────────────────────────────────────
# 8. 统一入口：分类 + 提取 + 摘要
# ──────────────────────────────────────────────────────────────────────────────

def analyze_announcement(title: str, text: str, name: str = "") -> dict:
    ann_type   = classify_type(title)
    asset_type = get_reit_asset_type(name)

    # ── 收益分配 ──────────────────────────────
    if ann_type == "收益分配":
        details = extract_dividend(text)
        div    = details.get("dividend_per_unit")
        ratio  = details.get("distribution_ratio")
        ex_div = details.get("ex_dividend_date")
        parts  = []
        if div:   parts.append(f"每份 {div} 元")
        if ratio: parts.append(f"分配比例 {ratio}%")
        if ex_div: parts.append(f"除息日 {ex_div}")
        summary = "　".join(parts) or "收益分配公告"

    # ── 定期报告 ──────────────────────────────
    elif ann_type == "定期报告":
        details = extract_periodic(text, title, asset_type)
        rtype   = details.get("report_type") or ""
        if asset_type == "transportation":
            vol = details.get("traffic_volume") or details.get("traffic_daily_volume")
            yoy = details.get("traffic_yoy")
            summary = f"{rtype}：通行量 {vol}" + (f"　同比 {yoy}" if yoy else "") if vol else (rtype or "定期报告")
        elif asset_type == "energy":
            gen  = details.get("power_generation")
            gyoy = details.get("power_generation_yoy")
            pri  = details.get("power_price")
            if gen:
                summary = f"{rtype}：发电量 {gen}" + (f" 同比 {gyoy}" if gyoy else "") + (f"　电价 {pri} 元/度" if pri else "")
            else:
                summary = rtype or "定期报告"
        elif asset_type == "eco_environmental":
            vol  = details.get("treatment_volume")
            util = details.get("capacity_utilization")
            summary = f"{rtype}：处理量 {vol}" + (f"　产能利用率 {util}%" if util else "") if vol else (rtype or "定期报告")
        else:
            dist = details.get("distributable_per_unit")
            occ  = details.get("occupancy_rate")
            units = details.get("units_rented")
            parts = []
            if dist:  parts.append(f"每份可分配 {dist} 元")
            if occ:   parts.append(f"出租率 {occ}%")
            if units: parts.append(f"在租 {units} 套")
            summary = (f"{rtype}：" + "　".join(parts)) if parts else (rtype or "定期报告")

    # ── 临时公告 / 月度经营数据 ───────────────
    elif ann_type in ("临时公告", "月度经营数据"):
        details = extract_interim(text, asset_type)
        period  = details.get("report_period") or ""
        if asset_type == "transportation":
            vol = details.get("traffic_volume") or details.get("traffic_daily_volume")
            yoy = details.get("traffic_yoy")
            summary = f"{period} 通行量 {vol}" + (f" 同比 {yoy}" if yoy else "") if vol else (period or ann_type)
        elif asset_type == "energy":
            gen = details.get("power_generation")
            summary = f"{period} 发电量 {gen}" if gen else (period or ann_type)
        else:
            occ = details.get("occupancy_rate")
            summary = f"{period} 出租率 {occ}%" if occ else (period or ann_type)

    # ── 发售公告 ──────────────────────────────
    elif ann_type == "发售公告":
        details = extract_offering(text, title)
        price   = details.get("offering_price")
        shares  = details.get("offering_shares")
        parts   = []
        if price:  parts.append(f"发售价 {price} 元/份")
        if shares: parts.append(f"规模 {shares}")
        summary = "　".join(parts) or "新基金发售"

    # ── 扩募并购 ──────────────────────────────
    elif ann_type == "扩募并购":
        details = extract_expansion(text, title)
        price   = details.get("transaction_price")
        project = details.get("new_project")
        parts   = []
        if project: parts.append(project)
        if price:   parts.append(f"对价 {price}")
        summary = "　".join(parts) or "扩募/并购公告"

    # ── 持有人大会 ────────────────────────────
    elif ann_type == "持有人大会":
        details = extract_unitholder_meeting(text, title)
        date_   = details.get("meeting_date")
        summary = f"会议日期 {date_}" if date_ else "持有人大会"

    # ── 其他公告 ──────────────────────────────
    else:
        brief   = re.sub(r"\s+", " ", text[:200]).strip()[:120] if text else title[:60]
        details = {"brief": brief}
        summary = _extract_other_summary(text, title)

    return {"type": ann_type, "one_line_summary": summary, "details": details}


# ──────────────────────────────────────────────────────────────────────────────
# 9. 控制台展示
# ──────────────────────────────────────────────────────────────────────────────
TYPE_COLOR_CONSOLE = {
    "收益分配":     "bold green",
    "定期报告":     "bold cyan",
    "临时公告":     "bold yellow",
    "月度经营数据": "bold yellow",
    "发售公告":     "bold magenta",
    "扩募并购":     "bold blue",
    "持有人大会":   "bold red",
    "其他公告":     "dim white",
}

ALL_LABELS = {
    # 通用财务
    "report_type":            "报告类型",
    "report_period":          "报告期",
    "revenue":                "营业收入",
    "net_profit":             "净利润",
    "distributable_income":   "可供分配金额",
    "distributable_per_unit": "每份可供分配（元）",
    "cash_flow":              "经营现金流",
    "nav_per_unit":           "基金净值（元）",
    # 产业园/仓储/商业/数据中心
    "occupancy_rate":         "出租率（%）",
    "avg_rent":               "平均租金",
    "collection_rate":        "收缴率（%）",
    "top5_tenant_ratio":      "前五大租户占比（%）",
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
    "power_price":            "上网电价（元/度）",
    "power_generation_yoy":   "发电量同比",
    "power_price_change":     "电价同比",
    "equipment_availability": "设备可利用率（%）",
    # 生态环保
    "treatment_volume":       "处理量",
    "unit_price":             "处理单价",
    "capacity_utilization":   "产能利用率（%）",
    "treatment_yoy":          "处理量同比",
    # 分红
    "dividend_per_unit":      "每份分红（元）",
    "total_dividend":         "分红总额",
    "distribution_ratio":     "分配比例（%）",
    "dividend_yield_ann":     "年化分红率（%）",
    "record_date":            "权益登记日",
    "ex_dividend_date":       "除权除息日",
    "payment_date":           "红利发放日",
    "distribution_period":    "分配所属期",
    "cumulative_times":       "本次为第X次分红",
    # 发售
    "offering_price":         "发售价格（元/份）",
    "offering_shares":        "发行规模",
    "strategic_shares":       "战略配售份额",
    "institutional_shares":   "网下配售份额",
    "fee_rate":               "认购费率（%）",
    "asset_value":            "底层资产估值",
    "cap_rate":               "资本化率（%）",
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
    "special_notes":          "特殊事项",
    "brief":                  "内容摘要",
}


def print_item(item: dict):
    a        = item["analysis"]
    ann_type = a.get("type", "其他公告")
    color    = TYPE_COLOR_CONSOLE.get(ann_type, "white")
    summary  = a.get("one_line_summary", "")
    details  = a.get("details") or {}

    console.print(
        f"\n  [{color}]▶ {ann_type}[/{color}]  "
        f"[bold]{item['name']}[/bold]（{item['code']}）"
    )
    console.print(f"    标题：{item['title']}")
    if summary:
        console.print(f"    摘要：[italic]{summary}[/italic]")

    for key, label in ALL_LABELS.items():
        val = details.get(key)
        if val and str(val) not in ("null", "None", ""):
            console.print(f"    {label}：{val}")


# ──────────────────────────────────────────────────────────────────────────────
# 10. 主流程
# ──────────────────────────────────────────────────────────────────────────────
def main(date_str: Optional[str] = None):
    if date_str is None:
        date_str = date.today().strftime("%Y%m%d")
    target_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

    OUTPUT_DIR.mkdir(exist_ok=True)
    pdf_dir = OUTPUT_DIR / date_str
    pdf_dir.mkdir(exist_ok=True)

    console.rule(f"[bold]公募REITs日报  {target_date}[/bold]")

    reit_map   = get_all_reits()
    reit_codes = set(reit_map.keys())
    console.print(
        f"覆盖 [bold]{len(reit_map)}[/bold] 只公募REITs"
        f"（上交所 {sum(1 for c in reit_map if c.startswith('5'))} + "
        f"深交所 {sum(1 for c in reit_map if c.startswith('18'))}）\n"
    )

    console.print(f"正在从东方财富获取 {len(reit_map)} 只REITs公告...")
    raw_anns = fetch_announcements(target_date, reit_codes)
    for ann in raw_anns:
        if reit_map.get(ann["code"]):
            ann["name"] = reit_map[ann["code"]]
    console.print(f"找到 [bold]{len(raw_anns)}[/bold] 条REITs公告\n")

    all_results: list[dict] = []

    for ann in raw_anns:
        text     = get_pdf_text(ann["pdf_url"], pdf_dir, ann["ann_id"])
        analysis = analyze_announcement(ann["title"], text, ann["name"])

        item = {
            "code":     ann["code"],
            "name":     ann["name"],
            "title":    ann["title"],
            "date":     target_date,
            "ann_id":   ann["ann_id"],
            "pdf_url":  ann["pdf_url"],
            "analysis": analysis,
        }
        all_results.append(item)
        print_item(item)

    out_file = OUTPUT_DIR / f"reits_{date_str}.json"
    out_file.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    console.rule("[bold]汇总[/bold]")
    if not all_results:
        console.print(f"[yellow]{target_date} 无公告（非交易日或数据未更新）[/yellow]")
    else:
        counts: dict[str, int] = {}
        for r in all_results:
            t = r["analysis"].get("type", "其他")
            counts[t] = counts.get(t, 0) + 1

        tbl = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        tbl.add_column("公告类型", style="bold")
        tbl.add_column("数量", justify="right")
        for t, cnt in sorted(counts.items()):
            tbl.add_row(t, str(cnt))
        tbl.add_row("[bold]合计[/bold]", f"[bold]{len(all_results)}[/bold]")
        console.print(tbl)

    console.print(f"\nPDF 缓存目录：[underline]{pdf_dir}[/underline]")
    console.print(f"日报 JSON  ：[underline]{out_file}[/underline]")
    return all_results


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(arg)
