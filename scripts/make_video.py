import cv2
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
frames_dir = BASE / "static/output"

images = sorted(frames_dir.glob("anim_frame_*.png"))

first = cv2.imread(str(images[0]))
h, w, _ = first.shape

out = cv2.VideoWriter(
    str(BASE / "static/output/final.mp4"),
    cv2.VideoWriter_fourcc(*"mp4v"),
    8,
    (w, h)
)

for img in images:
    frame = cv2.imread(str(img))
    out.write(frame)

out.release()

print("final.mp4 created")
