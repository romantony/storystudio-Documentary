import json, sys; sys.path.insert(0, "build")
import rp
ST = "Authentic black-and-white archival photograph from 1914, film grain, soft vintage lens, period accurate, vertical composition, "
Q = {
 "q_car": "an open-top touring automobile stopped in a narrow Sarajevo street, the driver looking back to reverse, onlookers on the pavement",
 "q_stride": "a young man in a dark 1914 suit and cap stepping out of a crowd toward a stopped car, seen from behind, tense moment, no face visible",
 "q_ultimatum": "close-up of a formal diplomatic document with a wax seal and a fountain pen on a mahogany desk, Vienna, candlelight",
 "q_council": "Austro-Hungarian officials in uniform gathered around a table with a map, grave expressions, Vienna",
 "q_map": "antique hand-coloured map of Central Europe and the Balkans with new borders drawn in red ink, aged paper, no readable text, vertical",
 "q_reporter": "head and shoulders portrait of a middle-aged newspaper war correspondent with a moustache, bowler hat and long coat, standing in a Sarajevo street, facing the camera, mouth slightly open as if speaking",
}
jobs = {}
for k, p in Q.items():
    jobs[k] = ("qwen", rp.submit("qwen", {"model": "qwen", "prompt": ST + p, "aspect_ratio": "9:16", "project_id": "wwi_shorts", "frame_id": k}))
BG = {"bgm_a": "dark cinematic orchestral, tense low strings, slow pulsing drone, dramatic build, historical documentary, no vocals",
      "bgm_b": "investigative documentary underscore, ticking clock percussion, restrained strings, rising tension, no vocals",
      "bgm_c": "reflective elegiac orchestral, solemn piano and cello, slow, haunting, historical documentary, no vocals"}
for k, p in BG.items():
    jobs[k] = ("bgm", rp.submit("bgm", {"mode": "bgm", "prompt": p, "duration_s": 50, "steps": 20, "guidance": 7.0, "project_id": "wwi_shorts", "frame_id": k}))
jobs["rep_tts"] = ("flux", rp.submit("flux", {"mode": "tts", "engine": "kokoro", "text": "I'm in Sarajevo. It is June twenty-eighth, nineteen fourteen. Watch what happens next.", "voice": "bm_george", "speed": 0.95, "lang_code": "b", "project_id": "wwi_shorts", "frame_id": "rep"}))
json.dump({k: list(v) for k, v in jobs.items()}, open("shorts/rp/batch1_jobs.json", "w"), indent=1)
print("submitted", len(jobs)); res = rp.wait(jobs)
json.dump(res, open("shorts/rp/batch1_out.json", "w"), indent=1)
for k, v in res.items(): print(k, "ERROR " + v["error"] if "error" in v else "ok")
