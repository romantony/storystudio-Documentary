#!/bin/bash
# Container start: VNC password from the environment, then supervisord runs the desktop and the API.
set -euo pipefail
mkdir -p "$HOME/.vnc" /data/runs /data/claude
if [ -z "${VNC_PASSWORD:-}" ]; then echo "VNC_PASSWORD is not set" >&2; exit 1; fi
if [ -z "${DOCGEN_API_TOKEN:-}" ]; then echo "DOCGEN_API_TOKEN is not set" >&2; exit 1; fi
printf '%s' "$VNC_PASSWORD" | vncpasswd -f > "$HOME/.vnc/passwd"; chmod 600 "$HOME/.vnc/passwd"
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1
exec supervisord -n -c /etc/docgen/supervisord.conf
