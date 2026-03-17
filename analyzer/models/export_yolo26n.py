"""Export yolo26n.pt → yolo26n.onnx for analyzer runtime use.

Run inside the analyzer container (or any env with ultralytics + torch):

    python -m analyzer.models.export_yolo26n

The output is saved to analyzer/models/yolo26n.onnx.
"""

from pathlib import Path

MODEL_DIR = Path(__file__).parent
OUTPUT_PATH = MODEL_DIR / "yolo26n.onnx"


def export() -> None:
    from ultralytics import YOLO  # noqa: PLC0415

    print(f"Downloading yolo26n.pt and exporting to ONNX → {OUTPUT_PATH}")
    model = YOLO("yolo26n.pt")
    model.export(
        format="onnx",
        imgsz=640,
        half=False,      # FP32; set True for FP16 on GPU-only deployments
        dynamic=False,   # fixed batch=1 for deterministic input shape
        simplify=True,   # ONNX simplifier reduces graph complexity
        opset=17,
    )

    # ultralytics writes the file next to the .pt source; move to models/
    default_out = Path("yolo26n.onnx")
    if default_out.exists() and default_out.resolve() != OUTPUT_PATH.resolve():
        default_out.rename(OUTPUT_PATH)

    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    export()
