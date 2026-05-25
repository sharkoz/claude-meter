#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"

# When run via sudo, use the real user — not root
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)

# Build a PATH that includes common user bin locations so the service
# can find the claude binary regardless of the login environment.
USER_PATH="$REAL_HOME/.local/bin:$REAL_HOME/.npm-global/bin:/usr/local/bin:/usr/bin:/bin"

# Detect nvm node bin dir if present
NVM_DIR="${NVM_DIR:-$REAL_HOME/.nvm}"
if [ -d "$NVM_DIR/versions/node" ]; then
    LATEST_NODE=$(ls -1 "$NVM_DIR/versions/node" | sort -V | tail -1)
    if [ -n "$LATEST_NODE" ]; then
        USER_PATH="$NVM_DIR/versions/node/$LATEST_NODE/bin:$USER_PATH"
    fi
fi

cat > /etc/systemd/system/claude-meter.service << EOF
[Unit]
Description=Claude Meter daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$REAL_USER
WorkingDirectory=$SCRIPT_DIR
Environment="PATH=$USER_PATH"
ExecStart=$REAL_HOME/.local/bin/uv run $SCRIPT_DIR/claude-meter.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now claude-meter
systemctl status claude-meter
