import json, sys; sys.path.insert(0, "build")
import rp
P = "Cinematic realistic portrait photograph with muted painterly colour grading, authentic early 19th-century costume (1805-1815), period accurate, "
H = "Oil painting in the style of early 19th-century French history painting, dramatic lighting, authentic 1805-1815 uniforms and clothing, no modern objects, "
G = {  # 9:16 portraits / shorts
 "rep_austerlitz": (P + "head and shoulders of a middle-aged gentleman war correspondent with side-whiskers in a dark greatcoat and high collar, standing on a frozen snowy hilltop at dawn with mist and distant army campfires behind him, facing the camera, mouth slightly open as if speaking", "9:16"),
 "historian": (P + "head and shoulders of a grey-haired scholar-lawyer with spectacles in a dark coat and white cravat, seated in a candlelit study with leather law books, holding a thick bound book, facing the camera, mouth slightly open as if speaking", "9:16"),
 "rep_vienna": (P + "head and shoulders of the same style of gentleman correspondent with side-whiskers in a dark coat and cravat, standing in a grand ballroom of a Vienna palace with chandeliers and diplomats behind, facing the camera, mouth slightly open as if speaking", "9:16"),
 "coronation_q": (H + "Napoleon in imperial robes lifting a golden laurel crown above his own head before the altar of Notre-Dame, cardinals and the Pope watching, vertical composition", "9:16"),
 # 16:9 long-form scenes
 "soldier": (P + "weary French grenadier of the Imperial Guard in a tall bearskin cap and dark greatcoat, frost on his moustache, standing in a snowy road in the Russian winter, ragged soldiers behind him, facing the camera, medium shot", "16:9"),
 "dissolution": (H + "a stern Austrian emperor's court in 1806, courtiers in uniforms, a big imperial crown on a cushion being carried away, Vienna palace hall", "16:9"),
 "guerrilla": (H + "Spanish guerrilla fighters in brown cloaks and broad hats ambushing a French column in a rocky mountain pass, smoke and musket fire, in the manner of Goya", "16:9"),
 "retreat": (H + "French soldiers in tattered greatcoats trudging through deep snow, bodies and abandoned cannon, grey winter sky, 1812 retreat from Moscow", "16:9"),
 "continental": (H + "smugglers loading crates into small boats at night in a harbour, British warships in the distance, lanterns, 1807", "16:9"),
 "life": (H + "a village square in 1810 where young conscripts in civilian clothes line up before a recruiting officer in a blue uniform, mothers weeping, townspeople watching", "16:9"),
 "concert": (H + "diplomats in frock coats and uniforms around a long table with maps in a candlelit palace room, Vienna 1815", "16:9"),
 "restoration": (H + "restored old monarchs in ornate robes, a king being crowned in a grand cathedral with nobles bowing, 1815", "16:9"),
 "nationalism": (H + "a crowd of students and workers waving flags on a street barricade during the 1848 revolutions in a European city, dramatic light", "16:9"),
 "napoleon_young": (H + "portrait of the young General Bonaparte, 1796, slim, long dark hair, blue general's coat with gold embroidery, on a battlefield at dusk", "16:9"),
 "map1812": (H + "an antique hand-coloured map of Europe in 1812 showing the French Empire in blue, aged parchment, no readable text", "16:9"),
 "brumaire": (H + "soldiers with bayonets entering a legislative chamber at Saint-Cloud, deputies in red robes fleeing, 1799", "16:9"),
}
jobs = {}
for k, (p, a) in G.items():
    jobs[k] = ("qwen", rp.submit("qwen", {"model": "qwen", "prompt": p, "aspect_ratio": a, "project_id": "wars_e2", "frame_id": k}))
BG = {"bgm_long": "epic Napoleonic era orchestral underscore, marching snare drums, rising strings and brass, dramatic and reflective, historical documentary, no vocals, steady energy so a narrator's voice sits on top",
      "bgm_a": "grand ceremonial orchestral fanfare building slowly, French horns and timpani, regal and tense, historical documentary, no vocals",
      "bgm_b": "playful curious pizzicato strings and light percussion, mystery documentary underscore, no vocals",
      "bgm_c": "reflective elegiac orchestral, solemn piano and cello, slow, haunting, historical documentary, no vocals"}
for k, p in BG.items():
    jobs[k] = ("bgm", rp.submit("bgm", {"mode": "bgm", "prompt": p, "duration_s": 120 if k == "bgm_long" else 50, "steps": 20, "guidance": 7.0, "project_id": "wars_e2", "frame_id": k}))
T = {
 "tts_rep_austerlitz": ("bm_george", "b", [s["narration"] for s in json.load(open("script/script.json"))["scenes"] if s["asset"] == "reporter_austerlitz"][0]),
 "tts_historian": ("bm_lewis", "b", [s["narration"] for s in json.load(open("script/script.json"))["scenes"] if s["asset"] == "historian_code"][0]),
 "tts_rep_vienna": ("bm_george", "b", [s["narration"] for s in json.load(open("script/script.json"))["scenes"] if s["asset"] == "reporter_vienna"][0]),
 "tts_follow": ("bm_george", "b", "Follow for the full story."),
 "tts_follow_myth": ("bm_george", "b", "Follow for more history myths."),
}
for k, (v, l, t) in T.items():
    jobs[k] = ("flux", rp.submit("flux", {"mode": "tts", "engine": "kokoro", "text": t, "voice": v, "speed": 0.95, "lang_code": l, "project_id": "wars_e2", "frame_id": k}))
json.dump({k: list(v) for k, v in jobs.items()}, open("shorts/rp/e2b1_jobs.json", "w"), indent=1); print("submitted", len(jobs), flush=True)
res = rp.wait(jobs); json.dump(res, open("shorts/rp/e2b1_out.json", "w"), indent=1)
for k, v in res.items(): print(k, "ERROR " + v["error"] if "error" in v else "ok", flush=True)
