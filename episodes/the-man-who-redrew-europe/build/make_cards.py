from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
W, H = 1920, 1080
EMO = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
def emoji(ch, size=300):
    im = Image.new("RGBA", (136, 128), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((0, 0), ch, font=ImageFont.truetype(EMO, 109), embedded_color=True)
    return im.crop(im.getbbox()).resize((size, int(size * im.crop(im.getbbox()).height / im.crop(im.getbbox()).width)), Image.LANCZOS)
def card(bgpath, out, line):
    bg = Image.open(bgpath).convert("RGB")
    bg = bg.resize((W, int(bg.height * W / bg.width))) if bg.width / bg.height < W / H else bg.resize((int(bg.width * H / bg.height), H))
    l, t = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((l, t, l + W, t + H)).filter(ImageFilter.GaussianBlur(14))
    bg = ImageEnhance.Brightness(bg).enhance(0.28)
    d = ImageDraw.Draw(bg)
    items = [("\U0001F44D", "LIKE", (80, 170, 255)), ("\U0001F514", "SUBSCRIBE", (255, 60, 60)), ("\U0001F4E4", "SHARE", (70, 220, 120))]
    f = ImageFont.truetype(BOLD, 62)
    for i, (e, label, col) in enumerate(items):
        cx = 360 + i * 600
        em = emoji(e, 230); bg.paste(em, (cx - em.width // 2, 80), em)
        tw = d.textlength(label, font=f)
        d.text((cx - tw / 2, 335), label, font=f, fill=col, stroke_width=6, stroke_fill=(0, 0, 0))
    f2 = ImageFont.truetype(BOLD, 74)
    for k, (txt, col) in enumerate([("WARS THAT SHAPED THE WORLD", (255, 215, 0)), (line, (255, 255, 255))]):
        ff = f2 if k == 0 else ImageFont.truetype(BOLD, 52)
        tw = d.textlength(txt, font=ff); d.text(((W - tw) / 2, 790 + k * 105), txt, font=ff, fill=col, stroke_width=6, stroke_fill=(0, 0, 0))
    bg.save(out, quality=95); print(out)
card("images_period/versailles.jpg", "images_period/endcard.jpg", "Next: The American Civil War")
