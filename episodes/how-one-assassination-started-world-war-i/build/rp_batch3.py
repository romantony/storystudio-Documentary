import json, sys, urllib.request; sys.path.insert(0, "build")
import rp
b1 = json.load(open("shorts/rp/batch1_out.json")); b2 = json.load(open("shorts/rp/batch2_out.json"))
NEG = "music, speech, voice, singing"
J = {
 "sfx_car": {"mode": "i2a", "image_url": b1["q_car"]["image_url"], "prompt": "narrow cobblestone street ambience, distant crowd murmur, old car engine idling, footsteps on cobblestones", "duration_s": 8},
 "sfx_stride": {"mode": "i2a", "image_url": b1["q_stride"]["image_url"], "prompt": "tense crowd murmur, hurried footsteps on cobblestones, car door, then two sharp gunshots echoing between buildings", "duration_s": 8},
 "sfx_council": {"mode": "i2a", "image_url": b2["q_council2"]["image_url"], "prompt": "quiet office room tone, paper rustling, a clock ticking, low murmur", "duration_s": 8},
 "sfx_reporter": {"mode": "v2a", "video_url": b2["itk_reporter"]["result"], "prompt": "quiet European street ambience, distant footsteps and murmuring crowd, horse and carriage far away", "duration_s": 6},
}
jobs = {k: ("mm", rp.submit("mm", {**v, "negative_prompt": NEG, "project_id": "wwi_shorts", "frame_id": k})) for k, v in J.items()}
print("submitted", len(jobs), flush=True)
res = rp.wait(jobs, every=4); json.dump(res, open("shorts/rp/batch3_out.json", "w"), indent=1)
for k, v in res.items():
    print(k, "ERROR " + v["error"] if "error" in v else "ok " + str({a: str(b)[:80] for a, b in v.items() if a in ("audio_url", "duration_s")}), flush=True)
    if "audio_url" in v: open(f"shorts/assets/{k}.mp3", "wb").write(urllib.request.urlopen(urllib.request.Request(v["audio_url"], headers={"User-Agent": "curl/8.5.0"}), timeout=120).read())
