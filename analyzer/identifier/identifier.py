"""Stage 2 — Identifier: multi-frame OSNet re-ID based clip identification.

Strategy
--------
1. Split each clip into 3 temporal segments (0-33%, 33-66%, 66-100%).
2. In each segment find the best frame:
   - YOLO26n person detection; filter center_y < climb_threshold.
   - Score = confidence × bbox_area_fraction → argmax.
3. Crop the person bbox from each best frame (5% padding).
4. Save 3 thumbnails per clip: {clip_id}_thumb_0/1/2.jpg
   Primary thumbnail used in reports: _thumb_1 (middle segment).
5. Run OSNet re-ID on each crop → embedding vector.
6. L2-normalise and average the (up to 3) embeddings → representative.
7. Cluster representatives with DBSCAN (cosine distance).
8. Largest cluster = 'me'; those clips get is_me=True.
9. Annotate primary thumbnails with ME/other border.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import cv2
import numpy as np
from sklearn.cluster import DBSCAN

from analyzer.pipeline.base_stage import BaseStage
from analyzer.pipeline.context import PipelineContext
from analyzer.pipeline.onnx_infer import (
    load_session,
    preprocess,
    preprocess_reid,
    postprocess_det,
)

logger = logging.getLogger(__name__)

_DET_MODEL_PATH = os.environ.get(
    "YOLO26N_ONNX",
    str(Path(__file__).resolve().parent.parent / "models" / "yolo26n.onnx"),
)
_REID_MODEL_PATH = os.environ.get(
    "OSNET_ONNX",
    str(Path(__file__).resolve().parent.parent / "models" / "osnet_x0_25.onnx"),
)

_DEFAULTS = {
    "sample_fps": 2,           # frames per second to sample within each segment
    "climb_threshold": 0.65,   # center_y < this → person in climbing zone
    "conf_threshold": 0.3,     # minimum detection confidence
    "min_area_frac": 0.005,    # bbox must be ≥ 0.5% of frame area
    "dbscan_eps": 0.35,        # cosine distance threshold (same person ~ < 0.3)
    "dbscan_min_samples": 1,
    "thumbnail_pad": 0.05,     # relative bbox expansion for crop
    "n_segments": 3,           # temporal segments per clip
}


class IdentifierStage(BaseStage):
    """Stage 2 — multi-frame appearance embedding + DBSCAN is_me identification."""

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._det_session = load_session(_DET_MODEL_PATH)
        self._reid_session = load_session(_REID_MODEL_PATH)
        inp = self._det_session.get_inputs()[0].shape
        self._infer_h = inp[2] if isinstance(inp[2], int) else 640
        self._infer_w = inp[3] if isinstance(inp[3], int) else 640

    @property
    def name(self) -> str:
        return "identifier"

    # ------------------------------------------------------------------
    # Pipeline entry point
    # ------------------------------------------------------------------

    def process(self, context: PipelineContext) -> PipelineContext:
        cfg = {**_DEFAULTS, **self.config.get("identifier", {})}

        if not context.clips:
            logger.info("Identifier: no clips to process")
            return context

        thumb_dir = os.path.join(context.storage_root, context.session_id, "clips")
        os.makedirs(thumb_dir, exist_ok=True)

        features: list[np.ndarray | None] = []
        for clip in context.clips:
            if not clip.clip_path:
                logger.warning("Identifier: clip %s has no file, skipping", clip.clip_id)
                features.append(None)
                continue

            feat, primary_thumb = self._process_clip(clip.clip_path, thumb_dir, clip.clip_id, cfg)
            clip.thumbnail_path = primary_thumb
            features.append(feat)
            logger.info(
                "Identifier: clip %s → thumbnail=%s feat=%s",
                clip.clip_id,
                "✓" if primary_thumb and os.path.exists(primary_thumb) else "✗",
                "ok" if feat is not None else "none",
            )

        self._assign_is_me(context, features, cfg)
        self._annotate_thumbnails(context)
        return context

    # ------------------------------------------------------------------
    # Per-clip: 3-segment frame selection + OSNet embedding
    # ------------------------------------------------------------------

    def _process_clip(
        self,
        clip_path: str,
        thumb_dir: str,
        clip_id: str,
        cfg: dict,
    ) -> tuple[np.ndarray | None, str | None]:
        """Sample 3 segments, extract embeddings, return (avg_embedding, primary_thumb_path)."""
        cap = cv2.VideoCapture(clip_path)
        if not cap.isOpened():
            logger.error("Identifier: cannot open %s", clip_path)
            return None, None

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        if total_frames < 3:
            return None, None

        n_seg = cfg["n_segments"]
        seg_size = total_frames // n_seg
        # Segment boundaries: [(start, end), ...]
        segments = [
            (i * seg_size, min((i + 1) * seg_size - 1, total_frames - 1))
            for i in range(n_seg)
        ]

        sample_interval = max(1, int(fps / cfg["sample_fps"]))
        embeddings: list[np.ndarray] = []
        thumb_paths: list[str | None] = [None] * n_seg

        for seg_idx, (seg_start, seg_end) in enumerate(segments):
            best = self._best_frame_in_segment(
                clip_path, seg_start, seg_end, sample_interval, cfg
            )
            if best is None:
                continue

            frame, bbox = best
            crop = _crop_person(frame, bbox, cfg["thumbnail_pad"])
            if crop is None or crop.size == 0:
                continue

            # Save thumbnail
            thumb_path = os.path.join(thumb_dir, f"{clip_id}_thumb_{seg_idx}.jpg")
            cv2.imwrite(thumb_path, crop)
            thumb_paths[seg_idx] = thumb_path

            # Re-ID embedding
            emb = self._embed(crop)
            if emb is not None:
                embeddings.append(emb)

        primary_thumb = thumb_paths[1] or thumb_paths[0] or thumb_paths[2]

        if not embeddings:
            self._save_middle_frame(clip_path, thumb_dir, clip_id)
            primary_thumb = os.path.join(thumb_dir, f"{clip_id}_thumb_1.jpg")
            return None, primary_thumb

        # L2-normalise each embedding, then average
        stacked = np.array(embeddings, dtype=np.float32)
        norms = np.linalg.norm(stacked, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        stacked = stacked / norms
        avg_emb = stacked.mean(axis=0)
        avg_norm = np.linalg.norm(avg_emb)
        if avg_norm > 0:
            avg_emb /= avg_norm

        return avg_emb, primary_thumb

    def _best_frame_in_segment(
        self,
        clip_path: str,
        seg_start: int,
        seg_end: int,
        sample_interval: int,
        cfg: dict,
    ) -> tuple[np.ndarray, tuple[int, int, int, int]] | None:
        """Find the highest-scored person detection in [seg_start, seg_end] frame range."""
        cap = cv2.VideoCapture(clip_path)
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_POS_FRAMES, seg_start)

        climb_thresh = cfg["climb_threshold"]
        min_area = cfg["min_area_frac"]
        conf_thresh = cfg["conf_threshold"]

        best_score = -1.0
        best_frame: np.ndarray | None = None
        best_bbox: tuple[int, int, int, int] | None = None

        frame_idx = seg_start
        while frame_idx <= seg_end:
            ret, frame = cap.read()
            if not ret:
                break
            if (frame_idx - seg_start) % sample_interval == 0:
                fh, fw = frame.shape[:2]
                blob, r, pad = preprocess(frame, self._infer_h, self._infer_w)
                raw = self._det_session.run(
                    None, {self._det_session.get_inputs()[0].name: blob}
                )[0]
                dets = postprocess_det(raw, r, pad, (fh, fw), conf_thresh)

                for det in dets:
                    x1, y1, x2, y2, conf = det[0], det[1], det[2], det[3], det[4]
                    center_y = ((y1 + y2) / 2) / fh
                    area_frac = (x2 - x1) * (y2 - y1) / (fw * fh)
                    if center_y >= climb_thresh or area_frac < min_area:
                        continue
                    score = float(conf) * area_frac
                    if score > best_score:
                        best_score = score
                        best_frame = frame.copy()
                        best_bbox = (int(x1), int(y1), int(x2), int(y2))
            frame_idx += 1

        cap.release()
        if best_frame is None or best_bbox is None:
            return None
        return best_frame, best_bbox

    def _embed(self, crop: np.ndarray) -> np.ndarray | None:
        """Run OSNet re-ID on a person crop → 1D embedding or None."""
        try:
            blob = preprocess_reid(crop)
            out = self._reid_session.run(
                None, {self._reid_session.get_inputs()[0].name: blob}
            )[0]
            return out[0].astype(np.float32)
        except Exception as e:
            logger.warning("Identifier: OSNet inference error: %s", e)
            return None

    # ------------------------------------------------------------------
    # is_me assignment via DBSCAN (cosine distance)
    # ------------------------------------------------------------------

    def _assign_is_me(
        self,
        context: PipelineContext,
        features: list[np.ndarray | None],
        cfg: dict,
    ) -> None:
        valid_idx = [i for i, f in enumerate(features) if f is not None]

        if len(valid_idx) == 0:
            for clip in context.clips:
                clip.is_me = True
            logger.warning("Identifier: no features extracted, marking all is_me=True")
            return

        if len(valid_idx) == 1:
            for clip in context.clips:
                clip.is_me = True
            logger.info("Identifier: single clip, marking is_me=True")
            return

        mat = np.array([features[i] for i in valid_idx], dtype=np.float32)

        labels = DBSCAN(
            eps=cfg["dbscan_eps"],
            min_samples=cfg["dbscan_min_samples"],
            metric="cosine",
        ).fit_predict(mat)

        unique = set(labels) - {-1}
        if not unique:
            for clip in context.clips:
                clip.is_me = True
            logger.warning("Identifier: all DBSCAN noise, marking all is_me=True")
            return

        # "나" = 가장 많이 등장한 클러스터
        # 동수일 때는 여러 영상에 걸쳐 나타난 클러스터 우선
        def cluster_score(lbl: int) -> tuple[int, int]:
            member_clip_indices = [valid_idx[j] for j, l in enumerate(labels) if l == lbl]
            size = len(member_clip_indices)
            video_diversity = len({context.clips[i].raw_video_id for i in member_clip_indices})
            return size, video_diversity

        largest = max(unique, key=cluster_score)
        me_set = {valid_idx[j] for j, lbl in enumerate(labels) if lbl == largest}

        logger.info(
            "Identifier: %d cluster(s) found; largest=%d (%d/%d clips)",
            len(unique), largest, len(me_set), len(context.clips),
        )
        for i, clip in enumerate(context.clips):
            clip.is_me = i in me_set
            logger.info("Identifier: clip %s → is_me=%s", clip.clip_id, clip.is_me)

    # ------------------------------------------------------------------
    # Thumbnail annotation — coloured border after clustering
    # ------------------------------------------------------------------

    @staticmethod
    def _annotate_thumbnails(context: PipelineContext) -> None:
        """Draw border + label on primary thumbnail based on is_me result."""
        for clip in context.clips:
            if not clip.thumbnail_path or not os.path.exists(clip.thumbnail_path):
                continue
            img = cv2.imread(clip.thumbnail_path)
            if img is None:
                continue
            color = (74, 175, 74) if clip.is_me else (100, 100, 100)  # BGR green / gray
            thickness = 6 if clip.is_me else 3
            h, w = img.shape[:2]
            cv2.rectangle(img, (0, 0), (w - 1, h - 1), color, thickness)

            src = clip.raw_video_id.replace("rv-", "")[:12]
            label = f"{src}  {clip.start_time:.0f}-{clip.end_time:.0f}s"
            cv2.rectangle(img, (0, h - 22), (w, h), (0, 0, 0), -1)
            cv2.putText(img, label, (4, h - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 220, 220), 1, cv2.LINE_AA)

            me_label = "ME" if clip.is_me else "other"
            me_color = (74, 175, 74) if clip.is_me else (100, 100, 100)
            cv2.rectangle(img, (0, 0), (54, 22), (0, 0, 0), -1)
            cv2.putText(img, me_label, (4, 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, me_color, 1, cv2.LINE_AA)

            cv2.imwrite(clip.thumbnail_path, img)

    # ------------------------------------------------------------------
    # Fallback: save middle frame when no person detected
    # ------------------------------------------------------------------

    @staticmethod
    def _save_middle_frame(clip_path: str, thumb_dir: str, clip_id: str) -> None:
        cap = cv2.VideoCapture(clip_path)
        if not cap.isOpened():
            return
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
        ret, frame = cap.read()
        if ret:
            thumb_path = os.path.join(thumb_dir, f"{clip_id}_thumb_1.jpg")
            cv2.imwrite(thumb_path, frame)
        cap.release()


# ------------------------------------------------------------------
# Crop helper
# ------------------------------------------------------------------

def _crop_person(
    frame: np.ndarray,
    bbox: tuple[int, int, int, int],
    pad_frac: float,
) -> np.ndarray | None:
    """Return a padded crop of the person bbox, or None if degenerate."""
    fh, fw = frame.shape[:2]
    x1, y1, x2, y2 = bbox
    if x2 <= x1 or y2 <= y1:
        return None
    pad_x = int((x2 - x1) * pad_frac)
    pad_y = int((y2 - y1) * pad_frac)
    cx1 = max(0, x1 - pad_x)
    cy1 = max(0, y1 - pad_y)
    cx2 = min(fw, x2 + pad_x)
    cy2 = min(fh, y2 + pad_y)
    crop = frame[cy1:cy2, cx1:cx2]
    return crop if crop.size > 0 else None
