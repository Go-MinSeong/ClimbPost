#!/bin/bash
# git commit 후: 프롬프트 로그 파일 자동 생성 (소요시간 포함)
set -e

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# git commit 명령어인지 확인
if [ "$TOOL_NAME" != "Bash" ]; then exit 0; fi
echo "$COMMAND" | grep -q "git commit" || exit 0

# 커밋 정보 가져오기
cd "$CWD"
COMMIT_HASH=$(git log -1 --format="%h" 2>/dev/null || echo "unknown")
COMMIT_MSG=$(git log -1 --format="%s" 2>/dev/null || echo "unknown")
COMMIT_DATE=$(git log -1 --format="%Y-%m-%d" 2>/dev/null || echo "unknown")

# 세션 시간 계산
SESSION_FILE="$CWD/.claude/hooks/.current_session"
DURATION="unknown"
if [ -f "$SESSION_FILE" ]; then
  START_TIME=$(grep "START_TIME=" "$SESSION_FILE" | cut -d= -f2)
  NOW=$(date +%s)
  ELAPSED=$((NOW - START_TIME))
  MINUTES=$((ELAPSED / 60))
  DURATION="${MINUTES}분"
fi

# 프롬프트 버퍼 읽기
PROMPT_LOG="$CWD/.claude/hooks/.prompts_buffer"
PROMPTS=""
if [ -f "$PROMPT_LOG" ]; then
  PROMPTS=$(cat "$PROMPT_LOG")
fi

# 다음 번호 계산
PROMPTS_DIR="$CWD/docs/prompts"
mkdir -p "$PROMPTS_DIR"
LAST_NUM=$(ls "$PROMPTS_DIR"/ 2>/dev/null | grep -oE '^[0-9]+' | sort -n | tail -1)
if [ -z "$LAST_NUM" ]; then
  NEXT_NUM="001"
else
  NEXT_NUM=$(printf "%03d" $((10#$LAST_NUM + 1)))
fi

# 이미 이 커밋 해시가 기록되어 있으면 기존 파일에 추가
EXISTING=$(grep -rl "$COMMIT_HASH" "$PROMPTS_DIR"/*.md 2>/dev/null | head -1)
if [ -n "$EXISTING" ]; then
  # 기존 파일이 있으면 스킵
  exit 0
fi

# 제목 생성
TITLE=$(echo "$COMMIT_MSG" | sed 's/^[a-z]*([^)]*): //' | tr ' ' '-' | cut -c1-30)

# 프롬프트 로그 파일 생성
LOG_FILE="$PROMPTS_DIR/${NEXT_NUM}-${TITLE}.md"

cat > "$LOG_FILE" << LOGEOF
# ${NEXT_NUM} — ${COMMIT_MSG}

- **날짜**: ${COMMIT_DATE}
- **소요시간**: ${DURATION}
- **커밋**: \`${COMMIT_HASH}\` ${COMMIT_MSG}

## 프롬프트

\`\`\`
${PROMPTS}
\`\`\`
LOGEOF

# 버퍼 클리어
> "$PROMPT_LOG"

exit 0
