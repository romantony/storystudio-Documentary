import json, sys; sys.path.insert(0, "build")
import ltx
L = [
 ("sumter", "Historic lithograph comes to life: cannon fire flashes over the water, smoke billows from the fort, waves roll. Distant cannon thunder, crackling fire, lapping waves. Slow camera push-in."),
 ("industrial", "Historic photograph comes to life subtly: steam rises from the locomotive, grass sways in the breeze. Hissing steam, a distant whistle, birds. Slow camera push-in."),
 ("gettysburg", "Historic photograph comes to life subtly: clouds drift and grass moves in the wind over the battlefield. Wind, distant faint cannon, crows. Slow camera push-in."),
 ("atlanta", "Historic photograph comes to life subtly: smoke drifts over the ruined railway depot, steam and dust blow. Wind, creaking timbers, distant shouting. Slow camera push-in."),
 ("richmond", "Historic photograph comes to life subtly: water ripples in the canal, smoke rises from the ruins. Water lapping, wind, distant church bell. Slow camera push-in."),
 ("grant", "Historic photograph comes to life subtly: the tent canvas flaps, a general stands with a cigar and looks to the side, leaves rustle. Camp ambience, wind, distant bugle. Slow camera push-in."),
 ("address", "Historic photograph comes to life subtly: the crowd shifts, flags stir, hats move. Murmuring crowd, wind, a distant band. Slow camera push-in."),
 ("monitor", "Historic print comes to life: two ironclad ships exchange cannon fire at sea, smoke drifts, waves roll. Booming cannons, waves, metallic clangs. Slow camera push-in."),
 ("march", "Historic photograph comes to life subtly: Union soldiers bend railroad rails over a fire, smoke rises. Hammering, crackling fire, distant voices. Slow camera push-in."),
 ("ford", "Historic photograph comes to life subtly: townspeople stand in the street outside a brick theatre, flags flutter at half mast. Muffled bells, crowd murmur, wind. Slow camera push-in."),
 ("inaug", "Historic photograph comes to life subtly: a large crowd gathers before the unfinished Capitol, hats and flags move in the wind. Crowd murmur, wind, distant band. Slow camera push-in."),
]
lj = {n: ltx.submit(f"images_period/{n}.jpg", p, secs=5, tag=f"e3_{n}") for n, p in L}
json.dump(lj, open("shorts/rp/e3_ltx1_jobs.json", "w"), indent=1); print("submitted", len(lj), flush=True)
for n, pid in lj.items():
    try: ltx.wait(pid, every=10); ltx.fetch(pid, f"shorts/assets/ltx_{n}.mp4"); print("done", n, flush=True)
    except Exception as e: print("FAIL", n, str(e)[:200], flush=True)
print("ALLDONE", flush=True)
