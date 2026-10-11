"""YouTube metadata and credits from meta.json (written by the LLM) plus facts computed here: chapter times from the
timeline, credits from the archive records, verify lists from the scripts.
python3 -m docgen metadata meta.json
meta.json:
{ "long": {"title", "alternatives": [], "tags": "a, b", "pinned_comment", "thumbnail_text", "hashtags": "#A #B",
           "description": "paragraphs; may contain {chapters}", "disclosure": "what is AI-generated",
           "chapters": {"1": "Title for the chapter starting at scene 1", "4": "..."}},
  "shorts": {"a_spark": {"day": 1, "title", "alternatives": [], "cover_text", "tags", "pinned_comment", "description", "hashtags"}} }
Writes out/youtube_metadata.md, out/youtube_metadata_shorts.md, out/youtube_metadata.json, out/credits.md."""
import json, os, sys
from .common import ASSETS, load_script, mkdirs
def ts(x): x = int(x); return f"{x // 60:02d}:{x % 60:02d}"
def main(cmd, argv):
    if not argv: sys.exit(__doc__)
    M = json.load(open(argv[0])); mkdirs("out"); script = load_script(); sc = {s["n"]: s for s in script["scenes"]}
    tl = {e["scene"]: e for e in json.load(open("build/timeline.json"))}
    PA = json.load(open("build/period_assets.json")) if os.path.exists("build/period_assets.json") else {}
    warn = []; L = M["long"]
    # chapters: YouTube needs the first at 00:00, at least three, each at least 10 seconds
    ch = sorted(((tl[int(n)]["start"], t) for n, t in L.get("chapters", {}).items() if int(n) in tl))
    keep = []
    for st, t in ch:
        if keep and st - keep[-1][0] < 10: warn.append(f"chapter '{t}' dropped: under 10 s after the previous one"); continue
        keep.append((st, t))
    if keep and keep[0][0] != 0: keep[0] = (0, keep[0][1])
    if len(keep) < 3: warn.append("fewer than 3 chapters: YouTube will not show them")
    chapters = "\n".join(f"{ts(st)} {t}" for st, t in keep)
    desc = L["description"].replace("{chapters}", "Chapters:\n" + chapters)
    if "{chapters}" not in L["description"]: desc += "\n\nChapters:\n" + chapters
    used = [e["asset"] for e in tl.values()]
    PA = {k: v for k, v in PA.items() if any(e["asset"] == k and e["src"] == v["path"] for e in tl.values())}   # credit only archive files actually on screen
    att = [f"{PA[a]['commons_title'][5:]} by {PA[a].get('artist') or 'unknown'}, {PA[a]['license']}" for a in dict.fromkeys(used) if a in PA and PA[a].get("needs_attribution", "BY" in PA[a]["license"])]
    if att: desc += "\n\nAttribution (Wikimedia Commons): " + "; ".join(att) + "."
    desc += "\n\n" + L.get("disclosure", "Narration and music in this video are AI-generated.") + "\n\n" + L.get("hashtags", "")
    ver = [(n, s["asset"], s["verify_note"]) for n, s in sc.items() if s.get("verify")]
    for ph in ("[PLAYLIST URL]", "[EPISODE"):
        if ph in desc: warn.append(f"placeholder {ph}...] still in the description")
    md = (f"# {L['title']}\n\n**Alternatives:** {'; '.join(L.get('alternatives', []))}\n\n**Category:** Education | **Made for kids:** no | **Altered/synthetic content:** yes"
          f" | **Thumbnail:** `thumb/thumbnail.jpg` ({L.get('thumbnail_text', '')})\n\n**Tags:** {L.get('tags', '')}\n\n**Pinned comment:** {L.get('pinned_comment', '')}\n\n## Description\n\n{desc}\n\n"
          f"## Before publishing: fact-check the `verify` scenes ({len(ver)})\n\n" + "\n".join(f"- Scene {n} ({a}): {v}" for n, a, v in ver) + "\n")
    open("out/youtube_metadata.md", "w").write(md)
    # credits
    lines = ["# Image credits (Wikimedia Commons)\n"] + [f"- {PA[a]['commons_title'][5:]} ({a}) — {PA[a]['license']} — {PA[a]['source']}" for a in sorted(set(used)) if a in PA]
    if att: lines.append("\nAttribution required: " + "; ".join(att))
    lines.append("\nAI-generated images: " + (", ".join(sorted(a for a in set(used) if a not in PA and os.path.exists(f"{ASSETS}/{a}.png"))) or "none"))
    lines.append("AI-animated clips: " + (", ".join(sorted(e["asset"] for e in tl.values() if e["kind"] == "animated")) or "none"))
    lines.append("AI talking characters: " + (", ".join(sorted(e["asset"] for e in tl.values() if e["kind"] in ("talking", "character"))) or "none"))
    open("out/credits.md", "w").write("\n".join(lines) + "\n")
    # shorts
    out = {"long": dict(L, description=desc, chapters=[{"start": st, "title": t} for st, t in keep], verify=[v for _, _, v in ver])}; smd = ["# YouTube metadata: Shorts (9:16)\n\nCommon: **Category** Education | **Made for kids** no | **Altered/synthetic content** yes | publish one per day after the long video.\n"]
    for sid, v in sorted(M.get("shorts", {}).items(), key=lambda kv: kv[1].get("day", 0)):
        s_ = json.load(open(f"shorts/{sid}/script.json")); imgs = list(dict.fromkeys(x["image"] for x in s_["segments"]))
        cred = [f"- {PA[a]['commons_title'][5:]} — {PA[a]['license']}" + (f" — by {PA[a]['artist']}" if PA[a].get("needs_attribution") and PA[a].get("artist") else "") for a in imgs if a in PA]
        vv = s_.get("verify", [])
        smd.append(f"## Day {v.get('day', '?')}: {s_.get('title', sid)}\n\n**Title:** {v['title']}\n\n**Alternatives:** {'; '.join(v.get('alternatives', []))}\n\n**Cover text:** {v.get('cover_text', '')}\n\n"
                   f"**Tags:** {v.get('tags', '')}\n\n**Hashtags:** {v.get('hashtags', '')}\n\n**Pinned comment:** {v.get('pinned_comment', '')}\n\n### Description\n\n{v.get('description', '')}\n\n{v.get('hashtags', '')}\n\n"
                   "### Credits (Wikimedia Commons)\n\n" + "\n".join(cred) + f"\n\nAI-generated images: {', '.join(a for a in imgs if a not in PA) or 'none'}\n\n**Verify before publishing:**\n" + "\n".join(f"- {x}" for x in vv) + "\n")
        if len(v["title"]) > 60: warn.append(f"short {sid}: title over 60 characters")
        out[sid] = dict(v, credits=cred, verify=vv, video=f"shorts/{sid}/out/{sid}.mp4")
    if M.get("shorts"): open("out/youtube_metadata_shorts.md", "w").write("\n".join(smd))
    out["warnings"] = warn; json.dump(out, open("out/youtube_metadata.json", "w"), indent=1, ensure_ascii=False)
    print(json.dumps({"chapters": len(keep), "verify": len(ver), "warnings": warn}))
