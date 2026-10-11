"""End card for the long video (like / subscribe / share over a blurred image).
python3 -m docgen card --bg <asset id or path> --line "Next: Why the Peace Failed" [--series "WARS THAT SHAPED THE WORLD"] [--out <archive dir>/endcard.jpg]"""
import sys
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from .common import ARCHIVE, find_image
W, H = 1920, 1080
EMO = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"; BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
def emoji(ch, size=230):
    im = Image.new("RGBA", (136, 128), (0, 0, 0, 0)); ImageDraw.Draw(im).text((0, 0), ch, font=ImageFont.truetype(EMO, 109), embedded_color=True)
    im = im.crop(im.getbbox()); return im.resize((size, int(size * im.height / im.width)), Image.LANCZOS)
def card(bgpath, out, line, series):
    bg = Image.open(bgpath).convert("RGB")
    bg = bg.resize((W, int(bg.height * W / bg.width))) if bg.width / bg.height < W / H else bg.resize((int(bg.width * H / bg.height), H))
    l, t = (bg.width - W) // 2, (bg.height - H) // 2
    bg = ImageEnhance.Brightness(bg.crop((l, t, l + W, t + H)).filter(ImageFilter.GaussianBlur(14))).enhance(0.28)
    d = ImageDraw.Draw(bg); f = ImageFont.truetype(BOLD, 62)
    for i, (e, label, col) in enumerate([("\U0001F44D", "LIKE", (80, 170, 255)), ("\U0001F514", "SUBSCRIBE", (255, 60, 60)), ("\U0001F4E4", "SHARE", (70, 220, 120))]):
        cx = 360 + i * 600; em = emoji(e); bg.paste(em, (cx - em.width // 2, 80), em)
        d.text((cx - d.textlength(label, font=f) / 2, 335), label, font=f, fill=col, stroke_width=6, stroke_fill=(0, 0, 0))
    for k, (txt, col, size) in enumerate([(series, (255, 215, 0), 74), (line, (255, 255, 255), 52)]):
        ff = ImageFont.truetype(BOLD, size); d.text(((W - d.textlength(txt, font=ff)) / 2, 790 + k * 105), txt, font=ff, fill=col, stroke_width=6, stroke_fill=(0, 0, 0))
    bg.save(out, quality=95); print(out)
def main(cmd, argv):
    g = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    bg = find_image(g("--bg", ""))
    if not bg or not g("--line"): sys.exit(__doc__)
    card(bg, g("--out", f"{ARCHIVE}/endcard.jpg"), g("--line"), g("--series", "WARS THAT SHAPED THE WORLD"))
