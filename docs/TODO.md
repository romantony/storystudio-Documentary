# TODO — WWI documentary ("How One Assassination Started World War I")

Run folder: `doc_run/how-one-assassination-started-world-war-i/`. Final video: `out/how-one-assassination-started-world-war-i.mp4` (9:20).

## Tomorrow
0. **Back-fill 3 WWI Shorts (9:16)** — approved. Per `SHORTS_PLAN.md`: Short A "The Spark" (the Sarajevo shooting), Short B "Myth vs Reality" (one WWI-origins misconception, fact-checked), Short C "Why It Still Matters" (alliances/empires collapse legacy). Each: own script (100-135 words), own TTS (plain text), Whisper timings, 9:16 image crops from `images_period/`, centred 3-word captions, end emoji card, metadata linking to the long video. Needs a `--aspect` option in `build/gen_assemble.py` first. Voice and local-vs-RunPod are still open (default: Charon, local).
1. **Watch the full video with sound.** Claude could not hear it. Check: voice/caption sync, music ducking under the voice, the 3-minute music loop repeating, volume.
2. **Fact-check the 13 `verify` scenes** (3, 9, 10, 11, 13, 14, 15, 17, 18, 19, 20, 23, 24) in `script/script.json` against `verify_note` before publishing.
3. **Confirm episode 2.** The end card promises "The Napoleonic Wars" next. Change it (script scene 26, `build/make_cards.py`, metadata) and re-render if you want something else.
4. **Review weak visuals:** scene 2 (theatre facade, not a street), scene 6 (reddish Balkan War scan), scene 11 (arrest photo is widely misattributed to Princip), the thumbnail text overlapping a third person at the right edge.
5. **Decide on period video.** None found. If you have WWI footage (or want Claude to try NARA / IWM film), add it for scenes that show moving subjects.
6. **Mid-roll chapter:** drop or rename "Wars That Shaped the World (series note)" in the description if you don't want it as a chapter.
7. **Upload prep:** paste `out/youtube_metadata.md`, add image credits from `out/credits.md`, upload `thumb/thumbnail.jpg`, set "altered or synthetic content" = yes.

## Housekeeping
- API keys (Gemini, Replicate) are on lines 1–2 of `~/storystudio-unified/docs/documentary/CLAUDE_SESSION_STOCK_DOCUMENTARY_PROMPTS.md` as an **uncommitted local edit** (the committed version has no keys, nothing pushed). Do not `git add`/commit that file with those lines; rotate the keys if it is ever committed or shared.
- Delete `audio_old/`, `build/words_old/` and `thumb/thumbnail_ai_v1.jpg` if not needed.
- Check the Storyblocks download licences for the 3 clips used (chess 355075065, clock 352152708, fire 347323273).

## Shorts + long-form packages (new)
- Open questions left in `SHORTS_PLAN.md`: voice for Shorts (default Charon) and local vs RunPod worker (default local). WWI back-fill is decided: yes, tomorrow.
- When starting episode 2: set up the per-topic folder layout, add `--aspect` to `build/gen_assemble.py`, write 4 scripts (1 long + 3 shorts).

## Series ("Wars That Shaped the World")
- Start episode 2 from `out/series_plan.md`. Reuse `build/gen_assemble.py`, `build/whisper_replicate.py`, `build/make_cards.py`, `thumb/make_thumb_real.py`.
- Reminder: send TTS plain text only (no style prefix).

## Episode 2: "The Man Who Redrew Europe" (built 2026-10-11, folder `doc_run/the-man-who-redrew-europe/`)
- Built: long video (8:01), 3 Shorts, metadata (`out/youtube_metadata*.md/json`), credits, thumbnail. **Nobody has listened to any audio yet.**
- Before upload: fact-check `verify` scenes in `script/script.json` and `shorts/*/script.json`; listen to the ACE-Step loop seam, the InfiniteTalk lip-sync and the LTX ambience; replace `[PLAYLIST URL]` and `[EPISODE 2 URL]`.
- Grenadier (scene 18) is an invented, dramatised AI character; description says so.
- Rebuild: `python3 build/gen_assemble.py && bash build/assemble.sh` (long); `python3 build/gen_short.py <id> build && bash shorts/<id>/build/assemble.sh` (Shorts).

## Episode 3: "The War That Ended Slavery" (built 2026-10-11, folder `doc_run/the-american-civil-war/`)
- Built: long (7:40), 3 Shorts, metadata, credits, thumbnail. **No audio listened to yet.**
- Before upload: fact-check `verify` scenes (script + shorts); replace plantation image (scene 3, weak); decide on graphic photos (scenes 12, 27); fill `[PLAYLIST URL]`, `[EPISODE 2 URL]`, `[EPISODE 3 URL]`. Soldier (scene 16) is a dramatised AI character.
- Next: Episode 4 "Why the Peace Failed" (WWII) per `out/series_plan.md`.
