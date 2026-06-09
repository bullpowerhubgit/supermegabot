-- ThinkDiag 2 macOS Setup - Automatische Installation
tell application "Terminal"
    do script "cd /Users/rudolfsarkany/windsurf && bash scripts/thinkdiag2-complete-setup.sh"
    activate
end tell
