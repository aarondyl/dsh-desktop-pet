#!/bin/bash
# 双击这个文件就能叫出「小深」。
# 关掉终端窗口 / 按 Ctrl-C 就是让它睡觉。

cd "$(dirname "$0")" || exit 1

pick_python() {
  for p in "$@"; do
    [ -x "$p" ] || continue
    if "$p" - <<'PY' >/dev/null 2>&1
import tkinter, sys
sys.exit(0 if tkinter.TkVersion >= 8.6 else 1)
PY
    then
      echo "$p"
      return 0
    fi
  done
  return 1
}

PY=$(pick_python \
  "/opt/miniconda3/bin/python3" \
  "/opt/homebrew/bin/python3" \
  "/usr/local/bin/python3" \
  "/usr/bin/env python3")
if [ -z "$PY" ]; then
  PY=$(pick_python "$(command -v python3)")
fi
if [ -z "$PY" ]; then
  echo "没有找到带 Tk 8.6 的 python3，请先安装 Python 3（推荐 conda 或 python.org 版本）。"
  exit 1
fi

exec "$PY" pet.py "$@"
