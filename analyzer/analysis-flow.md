# 분석 서버 요청/처리 흐름

> 다이어그램: `analysis-flow.excalidraw`

---

## 아키텍처 개요

```
Server (:8000)                         Analyzer (:8001, GPU)
  worker.py                              api/router.py
  _real_analyze()  ──POST /jobs──►       api/jobs.py  JobQueue
                   ◄─202 job_id──        pipeline/orchestrator.py
                   ──GET /jobs/{id}─►        Stage 1: Clipper     40%
                   ◄─{status,pct}──         Stage 2: Classifier  10%
                      (5s 간격 폴링)          Stage 3: Detector    15%
                   ──GET /jobs/{id}/result►  Stage 4: Identifier   5%
                   ◄─{clips:[...]}──         Stage 5: Editor       30%
                        │
                        ▼
                    DB 저장 (Clip 레코드)
```

---

## 1. Server → Analyzer 요청 준비 (`server/queue/worker.py`)

### `_real_analyze(job, db)`

| 단계 | 동작 |
|------|------|
| ① DB 조회 | `RawVideo`, `UploadSession`, `Gym` 레코드 조회 |
| ② color_map 로드 | DB Gym.color_map → 없으면 `data/color_maps/{gym_id}.json` 폴백 |
| ③ 경로 변환 | `file_url` (`/storage/raw/...`) → 절대경로 (`{STORAGE_ROOT}/raw/...`) |
| ④ duration 보정 | `rv.duration_sec`이 없으면 `ffprobe`로 실측 |
| ⑤ payload 구성 | session_id, gym_id, color_map, raw_videos[], pipeline_config |

### payload 예시

```json
{
  "session_id": "abc123",
  "gym_id": "gym_001",
  "color_map": {"mapping": {"노랑": "V0-V1", "파랑": "V4-V5"}},
  "raw_videos": [
    {"raw_video_id": "rv-001", "file_path": "/data/storage/raw/abc123/climb.mov", "duration_sec": 142.5}
  ],
  "storage_root": "/data/storage",
  "pipeline_config": {
    "clipper":    {"motion_threshold": 0.04, "still_frames": 6, "min_climb_sec": 10},
    "classifier": {"top_zone_ratio": 0.30, "hold_frames": 1, "fall_dy_threshold": 0.20},
    "detector":   {"min_saturation": 30, "max_samples": 20}
  }
}
```

---

## 2. HTTP 통신 계층

### 요청 흐름 (httpx.AsyncClient, timeout=30s)

```
POST  {ANALYZER_URL}/jobs          → 202 Accepted  {"job_id": "job_abc..."}
GET   {ANALYZER_URL}/jobs/{job_id} → 200 {"status": "processing", "progress_pct": 40, ...}
      (5초 간격, 최대 360회 = 30분)
GET   {ANALYZER_URL}/jobs/{job_id}/result → 200 {"clips": [...], "elapsed_sec": 38.2}
```

### 상태 전이

```
queued ──► processing ──► completed
                     └──► failed
                     └──► cancelled
```

### 타임아웃 체인

| 레이어 | 값 |
|--------|---|
| httpx AsyncClient | 30s (접속/헤더 수신) |
| 폴링 최대 대기 | 30분 (360 × 5s) |
| uvicorn keep-alive | 620s |

---

## 3. Analyzer API 레이어 (`analyzer/api/`)

### `router.py` 엔드포인트

| 메서드 | 경로 | 동작 |
|--------|------|------|
| POST | `/jobs` | `job_queue.submit(req)` → JobState 반환 (202) |
| GET | `/jobs/{job_id}` | `job_queue.get_status(job_id)` → status/progress |
| GET | `/jobs/{job_id}/result` | status=completed일 때만 clips 반환 (409 otherwise) |
| DELETE | `/jobs/{job_id}` | queued 상태만 취소 가능 |
| GET | `/health` | `{"status":"ok","gpu":true,"queue_size":0,"active_job":null}` |

### `jobs.py` JobQueue

- `asyncio.Queue` 기반 FIFO 단일 워커
- `JobState` 필드: `job_id`, `session_id`, `status`, `progress_pct`, `current_stage`, `stages_completed`, `result`, `error`, `created_at`, `started_at`
- 파이프라인은 `loop.run_in_executor(None, ...)` — 별도 스레드에서 실행 (event loop 블로킹 방지)
- `progress_callback(stage_name, pct)` → 폴링 응답에 실시간 반영

---

## 4. 파이프라인 5단계 (`analyzer/pipeline/`)

### Stage 1 — Clipper (40%)
**파일**: `clipper/clipper.py`

| 항목 | 내용 |
|------|------|
| 모델 | YOLOv8m-pose (`yolov8m-pose.pt`) |
| 샘플링 | 1 fps |
| 등반 판정 | `center_y < climb_threshold(0.55)` |
| 휴식 판정 | `center_y > rest_threshold(0.65)` 또는 미검출 |
| 구간 종료 | `gap_sec=5` 동안 휴식 상태 지속 |
| 클립 추출 | FFmpeg `-ss {start} -t {duration} -c copy` |
| 썸네일 | 클립 중간 프레임 JPEG 추출 |
| 출력 | `/data/storage/{session_id}/clips/{clip_id}.mp4` + `{clip_id}_thumb.jpg` |

**center_y 계산**: COCO keypoints 5,6(어깨),11,12(엉덩이)의 평균 y (정규화, confidence > 0.3)

### Stage 2 — Classifier (10%)
**파일**: `classifier/classifier.py`

| 항목 | 내용 |
|------|------|
| 분석 구간 | 클립 마지막 `tail_seconds=3`초 |
| 샘플링 | 2 fps |
| success 조건 | `min_y < 0.40` (벽 상단 도달) |
| success 조건 | `last_y < first_y - 0.05` (끝이 시작보다 높음) |
| success 조건 | `last_y < 0.50` (최종 위치가 상반부) |
| fail 조건 | `dy > fall_dy_threshold(0.15)` 급락 감지 |
| 출력 | `clip.result = "success"` or `"fail"` |

### Stage 3 — Detector (15%)
**파일**: `detector/detector.py`

| 항목 | 내용 |
|------|------|
| 샘플링 | 1 fps, 최대 20프레임 |
| 손 위치 | COCO keypoints 9(왼손목), 10(오른손목), confidence > 0.3 |
| ROI | 손목 중심 ± `roi_pad_ratio=20%` 패딩 |
| 색상 분석 | HSV 변환 → 채도≥30, 명도≥50 픽셀만 추출 |
| 피부 제외 | Hue 0~20, Sat 30~170, Val≥80 마스크로 제외 |
| 색상표 | 노랑(H:20~35), 초록(H:36~85), 파랑(H:86~130), 빨강(wrap), 검정(저명도) |
| 투표 | 프레임별 keypoint confidence 가중 누적 투표 |
| 출력 | `clip.tape_color`, `clip.difficulty` (color_map 매핑) |

### Stage 4 — Identifier (5%)
**파일**: `identifier/identifier.py`

| 항목 | 내용 |
|------|------|
| 알고리즘 | DBSCAN 클러스터링 |
| 목적 | 같은 루트(색상+위치)의 클립 그룹화 |
| 출력 | `clip.is_me` (본인 등반 여부 판정) |

### Stage 5 — Editor (30%)
**파일**: `editor/editor.py`

| 항목 | 내용 |
|------|------|
| 문제 | iPhone이 BT.2020/HLG 10-bit HDR로 촬영 → iOS AVPlayer에서 검정/과노출 |
| 변환 | HDR → SDR: `colorspace=all=bt709:iall=bt2020:format=yuv420p` |
| BSF | `h264_metadata` Bitstream Filter 적용 |
| 출력 | `/data/storage/{session_id}/edited/{clip_id}_edited.mp4` |

---

## 5. 결과 반환 및 DB 저장

### Analyzer 응답

```json
{
  "session_id": "abc123",
  "clips": [
    {
      "clip_id": "a1b2c3d4e5f6",
      "raw_video_id": "rv-001",
      "start_time": 12.4,
      "end_time": 67.1,
      "duration_sec": 54.7,
      "clip_path": "/data/storage/abc123/clips/a1b2c3d4e5f6.mp4",
      "thumbnail_path": "/data/storage/abc123/clips/a1b2c3d4e5f6_thumb.jpg",
      "difficulty": "V4-V5",
      "tape_color": "파랑",
      "result": "success",
      "is_me": true,
      "edited_path": "/data/storage/abc123/edited/a1b2c3d4e5f6_edited.mp4"
    }
  ],
  "elapsed_sec": 38.2
}
```

### Server DB 저장 (`worker.py`)

- 절대경로 → `/storage/` URL 변환: `os.path.relpath(abs_path, STORAGE_ROOT)` → `f"/storage/{rel}"`
- `Clip` 레코드 생성: `clip_url`, `thumbnail_url`, `edited_url`, `difficulty`, `tape_color`, `result`, `is_me`

---

## 6. 공유 볼륨 구조

```
climbpost_data:/data/
  ├── climbpost.db              ← server 전용 SQLite
  └── storage/
       ├── raw/{session_id}/   ← 업로드 원본 (iOS → server)
       ├── clips/{session_id}/ ← 클립 + 썸네일 (analyzer 생성)
       ├── edited/{session_id}/← HDR→SDR 변환본 (analyzer 생성)
       └── thumbnails/         ← (레거시 경로)
```

server와 analyzer가 동일 볼륨 마운트 → 파일 복사 없이 경로로 직접 공유.

---

## 7. MOCK_ANALYSIS 모드

`MOCK_ANALYSIS=true` 환경변수 시 `_mock_analyze()` 호출.
HTTP 요청 없이 가짜 클립 데이터를 즉시 DB에 삽입. analyzer 컨테이너 불필요.

```bash
docker compose up server   # analyzer 없이 mock 모드로 server만 기동
```
