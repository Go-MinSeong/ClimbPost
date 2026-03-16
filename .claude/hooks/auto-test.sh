#!/bin/bash
# 파일 수정 후: 빠른 테스트 자동 실행 (비동기)
set -e

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# Edit/Write 도구로 Python 파일이 수정된 경우만
if [ "$TOOL_NAME" != "Edit" ] && [ "$TOOL_NAME" != "Write" ]; then exit 0; fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')

# Python 파일인 경우 빠른 테스트 실행
if echo "$FILE_PATH" | grep -qE "\.(py)$"; then
  cd "$CWD"

  # server 파일 수정 → server 테스트
  if echo "$FILE_PATH" | grep -q "server/"; then
    python3 -m pytest tests/server/ -x -q --tb=line 2>&1 | tail -3 &
  fi

  # analyzer 파일 수정 → analyzer 빠른 테스트 (slow 제외)
  if echo "$FILE_PATH" | grep -q "analyzer/"; then
    python3 -m pytest tests/analyzer/ -x -q --tb=line -m "not slow" 2>&1 | tail -3 &
  fi
fi

exit 0
