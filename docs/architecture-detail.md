# ClimbPost 아키텍처 상세

## 시스템 구성도

```
┌──────────────────────────────────────────────────────────────┐
│                    iOS App (SwiftUI)                         │
│                                                              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│  │  Auth    │  │ Gallery │  │ Upload  │  │ Result  │       │
│  │ Module   │  │ Module  │  │ Module  │  │ Module  │       │
│  └────┬─────┘  └────┬────┘  └────┬────┘  └────┬────┘       │
│       └──────────────┴───────────┴─────────────┘            │
│                      │ APIClient                             │
│                      │ (URLSession)                          │
└──────────────────────┼───────────────────────────────────────┘
                       │ HTTP (localhost:8000)
┌──────────────────────┼───────────────────────────────────────┐
│                 Backend Server (FastAPI)                      │
│                      │                                       │
│  ┌───────┐  ┌───────┴──────┐  ┌──────────┐  ┌───────────┐  │
│  │ Auth  │  │  Upload API  │  │ Clips API│  │ Push API  │  │
│  │Router │  │  /videos/*   │  │ /clips/* │  │ /push/*   │  │
│  └───────┘  └──────────────┘  └──────────┘  └───────────┘  │
│                      │                                       │
│  ┌───────────────────┴───────────────────────────────────┐  │
│  │               SQLite Database                          │  │
│  │  users | gyms | upload_sessions | raw_videos           │  │
│  │  clips | jobs | device_tokens                          │  │
│  └───────────────────────────────────────────────────────┘  │
│                      │                                       │
│  ┌───────────────────┴──────┐  ┌─────────────────────────┐  │
│  │     Job Queue Worker     │  │   Static File Server    │  │
│  │  (poll_jobs → pipeline)  │  │  /storage/* → disk      │  │
│  └──────────────────────────┘  └─────────────────────────┘  │
└──────────────────────┼───────────────────────────────────────┘
                       │ Python import
┌──────────────────────┼───────────────────────────────────────┐
│             Analyzer Pipeline (Python)                        │
│                      │                                       │
│  ┌─────────┐  ┌──────┴──────┐  ┌──────────┐  ┌──────────┐  │
│  │ Clipper │→│ Classifier  │→│ Detector  │→│Identifier│  │
│  │Stage 1  │  │  Stage 2    │  │ Stage 3   │  │ Stage 4  │  │
│  └─────────┘  └─────────────┘  └──────────┘  └──────────┘  │
│       │                                            │         │
│       │         ┌──────────┐                       │         │
│       └────────→│  Editor  │←──────────────────────┘         │
│                 │ Stage 5  │                                 │
│                 └──────────┘                                 │
└──────────────────────────────────────────────────────────────┘
```

---

## iOS 앱 구조

```
ios/ClimbPost/
├── App/
│   ├── ClimbPostApp.swift      # @main 진입점, AppDelegate (Push)
│   ├── ContentView.swift       # 인증 분기 (Login ↔ MainView)
│   └── DemoFlowView.swift      # 데모용 탭 뷰 (개발 전용)
│
├── Auth/
│   ├── LoginView.swift         # 로그인 화면 (Apple/Google)
│   ├── AuthService.swift       # OAuth 토큰 처리
│   └── AuthState.swift         # @Published 인증 상태
│
├── Common/
│   ├── APIClient.swift         # HTTP 클라이언트 (모든 서버 API 호출)
│   ├── Models.swift            # Codable 모델 (서버 응답 매핑)
│   ├── KeychainHelper.swift    # JWT 토큰 Keychain 저장
│   ├── Config.swift            # 서버 URL (#if DEBUG → localhost)
│   └── Theme.swift             # 디자인 시스템 (AppColor, AppFont)
│
├── Gallery/
│   ├── GalleryView.swift       # 영상 목록 + 선택 UI
│   ├── GalleryService.swift    # PHAsset 스캔 + GPS 매칭
│   └── GymDatabase.swift       # gyms.json 로드 + GPS 거리 계산
│
├── Upload/
│   ├── UploadView.swift        # 업로드 진행 UI (원형 프로그레스)
│   ├── UploadService.swift     # PHAsset export → 서버 multipart 업로드
│   └── UploadState.swift       # @Published 업로드 상태
│
├── Result/
│   ├── AnalysisWaitingView.swift  # 분석 대기 화면 (폴링 + 단계 표시)
│   ├── ResultView.swift        # 클립 그리드 + 필터 (난이도/결과/내 클립)
│   ├── ResultViewModel.swift   # 클립 데이터 fetch + 필터 로직
│   ├── ClipDetailView.swift    # 영상 재생 + 메타데이터 카드
│   └── Clip+Hashable.swift     # Clip 모델 Hashable 확장
│
├── Share/
│   ├── CarouselView.swift      # 캐러셀 구성 (선택 + 순서)
│   └── ShareService.swift      # 카메라롤 저장 + 인스타그램 공유
│
├── Push/
│   └── PushManager.swift       # APNs 등록 + 푸시 딥링크
│
└── Resources/
    ├── gyms.json               # 암장 GPS 데이터베이스
    └── color_maps/
        └── gym_001.json        # 테이프 색상 → 난이도 매핑
```

### 네비게이션 플로우
```
LoginView → ContentView → MainView
                            ├→ GalleryView → UploadView → AnalysisWaitingView → ResultView
                            │                                                      ├→ ClipDetailView
                            │                                                      └→ CarouselView
                            └→ ResultView (최근 세션 탭 or 푸시 딥링크)
```

### 디자인 시스템
- **브랜드 컬러**: 코랄 `#FF6B35` (accent), 다크 네이비 `#1A1A2E` (background)
- **폰트**: SF Rounded (heroTitle 36pt, sectionTitle 20pt, cardTitle 16pt)
- **버튼**: `PrimaryButtonStyle` — 코랄 배경, 흰 텍스트, press 스케일 애니메이션
- **전체 UI**: 한국어 (타겟: 한국 클라이머)

---

## 서버 구조

```
server/
├── main.py                     # FastAPI 앱 + lifespan + StaticFiles 마운트
├── config/
│   └── settings.py             # 환경변수 설정 (DB, JWT, Storage 경로)
├── auth/
│   ├── router.py               # POST /auth/login, /refresh, GET /me
│   └── service.py              # Apple/Google 토큰 검증, JWT 발급
├── api/
│   ├── upload.py               # POST /videos/sessions, /upload, /start-analysis
│   ├── clips.py                # GET /clips, /clips/{id}, /clips/{id}/video
│   └── analysis.py             # GET /analysis/{session_id}/status
├── queue/
│   └── worker.py               # 백그라운드 작업 큐 (poll_jobs → _real_analyze)
├── push/
│   └── service.py              # POST /push/register, APNs HTTP/2 발송
└── db/
    ├── database.py             # SQLAlchemy engine + session
    ├── models.py               # 7개 테이블 ORM 모델
    └── schemas.py              # Pydantic request/response 모델
```

### API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| POST | /auth/login | 소셜 로그인 (Apple/Google) |
| POST | /auth/refresh | JWT 갱신 |
| GET | /auth/me | 현재 유저 정보 |
| POST | /videos/sessions | 업로드 세션 생성 |
| POST | /videos/upload/{sid} | 영상 파일 업로드 |
| POST | /videos/sessions/{sid}/start-analysis | 분석 시작 |
| GET | /analysis/{sid}/status | 분석 진행 상태 |
| GET | /clips | 클립 목록 (필터: session_id, difficulty, result, is_me) |
| GET | /clips/{id} | 클립 상세 |
| GET | /clips/{id}/video | 클립 영상 스트리밍 |
| POST | /push/register | 디바이스 토큰 등록 |
| GET | /health | 헬스체크 |
| GET | /storage/* | 정적 파일 서빙 (썸네일, 클립, 편집본) |

### 데이터베이스 스키마

| 테이블 | 주요 컬럼 | 설명 |
|--------|----------|------|
| users | id, email, provider | 유저 (Apple/Google) |
| gyms | id, name, lat, lng, color_map | 암장 GPS + 색상 매핑 |
| upload_sessions | id, user_id, gym_id, status | 업로드 세션 |
| raw_videos | id, session_id, file_url | 원본 영상 |
| clips | id, difficulty, result, is_me, urls... | 분석된 클립 |
| jobs | id, session_id, status | 분석 작업 큐 |
| device_tokens | id, user_id, token | APNs 푸시 토큰 |

---

## 분석 파이프라인 구조

```
analyzer/
├── pipeline/
│   ├── orchestrator.py         # Pipeline 클래스 (스테이지 순차 실행)
│   ├── base_stage.py           # BaseStage ABC (process 인터페이스)
│   └── context.py              # PipelineContext, RawVideoInfo, ClipInfo
├── clipper/
│   └── clipper.py              # Stage 1: 등반 구간 감지 + 클립 추출
├── classifier/
│   └── classifier.py           # Stage 2: 완등/실패 판별
├── detector/
│   └── detector.py             # Stage 3: 테이프 색상 → 난이도
├── identifier/
│   └── identifier.py           # Stage 4: "나" 식별 (클러스터링)
├── editor/
│   └── editor.py               # Stage 5: 3:4 크롭 + 60초 트림
├── config/
│   └── settings.py             # 파이프라인 설정 + 스테이지 목록
└── models/                     # AI 모델 파일 (placeholder)
```

### 파이프라인 데이터 흐름

```
PipelineContext 입력:
  session_id, gym_id, color_map, raw_videos[]

Stage 1 — Clipper:
  raw_videos[] → clips[] (start/end 시간, clip 파일, 썸네일)
  방법: MediaPipe Pose로 사람 y좌표 추적
        y < 0.55 = 등반 중, y > 0.65 = 휴식
        5초 이상 휴식 → 구간 종료

Stage 2 — Classifier:
  clips[].result = "success" | "fail"
  방법: 전체 클립의 y좌표 분석
        min(y) < 0.40 = 높이 올라감 → success
        급격한 하강(dy > 0.20) → fail

Stage 3 — Detector:
  clips[].difficulty, clips[].tape_color
  방법: 손목 ROI에서 HSV 색상 분석
        피부색 필터링 후 지배적 색상 감지
        color_map으로 한국어 색상 → 난이도 매핑

Stage 4 — Identifier:
  clips[].is_me = true | false
  방법: 상체 HSV 히스토그램 + 체형 비율 추출
        DBSCAN 클러스터링 → 최대 클러스터 = "나"

Stage 5 — Editor:
  clips[].edited_path
  방법: FFmpeg로 3:4 크롭 (1080x1440) + 60초 트림
```

---

## 테스트 구조

```
tests/
├── conftest.py                 # 최상위 공유 fixture
├── pytest.ini                  # 테스트 설정 + slow 마커
├── test_integration.py         # E2E: 업로드 → 분석 → 클립 조회 (12 tests)
├── server/
│   ├── conftest.py             # 인메모리 SQLite + TestClient
│   ├── test_auth.py            # 인증 API (5 tests)
│   ├── test_upload.py          # 업로드 API (6 tests)
│   ├── test_clips.py           # 클립 API (7 tests)
│   ├── test_analysis.py        # 분석 상태 API (4 tests)
│   ├── test_push.py            # 푸시 API (3 tests)
│   ├── test_models.py          # DB 모델 (6 tests)
│   └── test_worker.py          # Mock 분석 워커 (2 tests)
└── analyzer/
    ├── conftest.py             # test2.mov 경로 + 공유 fixture
    ├── test_context.py         # 데이터 클래스 (3 tests)
    ├── test_orchestrator.py    # 파이프라인 오케스트레이터 (5 tests)
    ├── test_clipper.py         # Clipper 스테이지 (6 tests, 4 slow)
    ├── test_classifier.py      # Classifier 스테이지 (6 tests)
    ├── test_detector.py        # Detector 스테이지 (8 tests)
    ├── test_identifier.py      # Identifier 스테이지 (4 tests)
    ├── test_editor.py          # Editor 스테이지 (5 tests, 4 slow)
    └── test_full_pipeline.py   # 풀 파이프라인 (1 slow test)

총 83 tests | 서버 45 | 분석기 38
```

---

## 파일 저장 규칙

```
data/storage/
├── raw/{session_id}/           # 원본 업로드 영상
│   └── video_name.mov
├── {session_id}/clips/         # 분석된 클립 + 썸네일
│   ├── {clip_id}.mp4
│   └── {clip_id}_thumb.jpg
└── edited/{session_id}/        # 3:4 편집본
    └── {clip_id}_edited.mp4
```

DB에는 `/storage/...` 형태의 상대 URL이 저장되고,
서버의 `StaticFiles` 마운트로 `http://localhost:8000/storage/...` 로 HTTP 접근 가능.
