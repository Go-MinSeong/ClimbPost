"""Shared ONNX inference utilities for all analyzer stages.

Output format assumed (ultralytics YOLO26n post-NMS export):
  Detection : [1, 300,  6] — x1, y1, x2, y2, conf, cls
  Pose      : [1, 300, 57] — x1, y1, x2, y2, conf, cls,
                              kpt0_x, kpt0_y, kpt0_v, ..., kpt16_x, kpt16_y, kpt16_v
"""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

logger = logging.getLogger(__name__)

_INFER_SIZE = 640

# ImageNet mean/std for person re-ID models (OSNet, etc.)
_REID_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_REID_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)
REID_H, REID_W = 256, 128  # standard re-ID crop size (tall × narrow)

# COCO keypoint indices
KPT_L_SHOULDER = 5
KPT_R_SHOULDER = 6
KPT_L_WRIST    = 9
KPT_R_WRIST    = 10
KPT_L_HIP      = 11
KPT_R_HIP      = 12


def load_session(model_path: str | Path) -> ort.InferenceSession:
    """Create an ONNX InferenceSession preferring CUDAExecutionProvider."""
    so = ort.SessionOptions()
    so.log_severity_level = 3
    providers = [("CUDAExecutionProvider", {"device_id": 0}), "CPUExecutionProvider"]
    sess = ort.InferenceSession(str(model_path), sess_options=so, providers=providers)
    logger.info("ONNX session loaded (%s) → %s", Path(model_path).name, sess.get_providers()[0])
    return sess


def preprocess(
    frame: np.ndarray, target_h: int = _INFER_SIZE, target_w: int = _INFER_SIZE
) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Letterbox → [1, 3, H, W] float32 in [0, 1].

    Returns (blob, scale_ratio, (pad_x, pad_y)).
    """
    h, w = frame.shape[:2]
    r = min(target_h / h, target_w / w)
    new_h, new_w = int(h * r), int(w * r)
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    pad_h, pad_w = target_h - new_h, target_w - new_w
    top, left = pad_h // 2, pad_w // 2
    padded = cv2.copyMakeBorder(
        resized, top, pad_h - top, left, pad_w - left,
        cv2.BORDER_CONSTANT, value=(114, 114, 114),
    )
    blob = padded[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
    return np.expand_dims(blob, 0), r, (left, top)


def preprocess_reid(
    crop: np.ndarray, h: int = REID_H, w: int = REID_W
) -> np.ndarray:
    """Resize person crop → [1, 3, H, W] ImageNet-normalised float32.

    Suitable for OSNet and other torchvision-based re-ID models.
    """
    resized = cv2.resize(crop, (w, h), interpolation=cv2.INTER_LINEAR)
    rgb = resized[:, :, ::-1].astype(np.float32) / 255.0
    rgb = (rgb - _REID_MEAN) / _REID_STD
    blob = rgb.transpose(2, 0, 1)
    return np.expand_dims(blob, 0).astype(np.float32)


def postprocess_det(
    output: np.ndarray,
    r: float,
    pad: tuple[int, int],
    orig_shape: tuple[int, int],
    conf_thresh: float = 0.3,
) -> np.ndarray:
    """Decode detection output [1, N, 6] → person bboxes [M, 6] in original pixel coords.

    Returns array of shape [M, 6]: x1, y1, x2, y2, conf, cls.
    Filters to person class (cls == 0) only.
    """
    preds = output[0]  # [N, 6]
    mask = (preds[:, 5] == 0) & (preds[:, 4] >= conf_thresh)
    preds = preds[mask]
    if len(preds) == 0:
        return np.empty((0, 6), dtype=np.float32)
    return _unscale_xyxy(preds, r, pad, orig_shape)


def postprocess_pose(
    output: np.ndarray,
    r: float,
    pad: tuple[int, int],
    orig_shape: tuple[int, int],
    conf_thresh: float = 0.3,
) -> np.ndarray:
    """Decode pose output [1, N, 57] → person pose rows [M, 57] in original pixel coords.

    Returns array of shape [M, 57]: x1, y1, x2, y2, conf, cls, kpt0_x, kpt0_y, kpt0_v, ...
    Filters to person class (cls == 0) only.
    """
    preds = output[0]  # [N, 57]
    mask = (preds[:, 5] == 0) & (preds[:, 4] >= conf_thresh)
    preds = preds[mask]
    if len(preds) == 0:
        return np.empty((0, 57), dtype=np.float32)

    result = preds.copy()
    # Unscale bbox (columns 0-3)
    result[:, :4] = _unscale_xyxy(preds, r, pad, orig_shape)[:, :4]
    # Unscale keypoints (every 3 values starting at column 6: x, y, visibility)
    pad_x, pad_y = pad
    orig_h, orig_w = orig_shape
    for ki in range(17):
        base = 6 + ki * 3
        result[:, base]     = np.clip((preds[:, base]     - pad_x) / r, 0, orig_w)
        result[:, base + 1] = np.clip((preds[:, base + 1] - pad_y) / r, 0, orig_h)
        # visibility is untouched
    return result


def get_center_y(person: np.ndarray, frame_h: int) -> float | None:
    """Compute normalised center_y from shoulder + hip keypoints."""
    ys = []
    for ki in [KPT_L_SHOULDER, KPT_R_SHOULDER, KPT_L_HIP, KPT_R_HIP]:
        base = 6 + ki * 3
        if person[base + 2] > 0.3:
            ys.append(float(person[base + 1]) / frame_h)
    return float(np.mean(ys)) if ys else None


def get_wrist_points(
    person: np.ndarray,
    frame_h: int,
    frame_w: int,
    min_vis: float = 0.3,
) -> list[tuple[int, int, float]]:
    """Return list of (cx_px, cy_px, visibility) for detected wrists."""
    pts = []
    for ki in [KPT_L_WRIST, KPT_R_WRIST]:
        base = 6 + ki * 3
        vis = float(person[base + 2])
        if vis >= min_vis:
            cx = int(np.clip(person[base],     0, frame_w))
            cy = int(np.clip(person[base + 1], 0, frame_h))
            pts.append((cx, cy, vis))
    return pts


# ------------------------------------------------------------------
# Internal helper
# ------------------------------------------------------------------

def _unscale_xyxy(
    preds: np.ndarray,
    r: float,
    pad: tuple[int, int],
    orig_shape: tuple[int, int],
) -> np.ndarray:
    """Unpad + unscale bbox columns 0-3 in place on a copy."""
    result = preds.copy()
    pad_x, pad_y = pad
    orig_h, orig_w = orig_shape
    result[:, 0] = np.clip((preds[:, 0] - pad_x) / r, 0, orig_w)
    result[:, 1] = np.clip((preds[:, 1] - pad_y) / r, 0, orig_h)
    result[:, 2] = np.clip((preds[:, 2] - pad_x) / r, 0, orig_w)
    result[:, 3] = np.clip((preds[:, 3] - pad_y) / r, 0, orig_h)
    return result
