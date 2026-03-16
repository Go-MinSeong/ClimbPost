#!/bin/bash
# 세션 시작 시 타이머 시작 + 세션 ID 기록
set -e

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')
TIMESTAMP=$(date +%s)
DATE=$(date "+%Y-%m-%d %H:%M:%S")

# 세션 시작 시간을 파일에 기록
SESSION_FILE="$CWD/.claude/hooks/.current_session"
mkdir -p "$(dirname "$SESSION_FILE")"

cat > "$SESSION_FILE" << EOF
SESSION_ID=$SESSION_ID
START_TIME=$TIMESTAMP
START_DATE=$DATE
PROMPT_COUNT=0
EOF

echo "Session timer started at $DATE" >&2
exit 0
