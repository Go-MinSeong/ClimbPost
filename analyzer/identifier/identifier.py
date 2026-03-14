from __future__ import annotations

import logging

import cv2
import mediapipe as mp
import numpy as np
from sklearn.cluster import DBSCAN

from analyzer.pipeline.base_stage import BaseStage
from analyzer.pipeline.context import PipelineContext

logger = logging.getLogger(__name__)

# Default settings (overridable via config dict)
_DEFAULTS = {
    "sample_fps": 1,              # frames per second to sample for feature extraction
    "color_bins": 32,             # histogram bins per channel
    "dbscan_eps": 0.5,           # DBSCAN neighbourhood radius
    "dbscan_min_samples": 1,      # DBSCAN minimum cluster size
}


class IdentifierStage(BaseStage):
    """Stage 4 — identify which clips belong to the user ('me').

    Strategy:
      1. For each clip, extract the climber's appearance features:
         - Torso colour histogram (HSV, extracted from pose bounding box)
         - Body proportions (height/width ratio from pose landmarks)
      2. Cluster all feature vectors using DBSCAN.
      3. The largest cluster is assumed to be the user (since the
         camera operator climbs most often on a tripod-recorded session).
      4. Mark each clip's ``is_me`` flag accordingly.
    """

    @property
    def name(self) -> str:
        return "identifier"

    def process(self, context: PipelineContext) -> PipelineContext:
        cfg = {**_DEFAULTS, **self.config.get("identifier", {})}

        if not context.clips:
            logger.info("Identifier: no clips to process")
            return context

        # Extract feature vectors for each clip
        features: list[np.ndarray | None] = []
        for clip in context.clips:
            if not clip.clip_path:
                logger.warning("Identifier: clip %s has no file path, skipping", clip.clip_id)
                features.append(None)
                continue

            feat = self._extract_features(clip.clip_path, cfg)
            features.append(feat)

        # Collect valid features for clustering
        valid_indices = [i for i, f in enumerate(features) if f is not None]

        if len(valid_indices) < 2:
            # With 0-1 clips, assume all are "me"
            for clip in context.clips:
                clip.is_me = True
            logger.info("Identifier: ≤1 valid clip(s), marking all as is_me=True")
            return context

        feature_matrix = np.array([features[i] for i in valid_indices])

        # Normalise features to unit length for cosine-like comparison
        norms = np.linalg.norm(feature_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        feature_matrix = feature_matrix / norms

        # Cluster
        clustering = DBSCAN(
            eps=cfg["dbscan_eps"],
            min_samples=cfg["dbscan_min_samples"],
            metric="euclidean",
        ).fit(feature_matrix)

        labels = clustering.labels_

        # Find the largest cluster (ignoring noise label -1)
        unique_labels = set(labels)
        unique_labels.discard(-1)

        if not unique_labels:
            # All noise — mark all as "me" as fallback
            for clip in context.clips:
                clip.is_me = True
            logger.warning("Identifier: DBSCAN produced all noise, marking all as is_me=True")
            return context

        largest_label = max(unique_labels, key=lambda lbl: np.sum(labels == lbl))
        logger.info(
            "Identifier: found %d cluster(s), largest cluster=%d (%d clips)",
            len(unique_labels),
            largest_label,
            int(np.sum(labels == largest_label)),
        )

        # Build a set of clip indices that belong to the "me" cluster
        me_indices = set()
        for idx_in_valid, label in enumerate(labels):
            if label == largest_label:
                me_indices.add(valid_indices[idx_in_valid])

        # Assign is_me
        for i, clip in enumerate(context.clips):
            clip.is_me = i in me_indices
            logger.info("Identifier: clip %s → is_me=%s", clip.clip_id, clip.is_me)

        return context

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------

    def _extract_features(self, clip_path: str, cfg: dict) -> np.ndarray | None:
        """Extract appearance feature vector from a clip.

        The feature vector concatenates:
          - HSV colour histogram of the torso region (normalised)
          - Body aspect ratio (height / width)
        """
        cap = cv2.VideoCapture(clip_path)
        if not cap.isOpened():
            logger.error("Identifier: cannot open %s", clip_path)
            return None

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sample_interval = max(1, int(fps / cfg["sample_fps"]))

        pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=0,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        histograms: list[np.ndarray] = []
        aspect_ratios: list[float] = []
        bins = cfg["color_bins"]

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_interval != 0:
                frame_idx += 1
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(rgb)

            torso_roi, aspect = self._get_torso_roi(frame, results)

            if torso_roi is not None:
                hsv = cv2.cvtColor(torso_roi, cv2.COLOR_BGR2HSV)
                hist_h = cv2.calcHist([hsv], [0], None, [bins], [0, 180]).flatten()
                hist_s = cv2.calcHist([hsv], [1], None, [bins], [0, 256]).flatten()
                hist = np.concatenate([hist_h, hist_s])
                # Normalise histogram
                total = hist.sum()
                if total > 0:
                    hist = hist / total
                histograms.append(hist)

            if aspect is not None:
                aspect_ratios.append(aspect)

            frame_idx += 1

        pose.close()
        cap.release()

        if not histograms:
            return None

        # Average the histograms and aspect ratios across sampled frames
        avg_hist = np.mean(histograms, axis=0)
        avg_aspect = np.mean(aspect_ratios) if aspect_ratios else 0.0

        # Concatenate into a single feature vector
        feature = np.concatenate([avg_hist, [avg_aspect]])
        return feature

    @staticmethod
    def _get_torso_roi(
        frame: np.ndarray, results
    ) -> tuple[np.ndarray | None, float | None]:
        """Extract the torso bounding box from pose landmarks.

        Returns (torso_roi_image, body_aspect_ratio) or (None, None).
        """
        if not results.pose_landmarks:
            return None, None

        landmarks = results.pose_landmarks.landmark
        h, w = frame.shape[:2]

        # Torso landmarks: left/right shoulders (11, 12) and left/right hips (23, 24)
        torso_indices = [11, 12, 23, 24]
        points = []
        for idx in torso_indices:
            lm = landmarks[idx]
            if lm.visibility < 0.5:
                return None, None
            points.append((lm.x, lm.y))

        xs = [p[0] for p in points]
        ys = [p[1] for p in points]

        x_min = max(0, int(min(xs) * w))
        x_max = min(w, int(max(xs) * w))
        y_min = max(0, int(min(ys) * h))
        y_max = min(h, int(max(ys) * h))

        if x_max <= x_min or y_max <= y_min:
            return None, None

        torso_roi = frame[y_min:y_max, x_min:x_max]

        # Full body aspect ratio from all visible landmarks
        all_vis = [(lm.x, lm.y) for lm in landmarks if lm.visibility > 0.5]
        if len(all_vis) < 4:
            return torso_roi, None

        all_xs = [p[0] for p in all_vis]
        all_ys = [p[1] for p in all_vis]
        body_w = max(all_xs) - min(all_xs)
        body_h = max(all_ys) - min(all_ys)
        aspect = body_h / body_w if body_w > 0 else 0.0

        return torso_roi, aspect
