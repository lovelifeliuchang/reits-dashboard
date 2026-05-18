#!/bin/bash
cd "$(dirname "$0")"
mkdir -p logs

# 计算昨天日期（兼容 Mac 和 Linux）
if date -v-1d +%Y%m%d &>/dev/null 2>&1; then
    YESTERDAY=$(date -v-1d +%Y%m%d)   # Mac
else
    YESTERDAY=$(date -d "yesterday" +%Y%m%d)  # Linux
fi

LOG="logs/${YESTERDAY}.log"

echo "=== $(date) 开始运行（数据日期：${YESTERDAY}）===" >> "$LOG"

# 1. 下载公告、提取信息
/usr/local/bin/python3 reits_daily.py "$YESTERDAY" >> "$LOG" 2>&1

# 1b. 计算 T期货策略信号
/usr/local/bin/python3 t_signal.py "$YESTERDAY" >> "$LOG" 2>&1

# 2. 生成多日趋势 Dashboard 并推送到 GitHub Pages
/usr/local/bin/python3 generate_dashboard.py >> "$LOG" 2>&1
cd reits_reports && git add dashboard.html && git commit -m "update dashboard ${YESTERDAY}" && git push origin gh-pages >> "../$LOG" 2>&1
cd ..

# 3. 发送飞书卡片（含 Dashboard 链接）
/usr/local/bin/python3 send_feishu.py "$YESTERDAY" >> "$LOG" 2>&1

echo "=== $(date) 完成 ===" >> "$LOG"
