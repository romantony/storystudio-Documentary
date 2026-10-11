# Plan: 1 long-form + 3 Shorts (9:16) per topic

Applies from **episode 2** ("The Napoleonic Wars") onward. Episode 1 (WWI) is not back-filled unless you ask.

## Package per topic
| Item | Format | Length | Words (at ~2.5 wps) | Role |
|---|---|---|---|---|
| Long-form | 16:9, 1920x1080 | 8-10 min | ~1,300 | The full story (same pipeline as episode 1) |
| Short A: "The Spark" | 9:16, 1080x1920 | 40-55 s | 100-135 | The single most dramatic moment, told as a hook |
| Short B: "Myth vs Reality" | 9:16 | 40-55 s | 100-135 | One common misconception corrected |
| Short C: "Why It Still Matters" | 9:16 | 40-55 s | 100-135 | A line from the war to today |

**Each piece has its own script, written from scratch for its length.** Shorts are not cut-downs of the long script: a Short opens with the payoff in the first 2 seconds, has one idea, and ends with a loop-back line or a pointer to the long video.

**Shared vs separate**
- *Shared:* the research notes and facts list (one fact-checked source of truth per topic), the voice (Charon), the archival image/footage pool (credits file), the music style.
- *Separate per piece:* script, TTS audio, Whisper word timings, image selection and order, captions, music cut, metadata, thumbnail/cover.
- A given image may appear in the long-form and a Short, but each is edited, cropped and animated separately for its own aspect ratio.

## What changes for 9:16 (vs the 16:9 pipeline)
- **Output** 1080x1920 at 30 fps; same encoder settings.
- **Images:** archival photos are mostly landscape. Choose Short images for a portrait crop around the subject (crop to the subject, don't centre-crop blindly), or use a blurred-fill with the photo in the upper two-thirds. Check one frame per scene.
- **Motion:** Ken Burns zoom of 1.0 to 1.12 on a tighter crop; a new image every 3-5 seconds (the long-form holds 20 s).
- **Captions:** centred, larger (about 110 px), at most 3 words on screen at a time, current word highlighted (same colour as the long-form for brand consistency). Keep captions inside the safe zone: away from the top 12% and bottom 22% where the app UI sits.
- **Audio:** narration first; music lower than in the long-form (about 0.25 volume); loudnorm to about -14 LUFS; same limiter ceiling.
- **Call to action:** one line only ("follow for the full story"), no emoji card mid-video; show the like/subscribe/share emoji card for the last 2 seconds.
- **Cover frame:** a 9:16 still with the hook text (Shorts use a chosen frame, not a separate thumbnail).

## Script schema (single file per topic)
`script/<topic>.json` with four entries: `{id, format: "long"|"short", aspect, title, scenes:[{n, narration, image_query, verify}]}`. The existing `gen_assemble.py` gets an `--aspect` parameter and per-format caption style; scene-level `verify` flags and the plain-text-only TTS rule carry over.

## Folder layout
```
doc_run/<topic>/
  research/facts.md          # shared, fact-checked
  assets/                    # shared image pool + credits.md
  long/                      # script, audio, build, out
  short_a_spark/  short_b_myth/  short_c_matters/   # same structure each
```

## Workflow per topic (about one working day once set up)
1. Research + `facts.md`, mark claims needing verification.
2. Gather the image pool (Commons / LoC / NARA; paintings and engravings for pre-photo eras). Tag each image with the pieces it suits.
3. Write the 4 scripts; fact-check against `facts.md`.
4. TTS per script (plain text, no style prefix). Transcribe a sample to check.
5. Whisper (Replicate) word timings per script.
6. Assemble long-form, then the three Shorts (9:16).
7. QA each: duration, peak level, contact sheet, caption safe zone. **Listen before publishing.**
8. Metadata per piece; Shorts link to the long-form in the description and pinned comment, and the long-form description lists the Shorts.

## Publishing plan
- Day 0: long-form. Day 1, 2, 3: Short A, B, C (each pointing to the long video).
- Playlist: "Wars That Shaped the World"; Shorts get the same series tag and `#shorts`.

## Example, episode 2 (Napoleonic Wars), angles to confirm
- Short A: the moment Napoleon crowns himself emperor.
- Short B: "Napoleon was short": the myth and where it came from.
- Short C: the legal code and borders that outlived him.
All claims here need fact-checking before scripting.

## Open decisions
1. Back-fill three Shorts for episode 1 (WWI)? (Reuses the existing facts and images.)
2. Voice for Shorts: same Charon voice (recommended for brand), or a second voice?
3. Automate the Shorts step in the RunPod shorts worker plan (`~/longtoshort/`) or keep it local? (See the "Shorts RunPod worker plan" memory.)
