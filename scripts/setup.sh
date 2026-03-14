#!/bin/bash
# ClimbPost 초기 설정 스크립트
echo "ClimbPost 개발 환경 설정을 시작합니다..."

# Python 가상환경 생성 (분석 서버용)
echo "분석 서버 가상환경 생성 중..."
python3 -m venv analyzer/.venv
source analyzer/.venv/bin/activate
echo "설정 완료!"
