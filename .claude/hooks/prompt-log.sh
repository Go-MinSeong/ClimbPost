#!/bin/bash
# 유저 프롬프트 제출 시: 카운트 증가 + 프롬프트 내용 임시 저장
set -e

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // ""')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')
SESSION_FILE="$CWD/.claude/hooks/.current_session"
PROMPT_LOG="$CWD/.claude/hooks/.prompts_buffer"

# 프롬프트 카운트 증가
if [ -f "$SESSION_FILE" ]; then
  COUNT=$(grep "PROMPT_COUNT=" "$SESSION_FILE" | cut -d= -f2)
  NEW_COUNT=$((COUNT + 1))
  sed -i '' "s/PROMPT_COUNT=.*/PROMPT_COUNT=$NEW_COUNT/" "$SESSION_FILE"
fi

# 프롬프트 내용을 버퍼에 저장 (나중에 커밋 시 로그 파일에 기록)
DATE=$(date "+%Y-%m-%d %H:%M:%S")
echo "[$DATE] $PROMPT" >> "$PROMPT_LOG"

exit 0
