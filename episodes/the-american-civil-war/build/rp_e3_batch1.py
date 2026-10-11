import json, sys; sys.path.insert(0, "build")
import rp
SC = json.load(open("script/script.json"))["scenes"]; NAR = {s["asset"]: s["narration"] for s in SC}
P = "Cinematic realistic portrait photograph with muted sepia-tinged colour grading, authentic 1860s American costume, period accurate, "
H = "Photorealistic historical reconstruction in the style of 1860s American photography and illustration, muted tones, authentic 1861-1865 uniforms and clothing, no modern objects, "
G = {
 "reporter_sumter": (P + "head and shoulders of a middle-aged American newspaper correspondent with side-whiskers in a dark frock coat, cravat and top hat, standing on a Charleston seawall at dawn with harbour mist and a distant fort behind him, facing the camera, mouth slightly open as if speaking", "9:16"),
 "historian_amend": (P + "head and shoulders of a distinguished grey-bearded American scholar with spectacles in a dark frock coat and white shirt, seated in a book-lined study holding a thick bound book, candlelight, facing the camera, mouth slightly open as if speaking", "9:16"),
 "reporter_appomattox": (P + "head and shoulders of a middle-aged American newspaper correspondent with side-whiskers in a dark frock coat and cravat, standing in front of a small brick farmhouse with a porch in spring, soldiers in blue behind him, facing the camera, mouth slightly open as if speaking", "9:16"),
 "usct": (P + "dignified African American Union soldier of the United States Colored Troops in a dark blue frock coat and kepi, standing in a spring army camp with tents and fellow soldiers behind him, facing the camera, medium shot, calm determined expression, mouth slightly open as if speaking", "16:9"),
 "tension": (H + "a crowded 1860 American city street with men reading newspapers and arguing, a political rally banner in the background, tense mood", "16:9"),
 "resources": (H + "split scene: on the left a busy Northern iron foundry and locomotive works with smoking chimneys, on the right a Southern cotton field with fields stretching to the horizon, 1861", "16:9"),
 "graves": (H + "rows of white grave markers in a military cemetery at dusk, a lone flag, mist", "16:9"),
}
jobs = {}
for k, (p, a) in G.items():
    jobs[k] = ("qwen", rp.submit("qwen", {"model": "qwen", "prompt": p, "aspect_ratio": a, "project_id": "wars_e3", "frame_id": k}))
BG = {"bgm_long": "solemn American Civil War era orchestral underscore, mournful fiddle and cello, distant snare drum, reflective and building, historical documentary, no vocals, steady energy so a narrator's voice sits on top",
      "bgm_a": "tense dramatic orchestral underscore, low drums and strings building, historical documentary, no vocals",
      "bgm_b": "investigative documentary underscore, restrained strings, ticking percussion, rising tension, no vocals",
      "bgm_c": "reflective hopeful orchestral, solemn piano and warm strings, slow, historical documentary, no vocals"}
for k, p in BG.items():
    jobs[k] = ("bgm", rp.submit("bgm", {"mode": "bgm", "prompt": p, "duration_s": 120 if k == "bgm_long" else 50, "steps": 20, "guidance": 7.0, "project_id": "wars_e3", "frame_id": k}))
T = {"tts_rep_sumter": ("am_michael", NAR["reporter_sumter"]), "tts_historian": ("am_onyx", NAR["historian_amend"]), "tts_rep_appomattox": ("am_michael", NAR["reporter_appomattox"]),
     "tts_follow": ("am_michael", "Follow for the full story."), "tts_follow_myth": ("am_michael", "Follow for more history myths.")}
for k, (v, t) in T.items():
    jobs[k] = ("flux", rp.submit("flux", {"mode": "tts", "engine": "kokoro", "text": t, "voice": v, "speed": 0.95, "lang_code": "a", "project_id": "wars_e3", "frame_id": k}))
json.dump({k: list(v) for k, v in jobs.items()}, open("shorts/rp/e3b1_jobs.json", "w"), indent=1); print("submitted", len(jobs), flush=True)
res = rp.wait(jobs); json.dump(res, open("shorts/rp/e3b1_out.json", "w"), indent=1)
for k, v in res.items(): print(k, "ERROR " + v["error"] if "error" in v else "ok", flush=True)
