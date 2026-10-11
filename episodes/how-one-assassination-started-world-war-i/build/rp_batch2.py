import json, sys, urllib.request; sys.path.insert(0, "build")
import rp
b1 = json.load(open("shorts/rp/batch1_out.json")); A = lambda k: b1[k]["image_url"]
jobs = {}
ST = "Authentic black-and-white archival photograph from 1914, film grain, soft vintage lens, period accurate, vertical composition, "
jobs["q_council2"] = ("qwen", rp.submit("qwen", {"model": "qwen", "prompt": ST + "a group of older men in plain dark 1914 frock coats and civilian suits with high collars and moustaches, gathered around a table with papers and a map in a Vienna office, grave expressions, no uniforms, no insignia, no emblems", "aspect_ratio": "9:16", "project_id": "wwi_shorts", "frame_id": "q_council2"}))
for k in ("q_car", "q_stride"):
    jobs["anim_" + k] = ("flux", rp.submit("flux", {"mode": "animate", "image_url": A(k), "duration_s": 6, "effect": "zoom_in", "fps": 24, "vid_width": 576, "vid_height": 1024, "project_id": "wwi_shorts", "frame_id": "anim_" + k}))
jobs["itk_reporter"] = ("itk", rp.submit("itk", {"prompt": "a 1914 newspaper war correspondent speaking calmly to the camera in a street, subtle natural head movement", "image": A("q_reporter"), "audio": b1["rep_tts"]["audio"], "resolution": "480p", "enable_safety_checker": True}))
json.dump({k: list(v) for k, v in jobs.items()}, open("shorts/rp/batch2_jobs.json", "w"), indent=1); print("submitted", len(jobs), flush=True)
res = rp.wait(jobs); json.dump(res, open("shorts/rp/batch2_out.json", "w"), indent=1)
for k, v in res.items(): print(k, "ERROR " + v["error"] if "error" in v else "ok", flush=True)
