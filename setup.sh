#!/bin/bash
# 公募REITs日报系统 一键安装脚本
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON=$(which python3)
CRON_TIME="0 10 * * 1-6"  # 每周一至周六 10:00（发前一天数据）

echo "========================================"
echo "  公募REITs日报系统 安装程序"
echo "========================================"
echo ""

# ── 1. Python 依赖 ──────────────────────────
echo "[1/2] 安装 Python 依赖..."
$PYTHON -m pip install -q -r "$SCRIPT_DIR/requirements.txt"
echo "    ✓ 完成"
echo ""

# ── 2. 定时任务 ─────────────────────────────
echo "[2/2] 配置定时任务（每周一至周五 21:30 自动运行）..."
CRON_CMD="$CRON_TIME cd $SCRIPT_DIR && bash run_daily.sh"

if crontab -l 2>/dev/null | grep -q "reits_monitor/run_daily.sh"; then
    echo "    定时任务已存在，跳过"
else
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    echo "    ✓ 完成"
fi
echo ""

echo "========================================"
echo "  安装完成！仅需 Python3，无其他依赖。"
echo ""
echo "  手动运行：cd $SCRIPT_DIR && bash run_daily.sh"
echo "  定时触发：每周一至周五 21:30 自动执行"
echo "========================================"
