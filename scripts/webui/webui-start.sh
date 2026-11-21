#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="${CU_CONFIG_FILE:-$(python3 "$SCRIPT_DIR/../amazingdraw_paths.py" get config_file 2>/dev/null || echo "$SCRIPT_DIR/../config.json")}"
WEBUI_DIR="$SCRIPT_DIR"
WEBUI_PORT="8318"
WEBUI_PID_FILE="/tmp/amazing-draw-webui.pid"
WEBUI_LOG="/tmp/amazing-draw-webui.log"
DETACHED_SPAWN="$(cd "$SCRIPT_DIR/../gpu-pipeline" && pwd)/detached_spawn.py"

# 自动探测具备 fastapi 的 python 解释器（兼容 Homebrew python3.14 与系统 Python 3.9 环境）
PYTHON_BIN="python3"
if ! python3 -c "import fastapi" >/dev/null 2>&1; then
  if /usr/bin/python3 -c "import fastapi" >/dev/null 2>&1; then
    PYTHON_BIN="/usr/bin/python3"
  fi
fi

# Windows 下 detached_spawn.py 是原生进程，无法执行 Git Bash 的 python3 包装脚本
# （~/.local/bin/python3 是 #!/bin/bash 脚本，没有 .exe 后缀）。
# 因此解析成真实解释器路径，保证子进程能直接 exec。
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    RESOLVED_PY=$("$PYTHON_BIN" -c 'import sys; print(sys.executable)' 2>/dev/null || true)
    if [ -n "$RESOLVED_PY" ] && [ -f "$RESOLVED_PY" ]; then
      PYTHON_BIN="$RESOLVED_PY"
    fi
    ;;
esac

if [ -f "$CONFIG_FILE" ]; then
  # 路径经 argv 传入，避免 Windows 反斜杠在 -c 字符串里被当成转义序列
  WEBUI_PORT=$("$PYTHON_BIN" -c "import json,sys; print(json.load(open(sys.argv[1], encoding='utf-8')).get('webui_port', 8318))" "$CONFIG_FILE")
fi

health_ok() {
  curl -fsS "http://127.0.0.1:${WEBUI_PORT}/" >/dev/null 2>&1
}

collect_pids() {
  {
    if [ -f "$WEBUI_PID_FILE" ]; then
      cat "$WEBUI_PID_FILE" 2>/dev/null || true
      printf '\n'
    fi
    # pgrep 在 Git for Windows 的 Git Bash 里不存在，回退到 ps
    if command -v pgrep >/dev/null 2>&1; then
      pgrep -f 'scripts/webui/web_server.py' || true
      pgrep -f '[w]eb_server.py' || true
    else
      ps -W 2>/dev/null | awk '/web_server\.py/ {print $1}' || true
      ps 2>/dev/null | awk '/web_server\.py/ {print $1}' || true
    fi
    # 兜底：pid 文件丢失时按监听端口反查（Windows netstat 末列即 PID）
    if command -v netstat >/dev/null 2>&1; then
      netstat -ano 2>/dev/null | awk -v p=":${WEBUI_PORT}" \
        '$1 ~ /^TCP/ && $2 ~ p"$" && $4 == "LISTENING" {print $5}' || true
    fi
  } | awk 'NF' | sort -u | tr '\n' ' '
}

# Git Bash 的 kill 无法终止 Windows 原生进程（pid 空间不同），必须走 taskkill。
kill_pid() {
  pid="$1"
  if command -v taskkill >/dev/null 2>&1; then
    taskkill //PID "$pid" //F >/dev/null 2>&1 || true
  fi
  kill "$pid" 2>/dev/null || true
}

pid_alive() {
  if command -v tasklist >/dev/null 2>&1; then
    tasklist //FI "PID eq $1" //NH 2>/dev/null | grep -q "$1"
  else
    kill -0 "$1" 2>/dev/null
  fi
}

start_webui() {
  if health_ok; then
    echo "✅ WebUI 已运行: http://127.0.0.1:${WEBUI_PORT}"
    return 0
  fi

  if [ ! -f "$WEBUI_DIR/web_server.py" ]; then
    echo "❌ 找不到 web_server.py: $WEBUI_DIR"
    return 1
  fi
  if [ ! -f "$DETACHED_SPAWN" ]; then
    echo "❌ 找不到 detached_spawn.py: $DETACHED_SPAWN"
    return 1
  fi

  echo "🚀 启动 WebUI..."
  "$PYTHON_BIN" "$DETACHED_SPAWN" \
    --cwd "$WEBUI_DIR" \
    --log "$WEBUI_LOG" \
    --pid-file "$WEBUI_PID_FILE" \
    -- "$PYTHON_BIN" "$WEBUI_DIR/web_server.py" >/dev/null

  for _ in $(seq 1 30); do
    if health_ok; then
      echo "✅ WebUI 已启动: http://127.0.0.1:${WEBUI_PORT}"
      echo "   日志: $WEBUI_LOG"
      return 0
    fi
    sleep 1
  done

  echo "❌ WebUI 启动超时，请检查日志: $WEBUI_LOG"
  stop_webui
  return 1
}

stop_webui() {
  WEBUI_PIDS=$(collect_pids)

  if [ -z "${WEBUI_PIDS// /}" ]; then
    rm -f "$WEBUI_PID_FILE"
    if health_ok; then
      echo "⚠️ 端口 ${WEBUI_PORT} 仍在响应，但未找到 web_server.py 进程"
      return 1
    fi
    echo "ℹ️ WebUI 未运行"
    return 0
  fi

  echo "✋ 停止 WebUI: $WEBUI_PIDS"
  for pid in $WEBUI_PIDS; do
    kill_pid "$pid"
  done

  for _ in $(seq 1 15); do
    if ! health_ok; then
      STILL_RUNNING=0
      for pid in $WEBUI_PIDS; do
        if pid_alive "$pid"; then
          STILL_RUNNING=1
          break
        fi
      done
      if [ "$STILL_RUNNING" -eq 0 ]; then
        rm -f "$WEBUI_PID_FILE"
        echo "✅ 已停止 WebUI"
        return 0
      fi
    fi
    sleep 1
  done

  echo "⚠️ WebUI 未在 15s 内退出，执行强制停止"
  for pid in $WEBUI_PIDS; do
    kill_pid "$pid"
  done
  rm -f "$WEBUI_PID_FILE"
  echo "✅ 已强制停止 WebUI"
}

status_webui() {
  PIDS=$(collect_pids)
  if health_ok; then
    echo "✅ WebUI: http://127.0.0.1:${WEBUI_PORT}"
    if [ -n "${PIDS// /}" ]; then
      echo "   pid: $PIDS"
    fi
    if [ -f "$WEBUI_PID_FILE" ]; then
      echo "   pid-file: $(cat "$WEBUI_PID_FILE" 2>/dev/null || true)"
    fi
    echo "   日志: $WEBUI_LOG"
  else
    echo "ℹ️ WebUI 未运行 (port ${WEBUI_PORT})"
    if [ -n "${PIDS// /}" ]; then
      echo "   残留进程: $PIDS"
    fi
  fi
}

restart_webui() {
  stop_webui || true
  start_webui
}

case "${1:-start}" in
  -h|--help|help)
    echo "用法: $0 [start|stop|status|restart|help]"
    echo ""
    echo "选项/指令:"
    echo "  start    后台启动 WebUI（已运行则直接返回）"
    echo "  stop     停止 WebUI"
    echo "  status   查看运行状态"
    echo "  restart  先 stop 再 start"
    echo ""
    echo "端口: config.json webui_port（默认 ${WEBUI_PORT}）"
    echo "日志: $WEBUI_LOG"
    echo "pid:  $WEBUI_PID_FILE"
    exit 0
    ;;
  start)
    start_webui
    ;;
  stop)
    stop_webui
    ;;
  status)
    status_webui
    ;;
  restart)
    restart_webui
    ;;
  *)
    echo "用法: $0 [start|stop|status|restart|help]"
    exit 1
    ;;
esac
