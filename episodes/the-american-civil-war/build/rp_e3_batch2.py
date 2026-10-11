import json, sys, urllib.request; sys.path.insert(0, "build")
import rp, ltx
o = json.load(open("shorts/rp/e3b1_out.json")); U = lambda k: o[k]["image_url"]; AU = lambda k: o[k]["audio"]
ITK = {
 "itk_sumter": ("reporter_sumter", "tts_rep_sumter", "a newspaper correspondent in a top hat and dark frock coat speaking calmly to the camera on a seawall at dawn, subtle natural head movement, mist drifting"),
 "itk_historian": ("historian_amend", "tts_historian", "a bearded scholar with spectacles speaking thoughtfully to the camera in a candlelit study, subtle head movement, hand holding a book"),
 "itk_appomattox": ("reporter_appomattox", "tts_rep_appomattox", "a correspondent in a dark frock coat speaking calmly to the camera in front of a brick farmhouse, subtle natural head movement"),
 "itk_follow": ("reporter_appomattox", "tts_follow", "a correspondent in a dark frock coat speaking to the camera, subtle natural head movement"),
 "itk_follow_myth": ("reporter_appomattox", "tts_follow_myth", "a correspondent in a dark frock coat speaking to the camera, subtle natural head movement"),
}
jobs = {k: ("itk", rp.submit("itk", {"prompt": p, "image": U(i), "audio": AU(a), "resolution": "480p", "enable_safety_checker": True})) for k, (i, a, p) in ITK.items()}
json.dump({k: list(v) for k, v in jobs.items()}, open("shorts/rp/e3b2_itk_jobs.json", "w"), indent=1); print("itk submitted", len(jobs), flush=True)
pid = ltx.submit("shorts/assets/usct.png", "A dignified African American soldier of the United States Colored Troops in a blue frock coat and kepi stands in a spring army camp, tents and fellow soldiers behind him. He looks into the camera and says firmly: “They said we could not fight. We fought. Now let them say we are not free.” Wind in the trees, distant camp voices, a bugle far away. Static camera with a very slow push-in.", w=1280, h=720, secs=10, tag="e3_usct")
print("ltx submitted usct", flush=True)
res = rp.wait(jobs, every=10, limit=3000); json.dump(res, open("shorts/rp/e3b2_itk_out.json", "w"), indent=1)
for k, v in res.items():
    if "error" in v: print("itk FAIL", k, v["error"], flush=True); continue
    url = v.get("video_url") or v.get("video") or next((x for x in v.values() if isinstance(x, str) and x.startswith("http")), None)
    try: open(f"shorts/assets/{k}.mp4", "wb").write(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0"}), timeout=180).read()); print("itk done", k, flush=True)
    except Exception as e: print("itk dl FAIL", k, str(e)[:100], flush=True)
try: ltx.wait(pid, every=10); ltx.fetch(pid, "shorts/assets/ltx_usct.mp4"); print("ltx done usct", flush=True)
except Exception as e: print("ltx FAIL usct", str(e)[:200], flush=True)
print("ALLDONE", flush=True)
