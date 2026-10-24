#!/usr/bin/env bash
# Open the bringup panel. The container's root user needs access to your X server
# (XWayland on Wayland desktops), which is all the xhost line grants.
# GS_LINK=zenoh in .env: reach the robot through Zenoh (eduroam) instead of DDS (wired).
set -euo pipefail
cd "$(dirname "$0")"
xhost +si:localuser:root >/dev/null
# shellcheck disable=SC1091
[[ -f .env ]] && source .env
if [[ ${GS_LINK:-dds} == zenoh ]]; then
  export GS_DDS_CONFIG=cyclonedds_local.xml
  exec docker compose --profile zenoh up --build bringup_gui zenoh_bridge
fi
exec docker compose up --build bringup_gui
