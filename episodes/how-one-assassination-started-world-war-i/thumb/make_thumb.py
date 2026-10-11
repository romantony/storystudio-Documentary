import base64, json, os, subprocess, urllib.request
MODEL = "models/gemini-3.1-flash-image"
KEY = os.environ["GEMINI_API_KEY"]
here = os.path.dirname(os.path.abspath(__file__))
prompt = ("Cinematic 16:9 background for a history documentary thumbnail: a deserted 1914 European city street at dawn, "
          "wet cobblestones, a vintage open-top touring car seen only as a dark silhouette on the left third, drifting smoke and mist, "
          "desaturated sepia and slate-blue palette, high contrast, dramatic low light, the right half of the frame mostly dark empty space. "
          "No people's faces, no text, no letters, no logos.")
body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "16:9"}}}
req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/{MODEL}:generateContent",
    json.dumps(body).encode(), {"Content-Type": "application/json", "x-goog-api-key": KEY})
d = json.load(urllib.request.urlopen(req, timeout=300))
img = next(p["inlineData"] for p in d["candidates"][0]["content"]["parts"] if "inlineData" in p)
raw = os.path.join(here, "bg_raw.img"); open(raw, "wb").write(base64.b64decode(img["data"]))
print("mime", img.get("mimeType"))
font = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
def dt(text, y, size):
    return (f"drawtext=fontfile={font}:text='{text}':fontsize={size}:fontcolor=white:borderw=8:bordercolor=black:"
            f"x=w-tw-60:y={y}")
vf = "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720," + dt("ONE SHOT", 190, 100) + "," + dt("WORLD WAR", 310, 100)
out = os.path.join(here, "thumbnail.jpg")
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",raw,"-vf",vf,"-frames:v","1","-q:v","3",out],check=True)
print(out, os.path.getsize(out))
