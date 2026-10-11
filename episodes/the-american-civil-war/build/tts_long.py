"""Long-form narration: Gemini TTS (Charon) per scene for narrated scenes; Kokoro wavs for itk scenes; LTX clip audio for the soldier scene. Then RunPod Whisper -> build/words/s{n}.json"""
import base64, json, os, re, subprocess, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "build"); import rp
KEY = re.search(r"AIza[A-Za-z0-9_-]{20,}", open(rp.DOC).read()).group(0)
sc = json.load(open("script/script.json"))["scenes"]
os.makedirs("audio", exist_ok=True); os.makedirs("build/words", exist_ok=True)
TRIM = "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse"
ITK = {"reporter_sumter": "tts_rep_sumter", "historian_amend": "tts_historian", "reporter_appomattox": "tts_rep_appomattox"}
def tts(s):
    n = s["n"]; out = f"audio/s{n}.clean.wav"
    if os.path.exists(out): return n, "cached"
    if s["asset"] in ITK:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"shorts/assets/{ITK[s['asset']]}.wav", "-ar", "24000", "-ac", "1", out], check=True); return n, "kokoro"
    if s["asset"] == "usct":
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", "shorts/assets/ltx_usct.mp4", "-vn", "-ar", "24000", "-ac", "1", out], check=True); return n, "ltx-audio"
    body = {"contents": [{"parts": [{"text": s["narration"]}]}], "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Charon"}}}}}
    for a in range(5):
        try:
            req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash-tts:generateContent", json.dumps(body).encode(), {"Content-Type": "application/json", "x-goog-api-key": KEY})
            d = json.load(urllib.request.urlopen(req, timeout=300)); break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or a == 4: return n, f"FAILED {e.code}"
            time.sleep(8 * (a + 1))
    part = next(p for p in d["candidates"][0]["content"]["parts"] if "inlineData" in p)["inlineData"]
    open(f"audio/s{n}.pcm", "wb").write(base64.b64decode(part["data"]))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", f"audio/s{n}.pcm", "-af", TRIM, out], check=True)
    os.remove(f"audio/s{n}.pcm"); return n, "ok"
with ThreadPoolExecutor(3) as ex:
    for n, r in ex.map(tts, sc): print("tts", n, r, flush=True)
jobs = {}
for s in sc:
    n = s["n"]
    if os.path.exists(f"build/words/s{n}.json"): continue
    if not os.path.exists(f"audio/s{n}.clean.wav"): continue
    jobs[n] = ("flux", rp.submit("flux", {"mode": "transcribe", "audio": base64.b64encode(open(f"audio/s{n}.clean.wav", "rb").read()).decode(), "task": "transcribe", "language": "en", "return_timestamps": "word"}))
res = rp.wait(jobs, every=3)
for n, v in res.items():
    if "error" in v: print("whisper", n, "FAILED", v["error"]); continue
    json.dump(v, open(f"build/words/s{n}.json", "w")); print("whisper", n, "ok", flush=True)
tot = sum(float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f"audio/s{s['n']}.clean.wav"])) for s in sc if os.path.exists(f"audio/s{s['n']}.clean.wav"))
print("total narration s:", round(tot, 1))
