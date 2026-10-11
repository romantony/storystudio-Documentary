"""9:16 Short builder. Usage (from run folder): python3 build/gen_short.py <short_id> tts|words|build
Needs GEMINI_API_KEY (tts) / REPLICATE_API_TOKEN (words) in env. Plain-text TTS only (no style prefix)."""
import base64, difflib, json, os, re, subprocess, sys, time, urllib.error, urllib.request
sid, stage = sys.argv[1], sys.argv[2]
D = f"shorts/{sid}"
sc = json.load(open(f"{D}/script.json"))
W, H, FPS = 1080, 1920, 30
CARD_S = 2.5
os.makedirs(f"{D}/build", exist_ok=True); os.makedirs(f"{D}/out", exist_ok=True)
full_text = " ".join(s["text"] for s in sc["segments"])

def post(url, body, headers):
    req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None, headers)
    return json.load(urllib.request.urlopen(req, timeout=300))

if stage == "tts":
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash-tts:generateContent"
    body = {"contents": [{"parts": [{"text": full_text}]}], "generationConfig": {"responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Charon"}}}}}
    for attempt in (1, 2, 3):
        try:
            d = post(url, body, {"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]}); break
        except urllib.error.HTTPError as e:
            if attempt == 3 or e.code not in (429, 500, 502, 503, 504): sys.exit(f"TTS failed http {e.code}")
            time.sleep(8)
    part = next(p for p in d["candidates"][0]["content"]["parts"] if "inlineData" in p)["inlineData"]
    open(f"{D}/voice.pcm", "wb").write(base64.b64decode(part["data"]))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", f"{D}/voice.pcm",
        "-af", "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse", f"{D}/voice.wav"], check=True)
    os.remove(f"{D}/voice.pcm"); print("voice.wav ok")

elif stage == "words":
    sys.path.insert(0, "build"); import rp
    todo = {"main": (f"{D}/voice.wav", f"{D}/words.json")}
    if sc.get("intro"): todo["intro"] = (sc["intro"]["audio"], f"{D}/intro_words.json")
    jobs = {k: ("flux", rp.submit("flux", {"mode": "transcribe", "audio": base64.b64encode(open(a_, "rb").read()).decode(), "task": "transcribe", "language": "en", "return_timestamps": "word"})) for k, (a_, o_) in todo.items()}
    res = rp.wait(jobs, every=3)
    for k, (a_, o_) in todo.items():
        if "error" in res[k]: sys.exit(f"S2T {k} failed: {res[k]['error']}")
        json.dump(res[k], open(o_, "w")); print(o_, "ok (RunPod Whisper)")

elif stage == "build":
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f"{D}/voice.wav"]))
    norm = lambda w: re.sub(r"[^a-z0-9]", "", w.lower())
    def align(words, wh, dur_):
        A = [norm(w) for w in words]; B = [norm(c["text"]) for c in wh]
        tm = [None] * len(words)
        for blk in difflib.SequenceMatcher(None, A, B, autojunk=False).get_matching_blocks():
            for k in range(blk.size):
                ts_ = wh[blk.b + k]["timestamp"]; tm[blk.a + k] = (ts_[0], ts_[1] if ts_[1] is not None else ts_[0] + 0.3)
        i = 0
        while i < len(tm):
            if tm[i] is None:
                j = i
                while j < len(tm) and tm[j] is None: j += 1
                lo = tm[i-1][1] if i > 0 else 0.0; hi = tm[j][0] if j < len(tm) else dur_
                for k in range(i, j): tm[k] = (lo + (hi-lo)/(j-i)*(k-i), lo + (hi-lo)/(j-i)*(k-i+1))
                i = j
            else: i += 1
        return tm, sum(1 for a_ in A if a_ not in B)
    script, seg_of = [], []
    for i, s_ in enumerate(sc["segments"]):
        for w in s_["text"].split(): script.append(w); seg_of.append(i)
    times, miss = align(script, json.load(open(f"{D}/words.json"))["chunks"], dur)
    print("unmatched-by-whisper words:", miss)
    OFF = 0.0; intro_ev = []
    if sc.get("intro"):
        it = sc["intro"]; OFF = round(float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", it["video"]])), 3) + 0.25
        iw = it["text"].split(); itm, _ = align(iw, json.load(open(f"{D}/intro_words.json"))["chunks"], OFF)
    times = [(a_ + OFF, b_ + OFF) for a_, b_ in times]
    # segment boundaries = first word of each segment
    starts = []
    for i in range(len(sc["segments"])):
        starts.append(OFF if i == 0 else times[seg_of.index(i)][0] - 0.05)
    total = round(OFF + dur + 0.4, 3)
    ends = starts[1:] + [total]
    cmds, lst = [], []
    if OFF:
        cmds.append(f"ffmpeg -y -loglevel error -i {sc['intro']['video']} -filter_complex \"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:5,eq=brightness=-0.35[bg];"
                    f"[b]scale={W}:-2,hue=s=0,noise=alls=12:allf=t,eq=contrast=1.1[fg];[bg][fg]overlay=0:(H-h)/2-60,fps={FPS},format=yuv420p,tpad=stop_mode=clone:stop_duration=1,fade=t=out:st={OFF-0.15:.3f}:d=0.15[v]\" -map \"[v]\" -t {OFF} -an -c:v libx264 -preset veryfast -crf 18 {D}/build/seg_intro.mp4")
        lst.append("file 'seg_intro.mp4'\n")
    for i, (s, a, b) in enumerate(zip(sc["segments"], starts, ends)):
        L = round(b - a, 3); N = max(2, int(round(L * FPS))); out = f"{D}/build/seg{i}.mp4"
        fade = f"fade=t=in:st=0:d=0.15,fade=t=out:st={max(L-0.15,0):.3f}:d=0.15" if i else f"fade=t=out:st={max(L-0.15,0):.3f}:d=0.15"
        zoom = f"1+0.10*on/{N}" if i % 2 == 0 else f"1.10-0.10*on/{N}"
        src = s["image"] if "/" in s["image"] else f"images_period/{s['image']}.jpg"
        from PIL import Image as _I
        mode = ("fit" if _I.open(src).height < 1100 else "crop")   # low-res photos: whole frame on blurred fill, no tight crop
        if mode == "fit":   # low-res: 1080x1280 window (1.4x upscale, not 3x) over blurred full-frame fill
            fc = (f"[0:v]split[a][b];[a]scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},boxblur=60:6,eq=brightness=-0.3:saturation=0.6[bg];"
                  f"[b]scale={W*2}:2560:force_original_aspect_ratio=increase,crop={W*2}:2560:'min(max(iw*{s['fx']}-{W},0),iw-{W*2})':0[fg];"
                  f"[bg][fg]overlay=0:(H-h)/2-80,setsar=1,"
                  f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={N}:s={W}x{H}:fps={FPS},format=yuv420p,{fade}[v]")
        else:                        # portrait crop around the subject (fx = horizontal focus 0..1)
            fc = (f"[0:v]scale=-2:{H*2}:force_original_aspect_ratio=increase,"
                  f"crop={W*2}:{H*2}:'min(max(iw*{s['fx']}-{W},0),iw-{W*2})':0,setsar=1,"
                  f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={N}:s={W}x{H}:fps={FPS},format=yuv420p,{fade}[v]")
        cmds.append(f"ffmpeg -y -loglevel error -loop 1 -framerate {FPS} -i {src} -filter_complex \"{fc}\" -map \"[v]\" -t {L} -c:v libx264 -preset veryfast -crf 18 {out}")
        lst.append(f"file 'seg{i}.mp4'\n")
    open(f"{D}/build/seg_cmds.txt", "w").write("\n".join(cmds) + "\n")
    # end card (like / subscribe / share) for the last CARD_S seconds
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
    EMO = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"; BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    def emoji(ch, size):
        im = Image.new("RGBA", (136, 128), (0, 0, 0, 0)); ImageDraw.Draw(im).text((0, 0), ch, font=ImageFont.truetype(EMO, 109), embedded_color=True)
        im = im.crop(im.getbbox()); return im.resize((size, int(size * im.height / im.width)), Image.LANCZOS)
    bg = Image.open("images_period/p09.jpg").convert("RGB"); bg = bg.resize((int(bg.width * H / bg.height), H))
    l = (bg.width - W) // 2; bg = ImageEnhance.Brightness(bg.crop((l, 0, l + W, H)).filter(ImageFilter.GaussianBlur(14))).enhance(0.28)
    d = ImageDraw.Draw(bg); f = ImageFont.truetype(BOLD, 64)
    for k, (e, lab, col) in enumerate([("\U0001F44D", "LIKE", (80, 170, 255)), ("\U0001F514", "FOLLOW", (255, 60, 60)), ("\U0001F4E4", "SHARE", (70, 220, 120))]):
        y = 520 + k * 320; em = emoji(e, 190); bg.paste(em, (W // 2 - em.width // 2 - 230, y), em)
        d.text((W // 2 - 90, y + 40), lab, font=f, fill=col, stroke_width=6, stroke_fill=(0, 0, 0))
    ft = ImageFont.truetype(BOLD, 56); t1 = "WARS THAT SHAPED THE WORLD"
    d.text(((W - d.textlength(t1, font=ft)) / 2, 1500), t1, font=ft, fill=(255, 215, 0), stroke_width=5, stroke_fill=(0, 0, 0))
    bg.save(f"{D}/build/card.jpg", quality=95)
    cmds.append(f"ffmpeg -y -loglevel error -loop 1 -framerate {FPS} -i {D}/build/card.jpg -vf \"fade=t=in:st=0:d=0.2,format=yuv420p\" -t {CARD_S} -c:v libx264 -preset veryfast -crf 18 {D}/build/segcard.mp4")
    open(f"{D}/build/seg_cmds.txt", "w").write("\n".join(cmds) + "\n"); lst.append("file 'segcard.mp4'\n")
    open(f"{D}/build/list.txt", "w").write("".join(lst))
    # captions: max 3 words, centred, current word gold
    def ts(x): return f"{int(x//3600)}:{int(x%3600//60):02d}:{x%60:05.2f}"
    HI, LO = r"{\c&H00D7FF&}", r"{\c&HFFFFFF&}"
    allw = (iw if OFF else []) + script; alt = (itm if OFF else []) + times
    chunks, cur = [], []
    for k, w in enumerate(allw):
        if cur and (len(cur) == 3 or len(" ".join(allw[j] for j in cur + [k])) > 16 or allw[cur[-1]][-1] in ".,;:?!" or (OFF and k == len(iw))):
            chunks.append(cur); cur = []
        cur.append(k)
    if cur: chunks.append(cur)
    ev = []
    for ci, ch in enumerate(chunks):
        cend = alt[ch[-1]][1] + 0.12
        if ci + 1 < len(chunks): cend = min(cend, alt[chunks[ci+1][0]][0])
        for ii, k in enumerate(ch):
            st = alt[k][0]; en = alt[ch[ii+1]][0] if ii + 1 < len(ch) else cend
            if en - st < 0.05: en = st + 0.05
            txt = " ".join((HI if j == k else LO) + allw[j] for j in ch)
            ev.append(f"Dialogue: 0,{ts(st)},{ts(en)},Cap,,0,0,0,,{txt}")
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Cap,DejaVu Sans,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,2,5,70,70,0,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    open(f"{D}/build/caps.ass", "w").write(hdr + "\n".join(ev) + "\n")
    full = total + CARD_S
    bgm = sc.get("bgm", "bgm/bgm.mp3"); sfx = sc.get("sfx", [])
    ins = f"-i $D/build/captioned.mp4 -i $D/build/voicefull.wav -stream_loop -1 -i {bgm} " + " ".join(f"-i {x['file']}" for x in sfx)
    sfx_f = "".join(f"[{3+k}:a]aresample=48000,volume={x.get('volume',0.5)},adelay={int((x['at'] if 'at' in x else starts[x['segment']])*1000)}|{int((x['at'] if 'at' in x else starts[x['segment']])*1000)}[x{k}];" for k, x in enumerate(sfx))
    mix = f"[bg]{''.join(f'[x{k}]' for k in range(len(sfx)))}amix=inputs={1+len(sfx)}:duration=first:dropout_transition=0:normalize=0[bgs];" if sfx else "[bg]anull[bgs];"
    vf = (f"[1:a]aresample=48000,apad=whole_dur={full:.2f},alimiter=limit=0.7:level=disabled,asplit=2[vo][sc];{sfx_f}"
          f"[2:a]aresample=48000,volume=0.25,afade=t=in:d=1,afade=t=out:st={full-2.5:.2f}:d=2.5,atrim=0:{full:.2f}[bg];{mix}"
          f"[bgs][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[ducked];[vo][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,loudnorm=I=-12.5:TP=-1.5:LRA=11,aresample=48000,alimiter=limit=0.8:attack=0.5:release=30:level=disabled[a]")
    if OFF:
        vo = (f"ffmpeg -y -loglevel error -i {sc['intro']['audio']} -i $D/voice.wav -filter_complex \"[0:a]aresample=48000,apad=whole_dur={OFF}[i];[1:a]aresample=48000,adelay={int(OFF*1000)}|{int(OFF*1000)}[n];[i][n]amix=inputs=2:duration=longest:normalize=0\" $D/build/voicefull.wav")
    else:
        vo = "cp $D/voice.wav $D/build/voicefull.wav"
    open(f"{D}/build/assemble.sh", "w").write(f"""#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
D={D}
xargs -d '\\n' -P 4 -I{{}} bash -c '{{}}' < $D/build/seg_cmds.txt
ffmpeg -y -loglevel error -f concat -safe 0 -i $D/build/list.txt -c copy $D/build/base.mp4
ffmpeg -y -loglevel error -i $D/build/base.mp4 -vf "ass=$D/build/caps.ass" -c:v libx264 -crf 20 -preset veryfast -pix_fmt yuv420p $D/build/captioned.mp4
{vo}
ffmpeg -y -loglevel error {ins} -filter_complex \\
 "{vf}" \\
 -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -t {full:.2f} $D/out/{sid}.mp4
""")
    print(f"segments {len(sc['segments'])}, intro {OFF:.1f}s, voice {dur:.1f}s, total {full:.1f}s")
