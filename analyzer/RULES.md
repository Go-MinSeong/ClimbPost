# Analyzer 개발 규칙

이 파일은 analyzer 서비스 개발 시 반드시 지켜야 할 규칙을 정의합니다.

---

## 1. 모델 추론 — ONNX + GPU

- **모든 ML 모델은 ONNX 포맷으로 변환**하여 사용한다.
- 추론 런타임: `onnxruntime-gpu` (CUDA EP)
- PyTorch `.pt` / `.pth` 파일을 직접 로드하는 코드는 production 코드에 허용하지 않는다.
- 모델 파일 위치: `analyzer/models/` (`.onnx` 파일)
- 모델 변환 스크립트: `analyzer/models/export_*.py` 형태로 관리

### ONNX 추론 표준 패턴

```python
import onnxruntime as ort

# GPU 세션 (CUDA EP 우선, CPU 폴백)
providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
session = ort.InferenceSession("analyzer/models/model.onnx", providers=providers)
```

- 세션은 **모듈 로드 시 1회만 초기화** (매 프레임마다 재생성 금지)
- 단일 GPU이므로 세션 간 GPU 메모리 충돌 방지를 위해 스테이지별로 세션을 명시적으로 관리

---

## 2. GPU 자원 관리 — 단일 워커 큐

- **GPU는 1개**이므로 동시 추론은 허용하지 않는다.
- 백엔드 서버로부터 복수 작업 요청이 들어오면 **FIFO 큐에 대기**시키고, 한 번에 하나의 작업만 실행한다.
- 구현체: `analyzer/api/jobs.py` → `JobQueue` (asyncio.Queue 기반 단일 워커)
- 파이프라인 실행은 `loop.run_in_executor(None, ...)` 로 별도 스레드에서 수행 (event loop 블로킹 방지)
- 큐 상태는 `/health` 엔드포인트로 확인 가능 (`queue_size`, `active_job`)

---

## 3. 개발 및 테스트 환경 — 컨테이너

- **모든 개발 테스트는 컨테이너 안에서 실행**한다.
- 컨테이너 정의: `Dockerfile.analyzer`
- 컨테이너 실행: `docker compose up analyzer`
- GPU 패스스루: `docker-compose.yml`의 `deploy.resources.reservations.devices` (NVIDIA)

### 테스트 영상

- 위치: `data/test-data/data-1.mov`
- 컨테이너 내 경로: `/data/test-data/data-1.mov` (볼륨 마운트)
- 모든 파이프라인 테스트는 이 영상을 사용한다.

### 테스트 실행

```bash
# 컨테이너 진입 후 테스트
docker compose run --rm analyzer pytest tests/analyzer/ -v

# 단일 스테이지 테스트
docker compose run --rm analyzer pytest tests/analyzer/test_clipper.py -v
```

---

## 4. 코드 구조 규칙

- 각 스테이지는 `BaseStage`를 상속하고 `process(context)` 메서드만 외부에 노출한다.
- ONNX 세션은 스테이지 클래스의 `__init__` 에서 1회 로드한다.
- 설정값은 `config/settings.py` 에서 관리하고, 스테이지는 `self.config.get(stage_name, {})` 로 오버라이드를 받는다.
- FFmpeg 호출은 `subprocess.run(check=True)` 로 에러를 명시적으로 처리한다.

---

## 5. 개발 워크플로우 규칙

- **1 prompt = 1 commit**: 하나의 프롬프트(대화 턴)에서 완료된 작업은 반드시 하나의 커밋으로 마무리한다.
- 커밋 전 관련 테스트가 통과해야 한다 (컨테이너 내 실행).
- 커밋 메시지는 conventional commits 형식을 따른다 (`feat:`, `fix:`, `refactor:` 등).

---

## 6. 금지 사항

| 금지 | 이유 |
|------|------|
| `ultralytics.YOLO()` 직접 로드 | PyTorch 의존성, ONNX로 대체 |
| 스테이지 내 `YOLO()` 반복 초기화 | 매번 모델 로드로 성능 저하 |
| 동시 GPU 추론 | 단일 GPU 충돌 |
| 호스트 환경에서 파이프라인 테스트 | 재현성 보장 불가, 컨테이너 사용 |
