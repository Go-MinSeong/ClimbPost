"""Export yolo26n.pt → yolo26n.onnx for analyzer runtime use.

Run inside the analyzer container (or any env with ultralytics + torch):

    python -m analyzer.models.export_yolo26n

The output is saved to analyzer/models/yolo26n.onnx.
"""

import shutil
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
        half=False,
        dynamic=True,    # dynamic batch dimension required for batch inference
        simplify=True,
        opset=17,
    )

    # ultralytics writes the file next to the .pt source; copy to models/
    for candidate in [Path("yolo26n.onnx"), Path("/app/yolo26n.onnx")]:
        if candidate.exists() and candidate.resolve() != OUTPUT_PATH.resolve():
            shutil.copy2(str(candidate), str(OUTPUT_PATH))
            print(f"Saved: {OUTPUT_PATH}")
            return
    if OUTPUT_PATH.exists():
        print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    export()
