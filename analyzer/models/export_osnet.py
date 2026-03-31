"""Export OSNet-x0.25 (person re-ID) to ONNX.

Run once inside the analyzer container:
    python -m analyzer.models.export_osnet

Primary:  torchreid  (pip install torchreid)
Fallback: torchvision MobileNetV2 if torchreid is not installed

Output: analyzer/models/osnet_x0_25.onnx  (input [N,3,256,128] → output [N,512])
"""
from __future__ import annotations

import logging
from pathlib import Path

import torch

logger = logging.getLogger(__name__)
OUT = Path(__file__).parent / "osnet_x0_25.onnx"
REID_H, REID_W = 256, 128  # standard person re-ID crop size


class _MobileNetReID(torch.nn.Module):
    """torchvision MobileNetV2 truncated to a 1280-dim feature extractor."""

    def __init__(self) -> None:
        super().__init__()
        import torchvision.models as tvm
        base = tvm.mobilenet_v2(weights="DEFAULT")
        self.features = base.features
        self.pool = torch.nn.AdaptiveAvgPool2d(1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = self.pool(x)
        return x.flatten(1)


def _build_osnet() -> torch.nn.Module:
    try:
        import torchreid
        model = torchreid.models.build_model(
            name="osnet_x0_25",
            num_classes=751,   # Market-1501 pretrained
            pretrained=True,
            loss="softmax",
        )
        model.eval()
        logger.info("OSNet-x0.25 loaded from torchreid (Market-1501 pretrained)")
        return model
    except Exception as e:
        logger.warning("torchreid not available (%s), falling back to MobileNetV2", e)
        model = _MobileNetReID()
        model.eval()
        return model


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    model = _build_osnet()
    dummy = torch.zeros(1, 3, REID_H, REID_W)

    with torch.no_grad():
        out = model(dummy)
    logger.info("Model output shape: %s", tuple(out.shape))

    torch.onnx.export(
        model,
        dummy,
        str(OUT),
        opset_version=18,
        input_names=["image"],
        output_names=["embedding"],
        dynamic_axes={"image": {0: "batch"}, "embedding": {0: "batch"}},
    )

    import onnx
    onnx.checker.check_model(str(OUT))
    logger.info("ONNX export validated → %s", OUT)


if __name__ == "__main__":
    main()
