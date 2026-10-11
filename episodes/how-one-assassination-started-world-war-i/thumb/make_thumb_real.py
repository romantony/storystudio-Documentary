import base64, json, os, subprocess, urllib.request
MODEL = "models/gemini-3.1-flash-image"   # Nano Banana 2
KEY = os.environ["GEMINI_API_KEY"]
here = os.path.dirname(os.path.abspath(__file__))
base = os.path.join(here, "base_real.jpg")
# real photo: Franz Ferdinand & Sophie at Sarajevo Station (Commons, CC0), cover-cropped to 1280x720
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",os.path.join(here,"..","images_period","p09.jpg"),
    "-vf","scale=1280:-2,crop=1280:720:0:30","-q:v","2",base],check=True)
prompt = ("This is a real historical photograph from 1914. Turn it into a 16:9 YouTube thumbnail. Keep the photograph itself unchanged "
          "(same people, same framing), only slightly boost contrast. Add very large, bold, colourful title text with a thick black outline and "
          "a subtle glow, in the empty area on the right side: first line 'ONE SHOT' in vivid red-orange, second line 'WORLD WAR' in bright yellow. "
          "Spell the text exactly. No other text, logos or watermarks.")
body = {"contents": [{"parts": [{"text": prompt}, {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(open(base, "rb").read()).decode()}}]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "16:9"}}}
req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/{MODEL}:generateContent",
    json.dumps(body).encode(), {"Content-Type": "application/json", "x-goog-api-key": KEY})
d = json.load(urllib.request.urlopen(req, timeout=300))
img = next(p["inlineData"] for p in d["candidates"][0]["content"]["parts"] if "inlineData" in p)
raw = os.path.join(here, "nb2_raw.img"); open(raw, "wb").write(base64.b64decode(img["data"]))
out = os.path.join(here, "thumbnail.jpg")
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",raw,"-vf","scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720","-frames:v","1","-q:v","3",out],check=True)
print(out, os.path.getsize(out))
