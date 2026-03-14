#!/bin/bash
# log-prompt.sh — 커밋 후 자동으로 프롬프트 로그 엔트리를 생성한다
# Usage: 이 스크립트는 post-commit hook에서 호출된다
#
# 동작:
# 1. 가장 최근 커밋의 해시와 메시지를 가져온다
# 2. docs/prompts/ 에 다음 번호의 로그 파일을 만든다
# 3. 커밋 정보를 기록한다

set -e

PROMPTS_DIR="docs/prompts"
COMMIT_HASH=$(git log -1 --format="%h")
COMMIT_MSG=$(git log -1 --format="%s")
COMMIT_DATE=$(git log -1 --format="%Y-%m-%d")

# 다음 번호 계산
LAST_NUM=$(ls "$PROMPTS_DIR"/*.md 2>/dev/null | grep -oP '^\d+' | sort -n | tail -1 || echo "0")
LAST_NUM=$(ls "$PROMPTS_DIR"/ 2>/dev/null | grep -oE '^[0-9]+' | sort -n | tail -1)
if [ -z "$LAST_NUM" ]; then
  NEXT_NUM="001"
else
  NEXT_NUM=$(printf "%03d" $((10#$LAST_NUM + 1)))
fi

# 커밋 메시지에서 제목 추출 (feat/fix/test 등 제거)
TITLE=$(echo "$COMMIT_MSG" | sed 's/^[a-z]*([^)]*): //' | sed 's/ /-/g' | cut -c1-30)

LOG_FILE="$PROMPTS_DIR/${NEXT_NUM}-${TITLE}.md"

# 이미 이 커밋에 대한 로그가 있으면 스킵
if grep -r "$COMMIT_HASH" "$PROMPTS_DIR"/*.md 2>/dev/null | grep -q .; then
  exit 0
fi

cat > "$LOG_FILE" << EOF
# ${NEXT_NUM} — ${COMMIT_MSG}

- **날짜**: ${COMMIT_DATE}
- **커밋**: \`${COMMIT_HASH}\` ${COMMIT_MSG}
- **프롬프트**: (여기에 사용한 프롬프트를 기록하세요)
- **결과**: (변경 요약)
EOF

echo "[prompt-log] Created $LOG_FILE"
