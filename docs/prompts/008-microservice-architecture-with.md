# 008 — feat(analyzer): microservice architecture with async Job API and YOLOv8-pose

- **날짜**: %Y->- (HEAD -> feat/analyzer-microservice)
- **소요시간**: 37분
- **커밋**: `7df8118` feat(analyzer): microservice architecture with async Job API and YOLOv8-pose

## 프롬프트

```
[2026-03-16 22:52:19] /home/climbpost/ClimbPost에서 분석 서버 작업을 진행할거야. /home/climbpost/ClimbPost/analyzer
백엔드 서비스와의 RestAPI 문서를 작성해야하고, 실제 분석 서버가 어떻게 동작할지 계획을 같이 세워보자.
[2026-03-16 22:53:54] /home/climbpost/ClimbPost에서 분석 서버 작업을 진행할거야. /home/climbpost/ClimbPost/analyzer                                             
백엔드 서비스와의 RestAPI 문서를 작성해야하고, 실제 분석 서버가 어떻게 동작할지 계획을 같이 세워보자. 
프론트, 백엔트, 분석서버는 마이크로 서비스로 각 컨테이너를 띄워서 통신을 진행할거야.
개발용 분석서버 띄우는 도커 컴포즈 파일을 작성하고 내부에서 개발을 진행하자. GPU를 활용해야하므로 포함해서 컨테이너를 띄워야해.
분석서버가 해야할 일들을 나열하고 각 일들을 어떻게 수행할지 구체화하자.
[2026-03-16 23:05:17] Implement the following plan:

# ClimbPost 분석 서버 마이크로서비스 설계

analyzer/를 마이크로서비스로 분리하여 독립 컨테이너로 운영한다. 현재 동기식 POST /analyze 방식을 비동기 Job API로 전환하고, MediaPipe 기반 파이프라인을 YOLOv8-pose 기반으로 개선하여 정확도를 높인다. GPU 개발 환경을 Docker로 구성하여 컨테이너 내에서 hot reload 개발이 가능하도록 한다. 신규/수정 파일: docker-compose.dev.yml, analyzer/api/jobs.py, analyzer/api/router.py, analyzer/pipeline/orchestrator.py, analyzer/clipper/clipper.py, analyzer/classifier/classifier.py, analyzer/detector/detector.py, analyzer/requirements.txt, server/queue/worker.py, docs/api/analyzer-api.md... [+3000chars]
[2026-03-16 23:25:52] [system] background task notification — pytest 바이너리 탐색 완료
[2026-03-16 23:27:03] 3
[2026-03-16 23:31:10] 왜 프롬프트는 추가를 안해? 훅에 사용한 프롬프트는 저장이 있는데
[2026-03-16 23:37:13] 이번에만 현재 세션을 참고해서 채워줘.
[2026-03-16 23:40:19] 현재 업데이트 사항들은 현재 브랜치에 적절히 커밋을 올리고 푸시해줘
[2026-03-16 23:42:20] 입력해뒀어. 이이서 진행
```
