#!/bin/zsh
set -euo pipefail

project_dir="$(cd "$(dirname "$0")" && pwd)"
python_bin="$project_dir/.venv/bin/python"
plist_path="$HOME/Library/LaunchAgents/com.peternjorogew.cloudflare-domain-catcher.plist"
log_dir="$project_dir/logs"

if [[ ! -x "$python_bin" ]]; then
  print "Create the virtual environment first: uv venv --python 3.13"
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$log_dir"
launchctl bootout "gui/$(id -u)" "$plist_path" 2>/dev/null || true

cat > "$plist_path" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.peternjorogew.cloudflare-domain-catcher</string>
  <key>ProgramArguments</key>
  <array>
    <string>$python_bin</string>
    <string>$project_dir/domain_catcher.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$project_dir</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>30</integer>
  <key>StandardOutPath</key>
  <string>$log_dir/domain_catcher.log</string>
  <key>StandardErrorPath</key>
  <string>$log_dir/domain_catcher.error.log</string>
</dict>
</plist>
EOF

launchctl bootstrap "gui/$(id -u)" "$plist_path"
print "Installed and started: com.peternjorogew.cloudflare-domain-catcher"
