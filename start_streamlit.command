#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_PROJECT_DIR="/Users/jason/Desktop/vs图像小说"
PROJECT_DIR="${STREAMLIT_PROJECT_DIR:-$SCRIPT_DIR}"
if [[ ! -f "$PROJECT_DIR/streamlit_app.py" && -f "$DEFAULT_PROJECT_DIR/streamlit_app.py" ]]; then
  PROJECT_DIR="$DEFAULT_PROJECT_DIR"
fi

APP_FILE="streamlit_app.py"
VENV_DIR="$PROJECT_DIR/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT="${STREAMLIT_PORT:-8501}"

pause_on_error() {
  local status=$?
  if [[ $status -ne 0 ]]; then
    echo
    echo "Streamlit startup failed. See the message above for details."
    if [[ -t 0 ]]; then
      read -r -p "Press Enter to close this window..."
    fi
  fi
}
trap pause_on_error EXIT

cd "$PROJECT_DIR"

if [[ ! -f "$APP_FILE" ]]; then
  echo "Cannot find $APP_FILE in $PROJECT_DIR"
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Cannot find python3. Please install Python 3 first."
    exit 1
  fi

  echo "Creating virtual environment in .venv..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

NEED_INSTALL=0
if [[ ! -f "$VENV_DIR/.requirements-installed" ]]; then
  NEED_INSTALL=1
elif [[ requirements.txt -nt "$VENV_DIR/.requirements-installed" ]]; then
  NEED_INSTALL=1
elif ! python -m streamlit --version >/dev/null 2>&1; then
  NEED_INSTALL=1
fi

if [[ "$NEED_INSTALL" -eq 1 ]]; then
  echo "Installing Python dependencies..."
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  touch "$VENV_DIR/.requirements-installed"
fi

# 端口检测：如果端口被占用，先关闭占用该端口的进程
if command -v lsof >/dev/null 2>&1; then
  PIDS="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$PIDS" ]]; then
    echo "端口 $PORT 被占用（PID: $(echo "$PIDS" | tr '\n' ' ')），正在关闭..."
    echo "$PIDS" | xargs kill 2>/dev/null || true
    sleep 1
    # 如果还活着，强制杀掉
    PIDS="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "$PIDS" ]]; then
      echo "进程未退出，强制结束..."
      echo "$PIDS" | xargs kill -9 2>/dev/null || true
      sleep 1
    fi
    echo "端口 $PORT 已释放。"
    echo
  fi
fi

echo
echo "Starting Streamlit..."
echo "Project: $PROJECT_DIR"
echo "Local URL: http://localhost:$PORT"
echo

python -m streamlit run "$APP_FILE" --server.port "$PORT" --server.headless false
