"""Export yolo26n-pose.pt → yolo26n-pose.onnx for analyzer runtime use.

Run inside the analyzer container:
    python -m analyzer.models.export_yolo26n_pose
"""
import shutil
from pathlib import Path

MODEL_DIR = Path(__file__).parent
OUTPUT_PATH = MODEL_DIR / "yolo26n-pose.onnx"


def export() -> None:
    from ultralytics import YOLO  # noqa: PLC0415

    print(f"Exporting yolo26n-pose.pt → {OUTPUT_PATH}")
    model = YOLO("yolo26n-pose.pt")
    model.export(
        format="onnx",
        imgsz=640,
        half=False,
        dynamic=True,    # dynamic batch dimension required for batch inference
        simplify=True,
        opset=17,
    )
    for candidate in [Path("yolo26n-pose.onnx"), Path("/app/yolo26n-pose.onnx")]:
        if candidate.exists() and candidate.resolve() != OUTPUT_PATH.resolve():
            shutil.copy2(str(candidate), str(OUTPUT_PATH))
            print(f"Saved: {OUTPUT_PATH}")
            return
    if OUTPUT_PATH.exists():
        print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    export()
