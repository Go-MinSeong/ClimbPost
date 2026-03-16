# Analyzer Service REST API

Base URL: `http://localhost:8001` (dev) / `http://analyzer:8001` (Docker)

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | GPU status, queue size |
| `POST` | `/jobs` | Submit analysis job (202) |
| `GET` | `/jobs/{job_id}` | Job progress/status |
| `GET` | `/jobs/{job_id}/result` | Final result clips |
| `DELETE` | `/jobs/{job_id}` | Cancel job |

---

## GET /health

**Response 200**
```json
{
  "status": "ok",
  "gpu": true,
  "gpu_name": "NVIDIA GeForce RTX 3080",
  "queue_size": 2,
  "active_job": "job_abc123"
}
```

---

## POST /jobs

**Request**
```json
{
  "session_id": "abc123",
  "gym_id": "gym_001",
  "color_map": {
    "mapping": {
      "노랑": "V0-V1",
      "초록": "V2-V3",
      "파랑": "V4-V5",
      "빨강": "V6-V7",
      "검정": "V8+"
    }
  },
  "raw_videos": [
    {
      "raw_video_id": "vid_001",
      "file_path": "/data/storage/raw/abc123/video.mov",
      "duration_sec": 300.0
    }
  ],
  "storage_root": "/data/storage",
  "pipeline_config": {
    "clipper": { "min_climb_sec": 10 },
    "classifier": { "fall_dy_threshold": 0.20 },
    "detector": { "min_saturation": 30 }
  }
}
```

**Response 202 Accepted**
```json
{
  "job_id": "job_xyz789",
  "status": "queued",
  "created_at": "2026-03-16T10:00:00Z"
}
```

---

## GET /jobs/{job_id}

**Response 200**
```json
{
  "job_id": "job_xyz789",
  "session_id": "abc123",
  "status": "processing",
  "progress_pct": 60,
  "current_stage": "detector",
  "stages_completed": ["clipper", "classifier"],
  "created_at": "2026-03-16T10:00:00Z",
  "started_at": "2026-03-16T10:00:01Z",
  "error": null
}
```

**status values:** `queued` | `processing` | `completed` | `failed` | `cancelled`

**Response 404**
```json
{ "detail": "Job not found" }
```

---

## GET /jobs/{job_id}/result

**Response 200** (status == completed)
```json
{
  "job_id": "job_xyz789",
  "session_id": "abc123",
  "clips": [
    {
      "clip_id": "clip_a1b2c3",
      "raw_video_id": "vid_001",
      "start_time": 45.2,
      "end_time": 78.5,
      "duration_sec": 33.3,
      "clip_path": "/data/storage/clips/abc123/clip_a1b2c3.mp4",
      "thumbnail_path": "/data/storage/thumbnails/abc123/clip_a1b2c3.jpg",
      "edited_path": "/data/storage/edited/abc123/clip_a1b2c3.mp4",
      "difficulty": "V2-V3",
      "tape_color": "초록",
      "result": "success",
      "is_me": true
    }
  ],
  "elapsed_sec": 45.3
}
```

**Response 409** (not yet complete)
```json
{ "detail": "Job not completed yet", "status": "processing" }
```

---

## DELETE /jobs/{job_id}

**Response 200**
```json
{ "cancelled": true }
```

Returns `{ "cancelled": false }` if job is already processing or completed.

---

## Stage Progress Weights

| Stage | Weight | Cumulative |
|-------|--------|-----------|
| clipper | 40% | 40% |
| classifier | 10% | 50% |
| detector | 15% | 65% |
| identifier | 5% | 70% |
| editor | 30% | 100% |

---

## Development

```bash
# Start dev container with hot reload
docker compose -f docker-compose.dev.yml up analyzer

# Health check
curl http://localhost:8001/health

# Submit job
curl -X POST http://localhost:8001/jobs \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test","gym_id":"gym_001","color_map":{"mapping":{}},"raw_videos":[]}'

# Poll status
curl http://localhost:8001/jobs/{job_id}

# Get result
curl http://localhost:8001/jobs/{job_id}/result
```
