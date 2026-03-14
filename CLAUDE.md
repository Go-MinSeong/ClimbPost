# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ClimbPost (클라임포스트) — iOS app that auto-analyzes climbing videos and prepares Instagram carousel posts. Three-tier architecture: iOS (Swift) ↔ Backend API ↔ Analysis Server (Python/GPU).

## Architecture

- **ios/ClimbPost/**: Swift iOS app — Auth, Gallery scanning, Upload, Result preview, Instagram Share Sheet, Push notifications
- **server/**: Backend API — REST endpoints, JWT auth, job queue, APNs, database
- **analyzer/**: Python GPU pipeline — clipper → classifier → detector → identifier → editor (5-stage pipeline)
- **data/**: Gym GPS database (`gyms.json`) and tape color→difficulty mappings (`color_maps/`)

## Key Data Flow

Login → gallery scan (local GPS+date match against gyms.json) → upload → server queues analysis → 5-stage GPU pipeline → push notification → user reviews/filters clips → Instagram share via Share Sheet

## Analysis Pipeline Stages

1. **Clipper**: Extract climbing segments from raw video
2. **Classifier**: Success/fail determination (top hold reached or fall)
3. **Detector**: Tape color recognition → difficulty mapping (V0-V8+)
4. **Identifier**: User identification via appearance clustering (Re-ID)
5. **Editor**: Crop to 3:4 vertical, max 60s per clip

## Development Setup

```bash
# Python analyzer environment
scripts/setup.sh   # creates analyzer/.venv
source analyzer/.venv/bin/activate
```

## Development Philosophy

- **Vibe Coding**: AI agents handle technical decisions, maximize delegation
- **1 prompt = 1 commit** for traceability (실제로는 1 prompt → 멀티에이전트 → 여러 커밋 가능)
- All prompts logged in `docs/prompts/` (NNN-제목.md 형식)
- 커밋 시 `scripts/log-prompt.sh`가 자동으로 프롬프트 로그 템플릿 생성

## Prompt Logging Convention

커밋할 때 반드시 프롬프트 기록을 남긴다:
```
docs/prompts/NNN-제목.md
```
각 파일에는: 날짜, 프롬프트 원문, 커밋 해시, 에이전트 방식, 결과 요약을 기록한다.
멀티에이전트(whip)로 여러 커밋이 생긴 경우 하나의 프롬프트 파일에 모든 커밋을 매핑한다.

## Running the App (Development)

```bash
# 1. Server (MOCK mode for iOS dev without GPU)
cd /path/to/climbPost
MOCK_ANALYSIS=true python3 -m uvicorn server.main:app --port 8000

# 2. Server (REAL pipeline — needs mediapipe, opencv, ffmpeg)
python3 -m uvicorn server.main:app --port 8000

# 3. iOS (Xcode)
cd ios && xcodegen generate --spec project.yml
open ClimbPost.xcodeproj  # Run on simulator

# 4. Tests
python3 -m pytest tests/ -v                    # all 83 tests
python3 -m pytest tests/ -v -m "not slow"      # fast only (74 tests)
```

## Design System

- Brand color: Coral #FF6B35, Dark navy #1A1A2E
- iOS theme: `ios/ClimbPost/Common/Theme.swift` (AppColor, AppFont, PrimaryButtonStyle)
- All UI text in Korean (한국어)

## Constraints

- Fixed camera (tripod) indoor climbing videos only
- Vertical orientation assumed
- ~20 videos per visit, 1-10 min each
- PHASE 1: home network infrastructure (backend + GPU on same machine)

## Documentation

- `docs/planning.md` — master plan, motivation, milestones
- `docs/phase1-spec.md` — detailed PHASE 1 feature spec with acceptance criteria
- `docs/architecture.md` — system architecture, DB schema, network topology
