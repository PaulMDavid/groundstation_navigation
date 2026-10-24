#!/usr/bin/env bash
# Open the bringup panel. The container's root user needs access to your X server
# (XWayland on Wayland desktops), which is all the xhost line grants.
set -euo pipefail
cd "$(dirname "$0")"
xhost +si:localuser:root >/dev/null
exec docker compose up --build bringup_gui
