"""Contact sheets, so images and video frames can be checked by eye before they are used or published.
python3 -m docgen sheet --images a.jpg b.png ... --out build/sheet.jpg [--cols 6]
python3 -m docgen sheet --video out/x.mp4 --n 12 --out build/frames.jpg
python3 -m docgen sheet --archive --out build/archive_sheet.jpg        (every image in the archive dir, labelled)"""
import glob, os, subprocess, sys, tempfile
from PIL import Image, ImageDraw
from .common import ARCHIVE, dur

def sheet(files, out, cols=6, cell=(320, 200), labels=None):
    rows = (len(files) + cols - 1) // cols; S = Image.new("RGB", (cell[0] * cols, cell[1] * rows)); d = ImageDraw.Draw(S)
    for i, f in enumerate(files):
        im = Image.open(f).convert("RGB"); im.thumbnail(cell); x, y = (i % cols) * cell[0], (i // cols) * cell[1]; S.paste(im, (x, y))
        if labels: d.rectangle((x, y, x + 8 * len(labels[i]) + 6, y + 14), fill=(0, 0, 0)); d.text((x + 3, y + 1), labels[i], fill=(255, 255, 0))
    S.save(out, quality=88); print(out, len(files), "images")

def main(cmd, argv):
    out = argv[argv.index("--out") + 1] if "--out" in argv else "build/sheet.jpg"
    cols = int(argv[argv.index("--cols") + 1]) if "--cols" in argv else 6
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    if "--archive" in argv:
        fs = sorted(glob.glob(f"{ARCHIVE}/*.jpg")); sheet(fs, out, cols, labels=[os.path.basename(f)[:-4] for f in fs])
    elif "--video" in argv:
        v = argv[argv.index("--video") + 1]; n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 12; D = dur(v)
        vert = "--vertical" in argv; tmp = tempfile.mkdtemp(); fs = []
        for i in range(n):
            f = f"{tmp}/{i:03d}.jpg"; t = D * (i + 0.5) / n
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", v, "-frames:v", "1", f], check=True); fs.append(f)
        sheet(fs, out, cols, cell=(270, 480) if vert else (480, 270), labels=[f"{D * (i + 0.5) / n:.0f}s" for i in range(n)])
    else:
        i = argv.index("--images") + 1; fs = [a for a in argv[i:] if not a.startswith("--") and os.path.exists(a)]
        sheet(fs, out, cols, labels=[os.path.basename(f).rsplit(".", 1)[0][:30] for f in fs])
