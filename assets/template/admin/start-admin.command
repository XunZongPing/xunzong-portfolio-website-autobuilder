#!/bin/sh
# ===========================================================================
#  Portfolio admin launcher (macOS)
#
#  THIS FILE IS PURE ASCII ON PURPOSE (same policy as start-admin.bat):
#  every user-facing Chinese line is printed by server.py. This script only
#  finds a REAL python3 and hands over to server.py in this Terminal window.
#  Closing the window stops the server.
#
#  Double-click this file in Finder to start. If double-clicking does
#  nothing (the execute bit is lost after unzip), run once:
#      chmod +x admin/start-admin.command
#  or just run it through the shell (works without the execute bit):
#      sh admin/start-admin.command
# ===========================================================================

# resolve the script directory to an absolute path first
DIR=$(cd "$(dirname "$0")" && pwd) || exit 1
cd "$DIR" || exit 1

PY=""

# ---------------------------------------------------------- 1. find python3
if [ -n "$SITE_PY" ] && [ -x "$SITE_PY" ]; then
  PY="$SITE_PY"
fi

# the managed runtime shipped with the WorkBuddy workspace
if [ -z "$PY" ]; then
  for d in "$HOME/.workbuddy/binaries/python/versions"/*; do
    if [ -x "$d/bin/python3" ]; then
      PY="$d/bin/python3"
    fi
  done
fi

# python3 on PATH
if [ -z "$PY" ] && command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
fi

# Homebrew (Apple Silicon / Intel)
if [ -z "$PY" ]; then
  for p in /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if [ -x "$p" ]; then
      PY="$p"
    fi
  done
fi

# ------------------------------------------- 2. prove it actually runs code
# A path that exists is not enough. Import the very module the server needs
# -- that is the only real test.
if [ -n "$PY" ]; then
  "$PY" -c "import http.server" >/dev/null 2>&1 || PY=""
fi

if [ -z "$PY" ]; then
  echo ""
  echo "  [ERROR] No usable Python 3 found."
  echo ""
  echo "  Install Python 3.8+ (https://www.python.org/downloads/ or:"
  echo "      brew install python3 ),"
  echo "  or point SITE_PY at a real python3, e.g."
  echo "      SITE_PY=/usr/local/bin/python3 sh start-admin.command"
  echo ""
  printf 'Press Enter to close...'
  read -r _
  exit 1
fi

# ------------------------------------------------------------- 3. run it
PORT=8848
if [ -n "$SITE_PORT" ]; then
  PORT="$SITE_PORT"
fi
# SITE_OPEN=1 tells server.py "a human double-clicked this, open the browser".
SITE_OPEN=1
PYTHONIOENCODING=utf-8
PYTHONUTF8=1
export SITE_OPEN PYTHONIOENCODING PYTHONUTF8

"$PY" -u "$DIR/server.py"
RC=$?

# rc=3 means the port is already serving; server.py already printed the URL
# in Chinese, here we just help by opening it.
if [ "$RC" -eq 3 ]; then
  open "http://127.0.0.1:$PORT/"
fi

echo ""
printf 'Press Enter to close...'
read -r _
exit $RC
