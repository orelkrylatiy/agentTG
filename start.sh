#!/bin/bash
cd "$(dirname "$0")"

# Graceful stop + wait up to 10s
pkill -TERM -f tg_agent 2>/dev/null
for i in {1..10}; do
    sleep 1
    [ "$(pgrep -f tg_agent | wc -l)" -eq 0 ] && break
done
# Force kill if still alive
pkill -9 -f tg_agent 2>/dev/null
sleep 1

source .venv/bin/activate
nohup python -m tg_agent >> /tmp/agent.log 2>&1 &
echo "Агент запущен ✓  (Ctrl+C чтобы скрыть логи, агент продолжит работать)"
sleep 1
tail -f /tmp/agent.log
