#!/usr/bin/env bash
# event_bot launchd 自启安装脚本（Apple Silicon mac）
# 用法: bash scripts/event_bot/install_launchd.sh
#
# 装上之后:
#   开机自动起 / 进程退出自动拉起 / TG /restart 命令也靠它兜底
#   停: launchctl unload ~/Library/LaunchAgents/com.felix.event_bot.plist
#   启: launchctl load -w ~/Library/LaunchAgents/com.felix.event_bot.plist
#   看 stdout/stderr: tail -f $REPO/logs/event_bot.stdout.log

set -euo pipefail

LABEL="com.felix.event_bot"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

REPO="$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO" ]; then
    echo "错误: 当前目录不在 git 仓库内"; exit 1
fi

PYBIN="$REPO/.venv/bin/python"
BOT="$REPO/scripts/event_bot/bot.py"
CFG="$REPO/scripts/event_bot/config.py"

# 校验前置
for f in "$PYBIN" "$BOT" "$CFG"; do
    if [ ! -f "$f" ]; then
        echo "缺文件: $f"; exit 1
    fi
done

mkdir -p "$REPO/logs"
mkdir -p "$HOME/Library/LaunchAgents"

# 卸老 launchd 任务（如果之前装过）
launchctl unload "$PLIST" 2>/dev/null || true

# 杀掉之前 nohup 起的旧进程（如果有）
if [ -f "$REPO/logs/event_bot.pid" ]; then
    OLD_PID=$(cat "$REPO/logs/event_bot.pid" 2>/dev/null | tr -dc 0-9 || true)
    if [ -n "$OLD_PID" ] && ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "停止旧 nohup 进程 PID=$OLD_PID"
        kill "$OLD_PID" 2>/dev/null || true
        sleep 2
        ps -p "$OLD_PID" > /dev/null 2>&1 && kill -9 "$OLD_PID" 2>/dev/null || true
    fi
fi
pkill -f "scripts/event_bot/bot.py" 2>/dev/null || true
sleep 1

# 写 plist
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>WorkingDirectory</key>
    <string>$REPO/scripts/event_bot</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYBIN</string>
        <string>bot.py</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>$REPO/logs/event_bot.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$REPO/logs/event_bot.stderr.log</string>
</dict>
</plist>
EOF

launchctl load -w "$PLIST"
sleep 3

# 验证
if launchctl list | grep -q "$LABEL"; then
    echo "已加载: $PLIST"
    launchctl list | grep "$LABEL" | head -1
    echo
    echo "看输出:   tail -f $REPO/logs/event_bot.stdout.log"
    echo "看错误:   tail -f $REPO/logs/event_bot.stderr.log"
    echo "停止:     launchctl unload $PLIST"
    echo "启动:     launchctl load -w $PLIST"
else
    echo "加载失败，检查 stderr:"
    sleep 1
    tail -20 "$REPO/logs/event_bot.stderr.log" 2>/dev/null || echo "(stderr 还没产生)"
    exit 1
fi
