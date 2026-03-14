# ClimbPost (클라임포스트)

> 클라이밍 영상 자동 편집 & 인스타그램 업로드 앱

클라이밍장에서 찍은 영상만 있으면, 나머지는 앱이 전부 알아서 해줍니다.

## 프로젝트 개요

ClimbPost는 클라이밍 영상을 자동으로 분석하고, 인스타그램에 올릴 수 있는 캐러셀로 편집해주는 서비스입니다.

**핵심 기능:**
- 갤러리에서 당일 클라이밍 영상 자동 감지 (GPS 기반)
- AI가 클라이밍 구간만 자동 클리핑
- 성공/실패 자동 판별 & 난이도 자동 태깅
- 인스타그램 캐러셀용 자동 편집
- Share Sheet로 인스타 앱에 바로 전달

## 기술 스택

| 구성 | 기술 |
|------|------|
| iOS 앱 | Swift |
| Backend API | TBD |
| 분석 서버 | Python, GPU |
| DB | TBD |
| 코드 관리 | GitHub (public) |

## 레포지토리 구조

```
climbpost/
├── docs/           # 기획서, 프롬프트 기록
├── ios/            # iOS 앱 (Swift)
├── server/         # Backend API
├── analyzer/       # 분석 서버 (GPU)
├── data/           # 암장 GPS DB, 색상-난이도 매핑
└── scripts/        # 유틸 스크립트
```

## 문서

- [종합 기획서](docs/planning.md)
- [PHASE 1 기능 명세서](docs/phase1-spec.md)
- [시스템 아키텍처](docs/architecture.md)

## 개발 방식

- **바이브코딩** — AI 에이전트에게 최대한 위임
- **1 prompt = 1 commit** — 프롬프트 기록을 GitHub에서 관리
- 기술적인 선택은 AI에게 맡긴다

## 마일스톤

- **PHASE 1** (3주): 전체 파이프라인 + 필수 기능
- **PHASE 2**: 편집 기능 고도화
- **PHASE 3**: 분석·크롤링 기능 확장

## GitHub

- Repository: [Go-MinSeong/ClimbPost](https://github.com/Go-MinSeong/ClimbPost)
