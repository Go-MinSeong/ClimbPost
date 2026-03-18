"""Stage 2 — Identifier: per-clip thumbnail generation + 'am I in this clip?' detection.

Strategy
--------
1. For each clip, sample frames and run YOLO26n detection.
2. Pick the *best frame* per clip:
   - Person must be in the climbing zone (center_y < climb_threshold).
   - Score = detection_confidence × bbox_area_fraction → pick argmax.
3. Crop the person's full-body bbox from the best frame, save as thumbnail.
4. Extract an HSV colour histogram from the body crop (torso band) as a
   compact appearance feature per clip.
5. Cluster all feature vectors with DBSCAN.
   - Largest cluster → 'me' (assumption: the owner appears most often).
   - All clips in the largest cluster get is_me=True; others is_me=False.
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
    postprocess_det,
)

logger = logging.getLogger(__name__)

_MODEL_PATH = os.environ.get(
    "YOLO26N_ONNX",
    str(Path(__file__).resolve().parent.parent / "models" / "yolo26n.onnx"),
)

_DEFAULTS = {
    "sample_fps": 2,             # frames per second to sample per clip
    "climb_threshold": 0.65,     # center_y < this → person in climbing zone
    "conf_threshold": 0.3,       # minimum detection confidence
    "hist_bins": 32,             # histogram bins per channel (H and S)
    "dbscan_eps": 0.40,          # DBSCAN neighbourhood radius (L2 on normalised hist)
    "dbscan_min_samples": 1,     # minimum cluster size
    "thumbnail_pad": 0.05,       # relative bbox expansion when saving thumbnail
}


class IdentifierStage(BaseStage):
    """Stage 2 — identify which clips contain 'me' and generate per-clip thumbnails."""

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._session = load_session(_MODEL_PATH)
        inp = self._session.get_inputs()[0].shape
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

        features: list[np.ndarray | None] = []
        for clip in context.clips:
            if not clip.clip_path:
                logger.warning("Identifier: clip %s has no file, skipping", clip.clip_id)
                features.append(None)
                continue

            thumb_dir = os.path.join(
                context.storage_root, context.session_id, "clips"
            )
            os.makedirs(thumb_dir, exist_ok=True)
            thumb_path = os.path.join(thumb_dir, f"{clip.clip_id}_thumb.jpg")

            feat = self._process_clip(clip.clip_path, thumb_path, cfg)
            clip.thumbnail_path = thumb_path if os.path.exists(thumb_path) else None
            features.append(feat)
            logger.info(
                "Identifier: clip %s → thumbnail=%s feat=%s",
                clip.clip_id,
                "✓" if clip.thumbnail_path else "✗",
                "ok" if feat is not None else "none",
            )

        self._assign_is_me(context, features, cfg)
        self._annotate_thumbnails(context)
        return context

    # ------------------------------------------------------------------
    # Per-clip processing: best-frame selection + thumbnail + feature
    # ------------------------------------------------------------------

    def _process_clip(
        self, clip_path: str, thumb_path: str, cfg: dict
    ) -> np.ndarray | None:
        """Find best frame, save thumbnail, return HSV histogram feature."""
        cap = cv2.VideoCapture(clip_path)
        if not cap.isOpened():
            logger.error("Identifier: cannot open %s", clip_path)
            return None

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        sample_interval = max(1, int(fps / cfg["sample_fps"]))
        climb_thresh = cfg["climb_threshold"]

        best_score = -1.0
        best_frame: np.ndarray | None = None
        best_bbox: tuple[int, int, int, int] | None = None  # x1,y1,x2,y2

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % sample_interval == 0:
                fh, fw = frame.shape[:2]
                blob, r, pad = preprocess(frame, self._infer_h, self._infer_w)
                raw = self._session.run(None, {self._session.get_inputs()[0].name: blob})[0]
                dets = postprocess_det(raw, r, pad, (fh, fw), cfg["conf_threshold"])

                for det in dets:
                    x1, y1, x2, y2, conf = det[0], det[1], det[2], det[3], det[4]
                    center_y = ((y1 + y2) / 2) / fh
                    if center_y >= climb_thresh:
                        continue
                    area_frac = (x2 - x1) * (y2 - y1) / (fw * fh)
                    score = float(conf) * area_frac
                    if score > best_score:
                        best_score = score
                        best_frame = frame.copy()
                        best_bbox = (int(x1), int(y1), int(x2), int(y2))

            frame_idx += 1

        cap.release()

        if best_frame is None or best_bbox is None:
            logger.warning("Identifier: no climbing-zone detection found in %s", clip_path)
            # Fall back: use middle frame as thumbnail, no feature
            self._save_middle_frame(clip_path, thumb_path)
            return None

        # Save thumbnail: padded person crop
        fh, fw = best_frame.shape[:2]
        x1, y1, x2, y2 = best_bbox
        pad_px_x = int((x2 - x1) * cfg["thumbnail_pad"])
        pad_px_y = int((y2 - y1) * cfg["thumbnail_pad"])
        tx1 = max(0, x1 - pad_px_x)
        ty1 = max(0, y1 - pad_px_y)
        tx2 = min(fw, x2 + pad_px_x)
        ty2 = min(fh, y2 + pad_px_y)
        crop = best_frame[ty1:ty2, tx1:tx2]
        cv2.imwrite(thumb_path, crop)

        # Extract feature: HSV histogram of torso band (middle 40–80% height of crop)
        return _hsv_feature(crop, cfg["hist_bins"])

    # ------------------------------------------------------------------
    # is_me assignment via DBSCAN
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

        mat = np.array([features[i] for i in valid_idx])
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        mat = mat / norms

        labels = DBSCAN(
            eps=cfg["dbscan_eps"],
            min_samples=cfg["dbscan_min_samples"],
            metric="euclidean",
        ).fit_predict(mat)

        unique = set(labels) - {-1}
        if not unique:
            for clip in context.clips:
                clip.is_me = True
            logger.warning("Identifier: all DBSCAN noise, marking all is_me=True")
            return

        largest = max(unique, key=lambda lbl: int(np.sum(labels == lbl)))
        me_set = {valid_idx[j] for j, lbl in enumerate(labels) if lbl == largest}

        logger.info(
            "Identifier: %d cluster(s) found; largest=%d (%d/%d clips)",
            len(unique), largest, len(me_set), len(context.clips),
        )
        for i, clip in enumerate(context.clips):
            clip.is_me = i in me_set
            logger.info("Identifier: clip %s → is_me=%s", clip.clip_id, clip.is_me)

    # ------------------------------------------------------------------
    # Thumbnail annotation — draw is_me border after clustering
    # ------------------------------------------------------------------

    @staticmethod
    def _annotate_thumbnails(context: PipelineContext) -> None:
        """Draw a coloured border on each clip thumbnail based on is_me result.

        Green border  → is_me=True  (나)
        Gray  border  → is_me=False (타인)
        """
        for clip in context.clips:
            if not clip.thumbnail_path or not os.path.exists(clip.thumbnail_path):
                continue
            img = cv2.imread(clip.thumbnail_path)
            if img is None:
                continue
            color = (74, 175, 74) if clip.is_me else (100, 100, 100)  # BGR
            thickness = 6 if clip.is_me else 3
            h, w = img.shape[:2]
            cv2.rectangle(img, (0, 0), (w - 1, h - 1), color, thickness)

            # Label text: source video + time range
            src = clip.raw_video_id.replace("rv-", "")[:12]
            label = f"{src}  {clip.start_time:.0f}-{clip.end_time:.0f}s"
            cv2.rectangle(img, (0, h - 22), (w, h), (0, 0, 0), -1)
            cv2.putText(img, label, (4, h - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 220, 220), 1, cv2.LINE_AA)

            me_label = "ME" if clip.is_me else "other"
            me_color = (74, 175, 74) if clip.is_me else (100, 100, 100)
            cv2.rectangle(img, (0, 0), (50, 20), (0, 0, 0), -1)
            cv2.putText(img, me_label, (4, 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, me_color, 1, cv2.LINE_AA)

            cv2.imwrite(clip.thumbnail_path, img)

    # ------------------------------------------------------------------
    # Fallback thumbnail (middle frame, no person crop)
    # ------------------------------------------------------------------

    @staticmethod
    def _save_middle_frame(clip_path: str, thumb_path: str) -> None:
        cap = cv2.VideoCapture(clip_path)
        if not cap.isOpened():
            return
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
        ret, frame = cap.read()
        if ret:
            cv2.imwrite(thumb_path, frame)
        cap.release()


# ------------------------------------------------------------------
# Feature extraction helper
# ------------------------------------------------------------------

def _hsv_feature(crop: np.ndarray, bins: int) -> np.ndarray:
    """HSV colour histogram (H + S channels) from the torso band of a person crop."""
    h = crop.shape[0]
    # Torso band: 30–75% of crop height (upper body, avoids head and legs)
    y0 = int(h * 0.30)
    y1 = int(h * 0.75)
    torso = crop[y0:y1] if y1 > y0 else crop

    hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
    hist_h = cv2.calcHist([hsv], [0], None, [bins], [0, 180]).flatten()
    hist_s = cv2.calcHist([hsv], [1], None, [bins], [0, 256]).flatten()
    feat = np.concatenate([hist_h, hist_s]).astype(np.float32)
    total = feat.sum()
    if total > 0:
        feat /= total
    return feat
