# ClimbPost 실행 가이드

## 사전 요구사항

| 항목 | 버전 | 확인 명령어 |
|------|------|-----------|
| macOS | 15.0+ | `sw_vers` |
| Python | 3.9+ | `python3 --version` |
| Xcode | 16.0+ | `xcodebuild -version` |
| XcodeGen | 2.0+ | `xcodegen --version` |
| FFmpeg | 4.0+ | `ffmpeg -version` |
| Homebrew | - | `brew --version` |

### 설치 (없는 경우)

```bash
# XcodeGen
brew install xcodegen

# FFmpeg
brew install ffmpeg

# Python 패키지 (서버)
pip3 install fastapi uvicorn sqlalchemy pyjwt python-jose python-multipart httpx cryptography

# Python 패키지 (분석 엔진)
pip3 install mediapipe opencv-python numpy scikit-learn Pillow

# Python 패키지 (테스트)
pip3 install pytest pytest-asyncio httpx
```

---

## 1단계: 서버 실행

```bash
cd /path/to/climbPost

# 방법 A: Mock 분석 모드 (GPU 없이 iOS 개발용, 가짜 결과 생성)
MOCK_ANALYSIS=true python3 -m uvicorn server.main:app --host 0.0.0.0 --port 8000

# 방법 B: 실제 분석 파이프라인 (MediaPipe + FFmpeg 필요)
python3 -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

### 서버 확인

```bash
# 헬스체크
curl http://localhost:8000/health
# → {"status":"ok"}

# Swagger UI
open http://localhost:8000/docs
```

### 테스트 유저 생성 (최초 1회)

```bash
python3 -c "
from server.db.database import SessionLocal, create_tables
from server.db.models import User, Gym
import json

create_tables()
db = SessionLocal()
user = User(id='dev-user-001', provider='apple', email='test@climbpost.com')
db.add(user)
gym = Gym(
    id='gym_001', name='더클라임 강남',
    latitude=37.4967, longitude=127.0276,
    color_map=json.dumps({
        'gym_id': 'gym_001',
        'mapping': {'노랑':'V0-V1','초록':'V2-V3','파랑':'V4-V5','빨강':'V6-V7','검정':'V8+'}
    })
)
db.add(gym)
db.commit()
db.close()
print('Done')
"
```

---

## 2단계: iOS 앱 실행

```bash
cd ios

# Xcode 프로젝트 생성
xcodegen generate --spec project.yml

# Xcode에서 열기
open ClimbPost.xcodeproj
```

### Xcode 설정
1. **Scheme**: ClimbPost
2. **Destination**: iPhone 16 / iPhone 17 Pro (시뮬레이터)
3. **⌘R** 로 실행

### 시뮬레이터 CLI 실행 (Xcode 없이)

```bash
# 빌드
xcodebuild -project ClimbPost.xcodeproj -scheme ClimbPost \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  -configuration Debug build

# 설치 + 실행
APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData -name "ClimbPost.app" \
  -path "*/Debug-iphonesimulator/*" | head -1)
xcrun simctl install "iPhone 17 Pro" "$APP_PATH"
xcrun simctl launch "iPhone 17 Pro" com.climbpost.app

# 시뮬레이터 앱 열기
open -a Simulator
```

### 시뮬레이터에 테스트 영상 추가

```bash
# 시뮬레이터 사진 라이브러리에 영상 추가
xcrun simctl addmedia "iPhone 17 Pro" /path/to/video1.mov /path/to/video2.mov
```

> **참고**: 시뮬레이터 빌드는 `#if targetEnvironment(simulator)` 로 자동 로그인 + 사진 권한 바이패스가 활성화됩니다.

---

## 3단계: 전체 플로우 테스트

### 앱 내 유저 플로우
```
1. 홈 화면 → "오늘의 영상 스캔" 탭
2. 갤러리 → 클라이밍 영상이 자동 감지됨 (GPS 매칭)
3. 영상 선택 → "업로드" 탭
4. 확인 다이얼로그 → "업로드 시작"
5. 업로드 진행 (원형 프로그레스)
6. 업로드 완료 → "결과 보기"
7. 분석 대기 (단계별 프로그레스 + 메시지)
8. 분석 완료 → 자동으로 결과 화면 이동
9. 클립 그리드 (썸네일 + 난이도 뱃지 + 완등/실패)
10. 클립 탭 → 영상 재생 + 메타데이터
11. "공유할 클립 선택" → 캐러셀 구성
12. "인스타그램에 공유" → 카메라롤 저장 + 인스타 앱 실행
```

### API 직접 테스트 (curl)

```bash
# JWT 토큰 생성
TOKEN=$(python3 -c "from server.auth.service import create_jwt; print(create_jwt('dev-user-001'))")

# 세션 생성
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"gym_id":"gym_001"}' \
  http://localhost:8000/videos/sessions

# 영상 업로드
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/video.mov" \
  http://localhost:8000/videos/upload/{session_id}

# 분석 시작
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/videos/sessions/{session_id}/start-analysis

# 분석 상태 확인
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/analysis/{session_id}/status

# 클립 목록
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/clips?session_id={session_id}
```

---

## 4단계: 테스트 실행

```bash
cd /path/to/climbPost

# 전체 테스트 (83개)
python3 -m pytest tests/ -v

# 빠른 테스트만 (74개, 영상 처리 제외)
python3 -m pytest tests/ -v -m "not slow"

# 서버 테스트만
python3 -m pytest tests/server/ -v

# 분석 엔진 테스트만
python3 -m pytest tests/analyzer/ -v

# 통합 테스트만
python3 -m pytest tests/test_integration.py -v
```

---

## 문제 해결

### 서버가 안 뜸
```bash
# 포트 충돌 확인
lsof -i :8000
# 프로세스 종료
pkill -f "uvicorn server.main"
```

### 시뮬레이터에서 네트워크 에러
- 서버가 `http://localhost:8000`에서 실행 중인지 확인
- iOS는 `Config.swift`에서 `#if DEBUG` → `http://localhost:8000` 사용

### 분석이 안 됨 / 클립 0개
- MediaPipe, OpenCV, FFmpeg 설치 확인
- 영상이 클라이밍 영상인지 확인 (사람 포즈 감지 필요)
- 로그 확인: 서버 콘솔 출력에 `Clipper: found N raw segment(s)` 메시지

### 썸네일/영상 안 보임
- 서버의 정적 파일 서빙 확인: `curl http://localhost:8000/storage/` → 파일 목록
- DB의 URL이 `/storage/...` 형태인지 확인 (절대 경로이면 안 됨)

### Xcode 빌드 에러
```bash
# 프로젝트 재생성
cd ios && xcodegen generate --spec project.yml

# 클린 빌드
xcodebuild clean -project ClimbPost.xcodeproj -scheme ClimbPost
```
