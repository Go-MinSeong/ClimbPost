#!/bin/bash
# 유저 프롬프트 제출 시: 카운트 증가 + 프롬프트 내용 임시 저장

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // ""' 2>/dev/null || echo "")
CWD=$(echo "$INPUT" | jq -r '.cwd // "."' 2>/dev/null || echo ".")
SESSION_FILE="$CWD/.claude/hooks/.current_session"
PROMPT_LOG="$CWD/.claude/hooks/.prompts_buffer"

# task-notification 등 시스템 메시지는 건너뜀
if echo "$PROMPT" | grep -q '<task-notification>'; then
  exit 0
fi

# 빈 프롬프트는 건너뜀
if [ -z "$PROMPT" ]; then
  exit 0
fi

# 프롬프트 카운트 증가
if [ -f "$SESSION_FILE" ]; then
  COUNT=$(grep "PROMPT_COUNT=" "$SESSION_FILE" | cut -d= -f2)
  NEW_COUNT=$((COUNT + 1))
  sed -i "s/PROMPT_COUNT=.*/PROMPT_COUNT=$NEW_COUNT/" "$SESSION_FILE"
fi

# 프롬프트 내용을 버퍼에 저장 (나중에 커밋 시 로그 파일에 기록)
# 긴 프롬프트는 앞 500자만 저장하고 [truncated] 표시
DATE=$(date "+%Y-%m-%d %H:%M:%S")
PROMPT_LEN=${#PROMPT}
if [ "$PROMPT_LEN" -gt 500 ]; then
  SHORT_PROMPT="${PROMPT:0:500}... [+$((PROMPT_LEN - 500))chars]"
else
  SHORT_PROMPT="$PROMPT"
fi
echo "[$DATE] $SHORT_PROMPT" >> "$PROMPT_LOG"

exit 0
