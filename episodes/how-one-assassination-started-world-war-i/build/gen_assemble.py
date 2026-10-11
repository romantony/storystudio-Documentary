import json, os, re, subprocess, difflib
sc = {s["n"]: s for s in json.load(open("script/script.json"))["scenes"]}
W, H, FPS = 1920, 1080, 30
KEEP_STORYBLOCKS = {3: "clips/s03_355075065.mp4", 14: "clips/s14_352152708.mp4", 24: "clips/s24_347323273.mp4"}
CROP = {2: "iw:ih*0.92:0:0", 9: "iw:ih*0.91:0:0", 12: "iw:ih*0.92:0:ih*0.07", 13: "iw:ih*0.80:0:0", 16: "iw*0.88:ih*0.64:iw*0.06:ih*0.16"}
order = []
for n in sorted(k for k in sc if "after" not in sc[k]):
    order.append(n)
    order += [k for k in sc if sc[k].get("after") == n]
tl, t0 = [], 0.0
for n in order:
    aud = f"audio/s{n}.clean.wav"
    d = float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",aud]))
    L = round(d + 0.35, 3)
    img = {25: "images_period/cta_mid.jpg", 26: "images_period/cta_end.jpg"}.get(n) or KEEP_STORYBLOCKS.get(n, f"images_period/p{n:02d}.jpg")
    tl.append(dict(scene=n, start=round(t0, 3), end=round(t0 + L, 3), audio=aud, clip_or_image=img)); t0 += L
json.dump(tl, open("build/timeline.json", "w"), indent=1)
print("order:", order, "total", round(t0, 1))

cmds = []
for e in tl:
    n = e["scene"]; L = round(e["end"] - e["start"], 3); src = e["clip_or_image"]; out = f"build/seg{n}.mp4"
    fade = f"fade=t=in:st=0:d=0.25,fade=t=out:st={L-0.25:.3f}:d=0.25"
    aud = f"-i {e['audio']} -af aresample=48000,apad=pad_dur=0.35 -ar 48000 -ac 2"
    enc = f"-c:v libx264 -preset veryfast -crf 18 -c:a aac -b:a 192k -t {L} -movflags +faststart"
    if src.endswith(".mp4"):
        norm = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,format=yuv420p"
        cmds.append(f"ffmpeg -y -loglevel error -stream_loop -1 -ss 0.5 -t {L} -i {src} {aud} -vf \"{norm},{fade}\" -map 0:v -map 1:a {enc} {out}")
    else:
        N = int(round(L * FPS))
        pre = f"crop={CROP[n]}," if n in CROP else ""
        x = f"(iw-iw/zoom)*on/{N}" if n % 2 else f"(iw-iw/zoom)*(1-on/{N})"
        fc = (f"[0:v]{pre}split[a][b];[a]scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,boxblur=90:8,eq=brightness=-0.3:saturation=0.6[bg];"
              f"[b]scale=3840:2160:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,"
              f"zoompan=z='1+0.08*on/{N}':x='{x}':y='ih/2-(ih/zoom/2)':d={N}:s={W}x{H}:fps={FPS},format=yuv420p,{fade}[v]")
        cmds.append(f"ffmpeg -y -loglevel error -loop 1 -framerate {FPS} -i {src} {aud} -filter_complex \"{fc}\" -map \"[v]\" -map 1:a {enc} {out}")
cmds = [c for c in cmds if not os.path.exists(c.rsplit(" ",1)[1])]
open("build/seg_cmds.txt", "w").write("\n".join(cmds) + ("\n" if cmds else ""))
open("build/list.txt", "w").write("".join(f"file 'seg{e['scene']}.mp4'\n" for e in tl))

# ---- captions: script words timed by Replicate Whisper word timestamps ----
norm_t = lambda w: re.sub(r"[^a-z0-9]", "", w.lower())
def scene_words(n):
    script = sc[n]["narration"].split()
    wh = json.load(open(f"build/words/s{n}.json"))["chunks"]
    A = [norm_t(w) for w in script]; B = [norm_t(c["text"]) for c in wh]
    times = [None] * len(script)
    for blk in difflib.SequenceMatcher(None, A, B, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            ts = wh[blk.b + k]["timestamp"]; times[blk.a + k] = (ts[0], ts[1] if ts[1] is not None else ts[0] + 0.3)
    # interpolate unmatched words between known neighbours
    i = 0
    while i < len(times):
        if times[i] is None:
            j = i
            while j < len(times) and times[j] is None: j += 1
            lo = times[i-1][1] if i > 0 else 0.0
            hi = times[j][0] if j < len(times) else (wh[-1]["timestamp"][1] or lo + 1)
            step = (hi - lo) / (j - i)
            for k in range(i, j): times[k] = (lo + step * (k - i), lo + step * (k - i + 1))
            i = j
        else: i += 1
    return list(zip(script, times))
FUNC = {"the","a","an","of","to","and","in","with","that","very","for","on","at","by","but","or","its","his","her","their"}
def chunk(words):
    out, cur = [], []
    for w, t in words:
        cur.append((w, t))
        endp = w[-1] in ".,;:?!"
        if (endp and len(cur) >= 3) or len(cur) >= 6:
            if len(cur) < 6 and not endp: continue
            if w.lower().strip(".,;:!?") in FUNC and len(cur) < 6: continue
            out.append(cur); cur = []
    if cur:
        if out and len(cur) <= 2: out[-1] += cur
        else: out.append(cur)
    return out
def t(x): h=int(x//3600); m=int(x%3600//60); s=x%60; return f"{h}:{m:02d}:{s:05.2f}"
HI, LO = r"{\c&H00D7FF&}", r"{\c&HFFFFFF&}"
ev, nwords = [], 0
for e in tl:
    n = e["scene"]; off = e["start"]
    chunks = chunk(scene_words(n))
    for ci, ch in enumerate(chunks):
        end_chunk = ch[-1][1][1] + 0.12
        if ci + 1 < len(chunks): end_chunk = min(end_chunk, chunks[ci+1][0][1][0])
        brk = (len(ch) + 1) // 2
        for i, (w, (s0, s1)) in enumerate(ch):
            st = off + s0; en = off + (ch[i+1][1][0] if i + 1 < len(ch) else end_chunk)
            if en - st < 0.05: en = st + 0.05
            parts = []
            for j, (wj, _) in enumerate(ch):
                if j == brk and len(ch) > 3: parts.append(r"\N")
                parts.append((HI if j == i else LO) + wj.upper() if False else (HI if j == i else LO) + wj)
            txt = " ".join(parts).replace(" \\N ", "\\N")
            ev.append(f"Dialogue: 0,{t(st)},{t(en)},Cap,,0,0,0,,{txt}"); nwords += 1
hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Cap,DejaVu Sans,92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,2,5,140,140,40,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
open("build/caps.ass", "w").write(hdr + "\n".join(ev) + "\n")
print("caption word-events:", nwords)
total = tl[-1]["end"]
open("build/assemble.sh", "w").write(f"""#!/bin/bash
# Generated by build/gen_assemble.py. Run from the run folder. Captions: Replicate Whisper word timings, centred, current word highlighted.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p out
xargs -d '\\n' -P 4 -I{{}} bash -c '{{}}' < build/seg_cmds.txt
ffmpeg -y -loglevel error -f concat -safe 0 -i build/list.txt -c copy build/base.mp4
ffmpeg -y -loglevel error -i build/base.mp4 -vf "ass=build/caps.ass" -c:v libx264 -crf 20 -preset veryfast -pix_fmt yuv420p -c:a copy build/captioned.mp4
ffmpeg -y -loglevel error -i build/captioned.mp4 -stream_loop -1 -i bgm/bgm.mp3 -filter_complex \\
 "[1:a]volume=0.35,afade=t=in:d=2,afade=t=out:st={total-3:.2f}:d=3,atrim=0:{total:.2f}[bg];[0:a]alimiter=limit=0.7:level=disabled,asplit=2[vo][sc];[bg][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[ducked];[vo][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,loudnorm=I=-16:TP=-2:LRA=11,aresample=48000,alimiter=limit=0.6:attack=0.5:release=30:level=disabled[a]" \\
 -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -shortest out/how-one-assassination-started-world-war-i.mp4
""")
