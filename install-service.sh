#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"

# When run via sudo, use the real user — not root
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)

cat > /etc/systemd/system/claude-meter.service << EOF
[Unit]
Description=Claude Meter daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$REAL_USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$REAL_HOME/.local/bin/uv run $SCRIPT_DIR/claude-meter.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now claude-meter
systemctl status claude-meter
