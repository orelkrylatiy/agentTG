#!/bin/bash
cd "$(dirname "$0")"
pkill -TERM -f tg_agent 2>/dev/null
sleep 3
source .venv/bin/activate
nohup python -m tg_agent >> /tmp/agent.log 2>&1 &
echo "Агент запущен ✓  (Ctrl+C чтобы скрыть логи, агент продолжит работать)"
sleep 1
tail -f /tmp/agent.log
