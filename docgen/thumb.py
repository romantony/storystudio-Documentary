"""Thumbnail: a real image on the left, large coloured title text added by the Gemini image model.
python3 -m docgen thumb --image <asset id or path> --lines "WAR THAT" "ENDED" "SLAVERY"
Writes thumb/thumbnail.jpg (1280x720). Look at the result: the model can misspell the text."""
import base64, json, os, subprocess, sys, urllib.request
from PIL import Image, ImageEnhance, ImageFilter
from .common import find_image, key, mkdirs
MODEL = os.environ.get("DOCGEN_IMAGE_MODEL", "gemini-3.1-flash-image")
def main(cmd, argv):
    if "--image" not in argv or "--lines" not in argv: sys.exit(__doc__)
    src = find_image(argv[argv.index("--image") + 1]); lines = [a for a in argv[argv.index("--lines") + 1:] if not a.startswith("--")]
    if not src: sys.exit("image not found")
    mkdirs("thumb"); art = Image.open(src).convert("RGB")
    bg = art.resize((1280, max(720, int(art.height * 1280 / art.width)))); y = (bg.height - 720) // 3
    bg = ImageEnhance.Brightness(bg.crop((0, y, 1280, y + 720)).filter(ImageFilter.GaussianBlur(25))).enhance(0.3)
    fg = art.resize((int(art.width * 720 / art.height), 720))
    if fg.width > 760: fg = fg.crop(((fg.width - 760) // 2, 0, (fg.width - 760) // 2 + 760, 720))
    bg.paste(fg, (60, 0)); bg.save("thumb/base.jpg", quality=95)
    cols = ["vivid red-orange", "bright yellow", "bright yellow"]; nth = ["first", "second", "third"]
    spec = ", ".join(f"{nth[i]} line '{t}' in {cols[min(i, 2)]}" for i, t in enumerate(lines[:3]))
    prompt = ("This is a thumbnail base: a real public-domain image on the left with dark space on the right. Turn it into a 16:9 YouTube thumbnail. "
              "Keep the image unchanged, only slightly boost contrast. Add very large, bold, colourful title text with a thick black outline and a subtle glow in the empty area on the right: "
              f"{spec}. Spell the text exactly. No other text, logos or watermarks.")
    body = {"contents": [{"parts": [{"text": prompt}, {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(open("thumb/base.jpg", "rb").read()).decode()}}]}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "16:9"}}}
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent", json.dumps(body).encode(), {"Content-Type": "application/json", "x-goog-api-key": key("GEMINI_API_KEY")})
    d = json.load(urllib.request.urlopen(req, timeout=300))
    img = next(p["inlineData"] for p in d["candidates"][0]["content"]["parts"] if "inlineData" in p)
    open("thumb/raw.img", "wb").write(base64.b64decode(img["data"]))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", "thumb/raw.img", "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720", "-frames:v", "1", "-q:v", "3", "thumb/thumbnail.jpg"], check=True)
    print("thumb/thumbnail.jpg")
