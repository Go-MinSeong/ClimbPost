#!/bin/bash
# 세션 종료 전: 커밋되지 않은 변경사항 + 테스트 미실행 경고
set -e

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')
cd "$CWD"

WARNINGS=""

# 커밋되지 않은 변경사항 확인
UNCOMMITTED=$(git status -s 2>/dev/null | grep -v "^??" | wc -l | tr -d ' ')
if [ "$UNCOMMITTED" -gt 0 ]; then
  WARNINGS="${WARNINGS}⚠️ 커밋되지 않은 변경사항 ${UNCOMMITTED}개가 있습니다.\n"
fi

# 프롬프트 버퍼에 기록되지 않은 프롬프트 확인
PROMPT_LOG="$CWD/.claude/hooks/.prompts_buffer"
if [ -f "$PROMPT_LOG" ] && [ -s "$PROMPT_LOG" ]; then
  PROMPT_COUNT=$(wc -l < "$PROMPT_LOG" | tr -d ' ')
  WARNINGS="${WARNINGS}⚠️ 프롬프트 로그 미커밋: ${PROMPT_COUNT}개 프롬프트가 기록 대기 중입니다.\n"
fi

# 세션 소요시간 출력
SESSION_FILE="$CWD/.claude/hooks/.current_session"
if [ -f "$SESSION_FILE" ]; then
  START_TIME=$(grep "START_TIME=" "$SESSION_FILE" | cut -d= -f2)
  NOW=$(date +%s)
  ELAPSED=$((NOW - START_TIME))
  MINUTES=$((ELAPSED / 60))
  HOURS=$((MINUTES / 60))
  REMAINING_MIN=$((MINUTES % 60))
  if [ "$HOURS" -gt 0 ]; then
    WARNINGS="${WARNINGS}⏱️ 세션 소요시간: ${HOURS}시간 ${REMAINING_MIN}분\n"
  else
    WARNINGS="${WARNINGS}⏱️ 세션 소요시간: ${MINUTES}분\n"
  fi
fi

if [ -n "$WARNINGS" ]; then
  echo -e "$WARNINGS" | jq -Rs '{ additionalContext: . }'
fi

exit 0
