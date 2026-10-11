import json, sys, threading, urllib.request; sys.path.insert(0, "build")
import rp, ltx
o = json.load(open("shorts/rp/e2b1_out.json")); U = lambda k: o[k]["image_url"]; AU = lambda k: o[k]["audio"]
S = json.load(open("script/script.json"))["scenes"]
# --- InfiniteTalk (RunPod)
ITK = {
 "itk_austerlitz": ("rep_austerlitz", "tts_rep_austerlitz", "a war correspondent in a dark greatcoat speaking calmly to the camera on a frozen hill at dawn, subtle natural head movement, smoke rising from distant campfires"),
 "itk_historian": ("historian", "tts_historian", "a scholarly lawyer with spectacles speaking thoughtfully to the camera in a candlelit study, subtle head movement and hand holding a book"),
 "itk_vienna": ("rep_vienna", "tts_rep_vienna", "a correspondent in a dark coat speaking calmly to the camera in a grand ballroom, subtle natural head movement"),
 "itk_follow": ("rep_vienna", "tts_follow", "a correspondent in a dark coat speaking to the camera, subtle natural head movement"),
 "itk_follow_myth": ("rep_vienna", "tts_follow_myth", "a correspondent in a dark coat speaking to the camera, subtle natural head movement"),
}
jobs = {k: ("itk", rp.submit("itk", {"prompt": p, "image": U(i), "audio": AU(a), "resolution": "480p", "enable_safety_checker": True})) for k, (i, a, p) in ITK.items()}
json.dump({k: list(v) for k, v in jobs.items()}, open("shorts/rp/e2b2_itk_jobs.json", "w"), indent=1); print("itk submitted", len(jobs), flush=True)
# --- LTX (ComfyUI cloud): (name, source image, w, h, secs, prompt)
IMG = lambda k: f"images_period/{k}.jpg" if __import__("os").path.exists(f"images_period/{k}.jpg") else f"shorts/assets/{k}.png"
L = [
 ("soldier", "shorts/assets/soldier.png", 1280, 720, 10, "A weary French grenadier of the Imperial Guard in a bearskin cap, frost on his moustache, stands on a snowy road, ragged soldiers trudging behind him. He looks into the camera and says slowly, in a tired voice: “We marched in with songs. We walked out without boots. The cold did not care who was emperor.” Wind howls, snow blows, boots crunch in snow. Static camera with a very slow push-in."),
 ("trafalgar", IMG("trafalgar"), 1280, 720, 5, "Painting comes to life: warships fire broadsides in a storm, smoke drifts over rolling sea, masts sway. Cannon thunder, creaking timbers and crashing waves. Slow camera push-in."),
 ("moscow", IMG("moscow"), 1280, 720, 5, "Painting comes to life: the Kremlin burns, flames flicker and smoke rolls into the dark sky, tiny figures move. Roaring fire, crackling timbers and distant shouting. Slow camera push-in."),
 ("hundred_days", IMG("hundred_days"), 1280, 720, 5, "Painting comes to life: sailing ships glide on a calm sea at dawn, sails ripple in the wind. Gentle waves, wind in the rigging, gulls. Slow camera push-in."),
 ("coronation", IMG("coronation"), 1280, 720, 5, "Painting comes to life: crowds in the cathedral stir, candles flicker, robes shift. Echoing cathedral ambience, choir humming softly. Slow camera push-in."),
 ("austerlitz", IMG("austerlitz"), 1280, 720, 5, "Painting comes to life: cavalry gallops across the field, smoke drifts, flags wave. Hoofbeats, distant cannon fire and shouts. Slow camera push-in."),
 ("waterloo", IMG("waterloo"), 1280, 720, 5, "Painting comes to life: infantry volleys and cannon smoke roll across the ridge, soldiers move. Muskets crackle, cannon boom, distant drums. Slow camera push-in."),
 ("retreat", IMG("retreat"), 1280, 720, 5, "Soldiers trudge through deep snow in the retreat from Moscow, breath steaming, snow blowing in a bitter wind. Howling wind, crunching snow, a distant crow. Slow camera push-in."),
 ("borodino", IMG("borodino"), 1280, 720, 5, "Painting comes to life: artillery smoke rolls across the hills, columns advance. Heavy cannon fire, drums and shouting. Slow camera push-in."),
 ("coronation_q", "shorts/assets/coronation_q.png", 720, 1280, 5, "Painting comes to life: Napoleon holds the golden crown above his head and slowly lowers it onto his hair, courtiers and clergy watch, candles flicker. Cathedral echo, soft choir. Slow camera push-in."),
]
lj = {}
for n, src, w, h, s, p in L:
    lj[n] = ltx.submit(src, p, w=w, h=h, secs=s, tag=f"e2_{n}"); print("ltx submitted", n, flush=True)
json.dump(lj, open("shorts/rp/e2b2_ltx_jobs.json", "w"), indent=1)
def ltxrun():
    for n, pid in lj.items():
        try: ltx.wait(pid, every=10); ltx.fetch(pid, f"shorts/assets/ltx_{n}.mp4"); print("ltx done", n, flush=True)
        except Exception as e: print("ltx FAIL", n, str(e)[:200], flush=True)
t = threading.Thread(target=ltxrun); t.start()
res = rp.wait(jobs, every=10, limit=3000); json.dump(res, open("shorts/rp/e2b2_itk_out.json", "w"), indent=1)
for k, v in res.items():
    if "error" in v: print("itk FAIL", k, v["error"], flush=True); continue
    url = v.get("video_url") or v.get("video") or next((x for x in v.values() if isinstance(x, str) and x.startswith("http")), None)
    try: open(f"shorts/assets/{k}.mp4", "wb").write(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0"}), timeout=180).read()); print("itk done", k, flush=True)
    except Exception as e: print("itk dl FAIL", k, str(e)[:100], list(v.keys()), flush=True)
t.join(); print("ALLDONE", flush=True)
