"""Narration audio and word timings.
python3 -m docgen tts     [--short <id>]     Gemini TTS, plain text only (a style prefix gets read aloud)
python3 -m docgen timings [--short <id>]     RunPod Whisper word timestamps

Long video: one file per scene, audio/s<n>.clean.wav and build/words/s<n>.json. A scene's "voice" decides the source:
  "narrator" (default)  Gemini TTS of the narration
  "asset:<id>"          an existing voice file <asset dir>/<id>.wav (the Kokoro line a talking clip was made from)
  "clip"                the audio track of the scene's own clip (an LTX character who speaks)"""
import base64, json, os, subprocess, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from . import rp
from .common import ASSETS, dur, key, load_script, mkdirs
TRIM = "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse"   # ends only
MODEL = os.environ.get("DOCGEN_TTS_MODEL", "gemini-3.8-flash-tts")

def gemini_tts(text, out, voice="Charon"):
    body = {"contents": [{"parts": [{"text": text}]}], "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    for a in range(5):
        try:
            req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent", json.dumps(body).encode(), {"Content-Type": "application/json", "x-goog-api-key": key("GEMINI_API_KEY")})
            d = json.load(urllib.request.urlopen(req, timeout=300)); break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or a == 4: raise RuntimeError(f"TTS http {e.code}")
            time.sleep(8 * (a + 1))
    part = next(p for p in d["candidates"][0]["content"]["parts"] if "inlineData" in p)["inlineData"]
    pcm = out + ".pcm"; open(pcm, "wb").write(base64.b64decode(part["data"]))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", pcm, "-af", TRIM, out], check=True); os.remove(pcm)

def whisper(pairs):
    """pairs: {name: (wav, out_json)}; skips existing outputs."""
    jobs = {n: ("flux", rp.submit("flux", {"mode": "transcribe", "audio": base64.b64encode(open(a, "rb").read()).decode(), "task": "transcribe", "language": "en", "return_timestamps": "word"}))
            for n, (a, o) in pairs.items() if not os.path.exists(o)}
    bad = []
    for n, v in rp.wait(jobs, every=3).items():
        if "error" in v: bad.append(n); print("whisper FAIL", n, v["error"]); continue
        json.dump(v, open(pairs[n][1], "w")); print("whisper ok", n, flush=True)
    if bad: sys.exit(1)

def short_text(sc): return " ".join(s["text"] for s in sc["segments"])

def main(cmd, argv):
    sid = argv[argv.index("--short") + 1] if "--short" in argv else None
    if sid:
        D = f"shorts/{sid}"; sc = json.load(open(f"{D}/script.json"))
        if cmd == "tts":
            if not os.path.exists(f"{D}/voice.wav"): gemini_tts(short_text(sc), f"{D}/voice.wav", sc.get("narrator_voice", "Charon"))
            print(f"{D}/voice.wav", round(dur(f"{D}/voice.wav"), 1), "s")
        else:
            pairs = {"main": (f"{D}/voice.wav", f"{D}/words.json")}
            if sc.get("intro"): pairs["intro"] = (sc["intro"]["audio"], f"{D}/intro_words.json")
            whisper(pairs)
        return
    script = load_script(); scenes = script["scenes"]; mkdirs("audio", "build/words")
    if cmd == "tts":
        def one(s):
            n = s["n"]; out = f"audio/s{n}.clean.wav"; v = s.get("voice", "narrator")
            if os.path.exists(out): return n, "cached"
            if v.startswith("asset:"):
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{ASSETS}/{v[6:]}.wav", "-ar", "24000", "-ac", "1", out], check=True); return n, "asset"
            if v == "clip":
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", s["clip"], "-vn", "-ar", "24000", "-ac", "1", out], check=True); return n, "clip"
            try: gemini_tts(s["narration"], out, script.get("narrator_voice", "Charon")); return n, "ok"
            except Exception as e: return n, f"FAILED {e}"
        bad = 0
        with ThreadPoolExecutor(3) as ex:
            for n, r in ex.map(one, scenes):
                print("tts", n, r, flush=True); bad += r.startswith("FAILED")
        print("total narration s:", round(sum(dur(f"audio/s{s['n']}.clean.wav") for s in scenes if os.path.exists(f"audio/s{s['n']}.clean.wav")), 1))
        if bad: sys.exit(1)
    else:
        whisper({s["n"]: (f"audio/s{s['n']}.clean.wav", f"build/words/s{s['n']}.json") for s in scenes})
