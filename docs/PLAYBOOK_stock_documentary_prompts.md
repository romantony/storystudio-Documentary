<!-- API keys removed. Keys belong in environment variables (see .env.example), never in this file. -->

# Claude Session Playbook: Stock-Media Documentary (Storyblocks MCP + Google AI Studio + local ffmpeg)

**Purpose:** a repeatable set of prompts to paste into a Claude Code session to produce a short
documentary video end to end, locally, with no StoryStudio pipeline.
**Proven in:** the 2026-10-10 microscope test (5 Storyblocks clips + Kokoro TTS + burned captions).
This playbook generalises it and swaps in Google AI Studio for TTS, BGM and thumbnails.

**Inputs you give the session** (the only four things):

| Input | Example |
|---|---|
| `TOPIC` | How microscopes changed science |
| `SYNOPSIS` | 2–3 sentences of angle, audience and tone |
| `ASPECT_RATIO` | `16:9`, `9:16` or `1:1` |
| `DURATION` | target seconds, e.g. `60` |

**Tools the session needs**
- Storyblocks MCP, already added: `claude mcp get storyblocks` -> `https://mcp.storyblocks.com/mcp`, status Connected. Tools: `search_videos`, `search_images`, `get_stock_item_details`, `get_download_url`, `get_related_terms`, `list_categories`, `search_audio`.
- `GEMINI_API_KEY` exported in the shell (Google AI Studio key). Never print it, never write it into files.
- `ffmpeg` with `silenceremove`, `subtitles`/`ass`, `amix`, `sidechaincompress` (verified on this machine), `ffprobe`, `python3`.

> **Licensing rule.** `get_download_url` licenses the item and records a download on the account
> every time it is called, repeat calls included. Search and preview freely. Download **only** the
> clips and images you have decided to use, **once each**, and cache them.

---

## 0. Working folder and conventions

Paste once at the start of the session:

```text
You are producing a documentary video. Work only inside ./doc_run/<slug>/ where <slug> is a
kebab-case form of TOPIC. Create subfolders: script/ audio/ clips/ images/ thumb/ bgm/ build/ out/.

INPUTS
TOPIC: <topic>
SYNOPSIS: <synopsis>
ASPECT_RATIO: <16:9 | 9:16 | 1:1>
DURATION: <seconds>

DERIVED VALUES (compute and print them first, then wait for my "go"):
- Storyblocks orientation: 16:9 -> horizontal, 9:16 -> vertical, 1:1 -> horizontal (crop to square later).
- Output size: 16:9 = 1920x1080, 9:16 = 1080x1920, 1:1 = 1080x1080. fps 30.
- Narration word budget = DURATION * 2.4 words/second (Gemini TTS pace; recheck against real audio).
- Scene count = round(DURATION / 6), clamped to 4..24. Each scene is about 5-8 seconds.

RULES
- Never print or store GEMINI_API_KEY. Read it from the environment.
- Download a Storyblocks item (get_download_url) only after I approve the shortlist, once per item.
- Exclude editorial footage (is_editorial=false). Prefer released talent/property.
- After every stage, write a one-line status to build/log.md and show me the output file paths.
- If a step fails, stop and tell me; do not silently substitute a different provider.
```

---

## 1. Script and scene plan

```text
STAGE 1 - SCRIPT. Using TOPIC, SYNOPSIS and the word budget, write script/script.json:

{
  "title": "...",
  "scenes": [
    {
      "n": 1,
      "narration": "one to three sentences, plain text, no stage directions",
      "visual": "what the viewer sees, concrete and filmable",
      "video_query": { "required_keyword": "<ONE singular subject noun>", "keywords": "<3-5 words>" },
      "image_query": { "required_keyword": "<noun>", "keywords": "<3-5 words>" },
      "tone": "calm | urgent | wonder | sombre"
    }
  ]
}

Rules for the script:
- Open with a hook line. End with a single reflective line, not a call to action unless SYNOPSIS asks.
- Factual claims must be ones you are confident are true. Mark anything uncertain with "verify": true.
- required_keyword must be the main subject NOUN, singular (e.g. "microscope", "ruin", "soldier"),
  never an adjective, verb or setting. Storyblocks matches the setting and misses the subject
  otherwise.
- Prefer subjects Storyblocks covers well: science, technology, business, landmarks, nature,
  generic people at work. For specific historical events or named people expect thin coverage;
  plan an abstract or symbolic visual instead of promising archival footage.
- Total narration words must be within +/-10% of the budget. Print the count.
```

---

## 2. Stock video search (no downloads yet)

```text
STAGE 2 - VIDEO SHORTLIST. For each scene in script/script.json call search_videos with:
  keywords = video_query.keywords
  required_keywords = video_query.required_keyword
  orientation = <derived orientation>
  quality = HD
  is_editorial = false
  content_type = footage
  min_duration = 6, max_duration = 25
  results_per_page = 8
Do all scenes in parallel.

From the results, pick the best 1 and a runner-up per scene. Judge by TITLE and metadata, then
state in one line WHY it fits the narration. Reject: clips with on-screen text or UI, wrong tone
for the scene, obvious stock-photo staging when the scene is serious, and any item id already
used in an earlier scene (no repeats).

Write script/shortlist_video.json: [{scene, id, title, duration, details_url, reason, runner_up_id}].
Show me a compact table. Do NOT call get_download_url yet.
```

Notes from the first run: a CGI virus clip fit "disease" but not "cells"; a phone-in-bedroom DNA clip
was a poor tonal match for a documentary. Titles alone can mislead, so ask for the `thumbnail_url`
check in the QA stage if a scene matters.

---

## 3. Stock image search (inserts, B-roll stills, thumbnail base)

```text
STAGE 3 - IMAGE SHORTLIST. For scenes where a still is better than motion (title card background,
diagrams, portraits, maps) and for the thumbnail, call search_images with the image_query,
orientation matching the output, is_editorial=false, results_per_page=8.
Pick 1 per requested scene plus 3 thumbnail candidates (strong single subject, clear negative space
for a title, high contrast). Write script/shortlist_images.json with id, title, details_url,
reason. Do not download yet.
```

---

## 4. Approval gate and downloads

```text
STAGE 4 - DOWNLOAD. I approve the shortlist (edits: <list>). For each APPROVED item only:
call get_download_url exactly once, choose the MP4 1080p URL for video (or the highest-resolution
JPG available that is not larger than needed for images), curl it into clips/ or images/, and
record id, local path, resolution, duration in build/assets.json.
The signed URLs expire in about 30 minutes and must be used exactly as returned (do not edit or
re-encode any query parameter). Verify each file with ffprobe. Report any item that failed; do not
call get_download_url a second time for the same item without asking me.
```

---

## 5. Narration (Google AI Studio Gemini TTS)

Model ids change. First ask the API which TTS models your key can use:

```text
STAGE 5 - TTS. First run a ListModels call (GET https://generativelanguage.googleapis.com/v1beta/models
with the key in the x-goog-api-key header) and report the TTS-capable model ids. This repo has used
models/gemini-2.5-flash-preview-tts and has referenced gemini-3.1-flash-tts; use the newest one that
lists generateContent and supports AUDIO output. State which you chose.

Write audio/tts.py that, for each scene, calls
POST https://generativelanguage.googleapis.com/v1beta/<model>:generateContent
body:
{
  "contents": [{"parts": [{"text": "<style instruction>: <scene narration>"}]}],
  "generationConfig": {
    "responseModalities": ["AUDIO"],
    "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "<VOICE>"}}}
  }
}
Read the key from the environment. The response carries audio as base64 in
candidates[0].content.parts[*].inlineData.data. Gemini TTS returns raw 16-bit PCM, mono, 24000 Hz,
so wrap it with ffmpeg: ffmpeg -f s16le -ar 24000 -ac 1 -i in.pcm audio/sN.wav
(check inlineData.mimeType and adapt if it says otherwise).

Use ONE voice for all scenes (suggest a calm documentary voice such as "Charon" or "Kore"; confirm
the name exists in the docs/ListModels output) and one style line for consistency, e.g.
"Read as a calm, authoritative documentary narrator, unhurried:". Generate scenes sequentially and
retry once on 429/5xx. After generation print each scene's duration with ffprobe and the measured
words/second; if the total differs from DURATION by more than 15%, tell me and propose a fix
(rewrite scenes, or adjust style pace) rather than time-stretching.
```

---

## 6. Background music (Google AI Studio Lyria)

```text
STAGE 6 - BGM. Write bgm/bgm.py that generates ONE instrumental track for the whole video.
Prompt the model (no vocals): "<mood derived from SYNOPSIS>, instrumental, no vocals, no lyrics,
slow build, underscore for a documentary narration, sparse low-mid frequencies so a voice sits on
top, steady energy, clean ending". Target length = final video length + 5 seconds.

Model discovery: the repo's own BGM code tries models/lyria-realtime-exp then models/lyria-3-pro
via generateContent with responseModalities ["AUDIO"] (see backend/convex/documentaryBgmGenerator.ts).
Run ListModels and report which Lyria model your key actually exposes before calling it. Audio is
returned as base64 in candidates[0].content.parts[*].inlineData (note its mimeType). If generation
returns shorter than needed, loop it with ffmpeg (-stream_loop) and crossfade (acrossfade d=2)
rather than failing. If NO Lyria model is available to the key, stop and tell me; do not substitute
a different vendor on your own.
Save as bgm/bgm.mp3 (or .wav) and print duration.
```

---

## 7. YouTube thumbnail (Google AI Studio image generation)

```text
STAGE 7 - THUMBNAIL. Goal: a 1280x720 (16:9) JPG under 2 MB, even if the video is 9:16.

Option A (preferred when a good stock image was shortlisted): use the approved thumbnail image as
the base, crop/scale to 1280x720 with ffmpeg, then add the title text with ffmpeg drawtext or an
ASS overlay: max 4 words, very large, heavy outline for legibility at small size, placed in the
negative space.
Option B (generated background): use a Google AI Studio image model ("Nano Banana"). Run
ListModels and pick the current image-generation model that lists generateContent with IMAGE
output (this repo's lineage: gemini-2.5-flash-image). Prompt for a TEXT-FREE background; image
models render text poorly, so overlay the title with ffmpeg afterwards. The response returns the
image as inlineData base64.

Write thumb/make_thumb.py, produce thumb/thumbnail.jpg, and verify with ffprobe (1280x720, <2MB).
Then LOOK at the file (read the image) and judge: is the subject readable at 160px wide, does the
title contrast, is anything cropped? Fix and regenerate once if not.
```

---

## 8. YouTube metadata

```text
STAGE 8 - METADATA. Write out/youtube_metadata.json and out/youtube_metadata.md:

{
  "title": "<= 70 chars, front-load the keyword, no clickbait the video can't back up",
  "title_alternatives": ["... 3 options"],
  "description": "First 2 lines carry the hook and keyword (shown before 'show more'). Then a short
                  summary, then chapters from the real scene timings (00:00 format, first at 00:00),
                  then 'Stock footage: Storyblocks' credit line, then 3 relevant hashtags.",
  "tags": ["<= 12 tags, total under 450 characters, specific before broad"],
  "category": "Education | Science & Technology | ...",
  "pinned_comment": "one question that invites replies",
  "thumbnail_text": "<= 4 words, same as on the thumbnail",
  "is_made_for_kids": false,
  "altered_or_synthetic_content": true
}

Use the REAL scene start times from build/timeline.json for the chapters. Narration and music are
AI-generated, so set altered_or_synthetic_content true and mention it in the description. Do not
invent facts beyond script/script.json; keep any scene marked "verify": true out of the title.
```

---

## 9. Assembly with local ffmpeg

Run these in order. Each step is a separate command so failures are obvious.

```text
STAGE 9 - ASSEMBLE. Build with ffmpeg only. Write the commands into build/assemble.sh so the run is
reproducible, then execute it.

9a. REMOVE SILENCE (per scene narration, before measuring durations)
  ffmpeg -i audio/sN.wav -af "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15:
       stop_periods=-1:stop_threshold=-45dB:stop_duration=0.45:stop_silence=0.18" audio/sN.clean.wav
  - This trims leading/trailing silence and shortens long internal pauses, but KEEPS about 0.18 s
    so the voice does not sound clipped. Narration only: this is a blanket cutter and is wrong for
    dialogue.
  - Re-measure every cleaned file with ffprobe and write build/timeline.json:
    [{scene, start, end, audio, clip_or_image}] where each scene lasts audio_duration + 0.35 s
    and start = sum of previous scene lengths.

9b. FIT VIDEO TO EACH SCENE (one segment per scene)
  - Video clip: -ss 0.5 -t <scene_length> from the clip; if the clip is shorter than the scene,
    loop it (-stream_loop -1) and trim; never freeze-frame.
  - Still image: zoompan Ken Burns (slow 1.0 -> 1.08 zoom, alternating pan direction) for the
    scene length.
  - Normalise all segments identically: scale to cover the output size, crop to it, fps=30,
    setsar=1, yuv420p, 0.25 s fade in/out, and mux that scene's cleaned narration as the audio
    (aresample=48000, pad 0.35 s). Aspect handling: 16:9 source into 9:16 output = scale to cover
    height then crop the centre, check subject is not cut off by looking at one frame per scene.

9c. CONCAT
  Write build/list.txt (file 'segN.mp4' lines) and run
  ffmpeg -f concat -safe 0 -i build/list.txt -c copy build/base.mp4
  (all segments share codec/size/fps, so -c copy is safe).

9d. CAPTIONS (burn in)
  - Preferred: word timestamps from a local Whisper (faster-whisper) run on each cleaned scene
    audio; group into 2-line captions of at most 7 words, never ending a line on a function word
    (the, a, of, to, and, in, with, that, very).
  - Fallback (used in the first test): split each scene's narration at punctuation and distribute
    the scene's duration across chunks by character count. Timing then drifts by a fraction of a
    second inside long lines. Say which method you used.
  - Write build/caps.ass. Style: bold sans (DejaVu Sans), size = 3.2% of output height (about 58 at
    1080p, 100 at 1920 tall), white, 4 px black outline, bottom-centre, bottom margin 8% of height
    (9:16 needs about 12% so captions clear the platform UI).
  - ffmpeg -i build/base.mp4 -vf "ass=build/caps.ass" -c:v libx264 -crf 20 -pix_fmt yuv420p -c:a copy build/captioned.mp4

9e. OVERLAY BGM (duck under the voice, then normalise)
  ffmpeg -i build/captioned.mp4 -stream_loop -1 -i bgm/bgm.mp3 -filter_complex
   "[1:a]volume=0.35,afade=t=in:d=2,afade=t=out:st=<total-3>:d=3,atrim=0:<total>[bg];
    [0:a]asplit=2[vo][sc];
    [bg][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[ducked];
    [vo][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,
    loudnorm=I=-16:TP=-1.5:LRA=11[a]"
   -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -shortest out/<slug>.mp4
  Voice stays at full level, music sits about -14 to -18 dB under it and dips further while the
  narrator speaks. If the music is audible over the voice, lower volume to 0.25 first, not the
  compressor.

9f. QA (mandatory, report results)
  - ffprobe: duration within +/-3% of DURATION, resolution matches ASPECT_RATIO, has audio.
  - Extract 1 frame per scene (and 3 caption frames) into a contact sheet and LOOK at it: captions
    legible and not cut off, subject framed, no leftover text/watermark, no black frames.
  - ffmpeg -i out/<slug>.mp4 -af volumedetect -f null - : report mean/max volume (max below -1 dB).
  - Tell me honestly what you could not verify (you cannot hear the audio; say so).
```

---

## 10. One-shot prompt (after you trust the stages)

```text
Run the stock-media documentary playbook (stages 1-9) for:
TOPIC: ...
SYNOPSIS: ...
ASPECT_RATIO: ...
DURATION: ...
Stop at the Stage 4 gate and show me the shortlist tables (video and images) with the reason per
pick. After I reply "go", download, generate TTS, BGM and thumbnail, write the metadata, assemble,
and finish with the QA report and the output paths.
```

## 11. Cost and failure notes

| Item | Note |
|---|---|
| Storyblocks | each `get_download_url` = one licensed download on the account; cache by item id |
| Gemini TTS / Lyria / image | per-call API cost on the AI Studio key; Lyria/TTS model availability varies by key, hence ListModels first |
| Narration pace | measured: Kokoro about 3.2 words/s in this repo, Gemini TTS plan on about 2.4; trust the measured audio, not the estimate |
| Coverage gaps | specific events/people get thin stock results; use symbolic visuals or AI images, not mismatched footage |
| Not verifiable by Claude | how it sounds. A human must listen before publishing |
| Publishing | the playbook stops at files; uploading to YouTube is a separate, manual (or separately approved) step |

## 12. Known limits of this playbook

- Caption timing in the fallback mode is estimated, not forced-aligned.
- BGM is one generated track; it is not scene-aware.
- Storyblocks licensing terms for AI-generated, publicly distributed videos should be confirmed on
  your plan before publishing commercially.
  
  
  
  Runpod:-
  
  All four use RunPod's async API (/run, then poll /status/<id>). Set these first:
 
  export RUNPOD_API_KEY=...        # your RunPod key
  export RP=https://api.runpod.ai/v2
 
  The endpoint IDs come from orchestrator/src/fleet-registry.ts. The payload shapes come from the builders in orchestrator/src/steps/builders/ and ~/runpod/API.md. I haven't run any of
  these against the live endpoints.
 
  BGM (ACE-Step) — bgm-s2t (6apg6j7suzuezw)
 
  curl -X POST $RP/6apg6j7suzuezw/run \
    -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d '{"input":{"mode":"bgm","prompt":"cinematic orchestral, dramatic, no vocals","duration_s":30,"steps":20,"guidance":7.0,"project_id":"test","frame_id":"f1"}}'
  The output is an MP3 URL in audio. The orchestrator caps duration_s at 120.

  S2T (Whisper) — same endpoint, bgm-s2t

  curl -X POST $RP/6apg6j7suzuezw/run \
    -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d '{"input":{"mode":"transcribe","audio_url":"https://.../abc.wav","task":"transcribe","language":"en","return_timestamps":"word"}}'
  The output has text, word chunks, and srt. srt is only present when return_timestamps is "word".

  To burn captions into a video instead, use mode:"caption" with video_url, words_per_group, font_size, highlight_color, position and optional chunks. The tail's caption builder sends
  these.

  MMAudio SFX — mm-audio (nzkcsef9t2iv7s)

  curl -X POST $RP/nzkcsef9t2iv7s/run \
    -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d '{"input":{"mode":"v2a","video_url":"https://.../clip.mp4","prompt":"rain on tin roof, distant thunder","negative_prompt":"music, speech, voice, 
  singing","return_video":true,"project_id":"test","frame_id":"f1"}}'
  With return_video:true the output is video_url, the clip with the SFX muxed in. Without it you get a standalone audio_url MP3. Clips should be 30 s or shorter.

Qwen image gen — qwen-image-gen (e165se4r3eo5hp)

  curl -X POST $RP/e165se4r3eo5hp/run \
    -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d '{"input":{"model":"qwen","prompt":"A lighthouse at dusk, cinematic, golden light","aspect_ratio":"16:9","project_id":"test","frame_id":"f1"}}'
  model can be "qwen" or "flux" (Flux Klein 4B), because the endpoint hosts both. For image edit, use qwen-image-edit (oxwx8o879qwtla) with {"image_url":"...","prompt":"..."}.

  Poll any of them

  curl -H "Authorization: Bearer $RUNPOD_API_KEY" $RP/<endpoint_id>/status/<job_id>
  status goes IN_QUEUE, then IN_PROGRESS, then COMPLETED, and the result is in .output. Cold starts can take minutes.

  The ~/Qwen-Edit/docs/quartermaster-endpoint-integration.md doc I found covers Qwen's model/aspect_ratio options if you need more. I didn't read it.
  
  
  MeiGen-AI / InfiniteTalk

InfiniteTalk runs on Runpod Hub as a serverless image-to-video API (pricing: 480p: $0.25). InfiniteTalk is an audio-driven conversational AI video generation model. Create talking or singing videos from a single image and audio input. You can try InfiniteTalk in the browser playground on this page without writing code, or call the same endpoint from your own application through the Runpod API with an API key.

  curl -X POST https://api.runpod.ai/v2/infinitetalk/run \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer YOUR_API_KEY' \
    -d '{"input":{"prompt":"a cartoon computer talking","image":"https://image.runpod.ai/assets/meigen-ai/poddy.jpg","audio":"https://image.runpod.ai/assets/meigen-ai/audio.wav","resolution":"480p","enable_safety_checker":true}}'
    
    ComfyUI LTX2.5 I2V
    
    # Replace YOUR_API_KEY in the X-API-Key header and in extra_data.api_key_comfy_org.
curl --fail-with-body --max-time 60 --request POST 'https://cloud.comfy.org/api/prompt' \
  --header 'X-API-Key: YOUR_API_KEY' \
  --header 'Content-Type: application/json' \
  --data '{
  "prompt": {
    "75": {
      "class_type": "SaveVideo",
      "inputs": {
        "filename_prefix": "video/LTX_2.3_i2v",
        "format": "auto",
        "codec": "auto",
        "video": [
          "320:310",
          0
        ],
        "format.codec": "auto"
      },
      "_meta": {
        "title": "Save Video"
      }
    },
    "269": {
      "class_type": "LoadImage",
      "inputs": {
        "image": "UPLOADED_image_FILENAME"
      },
      "_meta": {
        "title": "Load Image"
      }
    },
    "320:276": {
      "class_type": "RandomNoise",
      "inputs": {
        "noise_seed": 42
      },
      "_meta": {
        "title": "RandomNoise"
      }
    },
    "320:277": {
      "class_type": "RandomNoise",
      "inputs": {
        "noise_seed": 60540193790228
      },
      "_meta": {
        "title": "RandomNoise"
      }
    },
    "320:278": {
      "class_type": "LTXVConcatAVLatent",
      "inputs": {
        "video_latent": [
          "320:288",
          0
        ],
        "audio_latent": [
          "320:307",
          1
        ]
      },
      "_meta": {
        "title": "Concat AV Latent"
      }
    },
    "320:279": {
      "class_type": "LTXVAudioVAELoader",
      "inputs": {
        "ckpt_name": "ltx-2.3-22b-dev-fp8.safetensors"
      },
      "_meta": {
        "title": "Load LTXV Audio VAE"
      }
    },
    "320:280": {
      "class_type": "KSamplerSelect",
      "inputs": {
        "sampler_name": "euler"
      },
      "_meta": {
        "title": "KSamplerSelect"
      }
    },
    "320:281": {
      "class_type": "ManualSigmas",
      "inputs": {
        "sigmas": "0.85, 0.7250, 0.4219, 0.0"
      },
      "_meta": {
        "title": "ManualSigmas"
      }
    },
    "320:282": {
      "class_type": "CFGGuider",
      "inputs": {
        "cfg": 1,
        "model": [
          "320:285",
          0
        ],
        "positive": [
          "320:284",
          0
        ],
        "negative": [
          "320:284",
          1
        ]
      },
      "_meta": {
        "title": "CFG Guider"
      }
    },
    "320:283": {
      "class_type": "SamplerCustomAdvanced",
      "inputs": {
        "noise": [
          "320:277",
          0
        ],
        "guider": [
          "320:314",
          0
        ],
        "sampler": [
          "320:291",
          0
        ],
        "sigmas": [
          "320:306",
          0
        ],
        "latent_image": [
          "320:318",
          0
        ]
      },
      "_meta": {
        "title": "SamplerCustomAdvanced"
      }
    },
    "320:284": {
      "class_type": "LTXVCropGuides",
      "inputs": {
        "positive": [
          "320:304",
          0
        ],
        "negative": [
          "320:304",
          1
        ],
        "latent": [
          "320:307",
          0
        ]
      },
      "_meta": {
        "title": "LTXVCropGuides"
      }
    },
    "320:285": {
      "class_type": "LoraLoaderModelOnly",
      "inputs": {
        "lora_name": "ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors",
        "strength_model": 0.5,
        "model": [
          "320:316",
          0
        ]
      },
      "_meta": {
        "title": "Load LoRA"
      }
    },
    "320:287": {
      "class_type": "LTXVLatentUpsampler",
      "inputs": {
        "samples": [
          "320:307",
          0
        ],
        "upscale_model": [
          "320:311",
          0
        ],
        "vae": [
          "320:316",
          2
        ]
      },
      "_meta": {
        "title": "LTXVLatentUpsampler"
      }
    },
    "320:288": {
      "class_type": "LTXVImgToVideoInplace",
      "inputs": {
        "strength": 1,
        "vae": [
          "320:316",
          2
        ],
        "image": [
          "320:289",
          0
        ],
        "latent": [
          "320:287",
          0
        ],
        "bypass": [
          "320:302",
          0
        ]
      },
      "_meta": {
        "title": "LTXVImgToVideoInplace"
      }
    },
    "320:289": {
      "class_type": "LTXVPreprocess",
      "inputs": {
        "img_compression": 18,
        "image": [
          "320:330",
          0
        ]
      },
      "_meta": {
        "title": "LTXV Preprocess"
      }
    },
    "320:290": {
      "class_type": "ResizeImageMaskNode",
      "inputs": {
        "resize_type": "scale dimensions",
        "scale_method": "lanczos",
        "input": [
          "269",
          0
        ],
        "resize_type.crop": "center",
        "resize_type.width": [
          "320:312",
          0
        ],
        "resize_type.height": [
          "320:299",
          0
        ]
      },
      "_meta": {
        "title": "Resize Image/Mask"
      }
    },
    "320:291": {
      "class_type": "KSamplerSelect",
      "inputs": {
        "sampler_name": "euler"
      },
      "_meta": {
        "title": "KSamplerSelect"
      }
    },
    "320:292": {
      "class_type": "ComfyMathExpression",
      "inputs": {
        "expression": "a/2",
        "values.a": [
          "320:312",
          0
        ]
      },
      "_meta": {
        "title": "Math Expression"
      }
    },
    "320:294": {
      "class_type": "ComfyMathExpression",
      "inputs": {
        "expression": "a/2",
        "values.a": [
          "320:299",
          0
        ]
      },
      "_meta": {
        "title": "Math Expression"
      }
    },
    "320:295": {
      "class_type": "EmptyLTXVLatentVideo",
      "inputs": {
        "batch_size": 1,
        "width": [
          "320:292",
          1
        ],
        "height": [
          "320:294",
          1
        ],
        "length": [
          "320:323",
          1
        ]
      },
      "_meta": {
        "title": "Empty LTXV Latent Video"
      }
    },
    "320:296": {
      "class_type": "LTXVImgToVideoInplace",
      "inputs": {
        "strength": 0.7,
        "vae": [
          "320:316",
          2
        ],
        "image": [
          "320:289",
          0
        ],
        "latent": [
          "320:295",
          0
        ],
        "bypass": [
          "320:302",
          0
        ]
      },
      "_meta": {
        "title": "LTXVImgToVideoInplace"
      }
    },
    "320:297": {
      "class_type": "LTXVAudioVAEDecode",
      "inputs": {
        "samples": [
          "320:309",
          1
        ],
        "audio_vae": [
          "320:279",
          0
        ]
      },
      "_meta": {
        "title": "LTXV Audio VAE Decode"
      }
    },
    "320:298": {
      "class_type": "ComfyMathExpression",
      "inputs": {
        "expression": "a",
        "values.a": [
          "320:300",
          0
        ]
      },
      "_meta": {
        "title": "Math Expression"
      }
    },
    "320:299": {
      "class_type": "PrimitiveInt",
      "inputs": {
        "value": 720
      },
      "_meta": {
        "title": "Height"
      }
    },
    "320:300": {
      "class_type": "PrimitiveInt",
      "inputs": {
        "value": 25
      },
      "_meta": {
        "title": "Frame Rate"
      }
    },
    "320:301": {
      "class_type": "PrimitiveInt",
      "inputs": {
        "value": 5
      },
      "_meta": {
        "title": "Duration"
      }
    },
    "320:302": {
      "class_type": "PrimitiveBoolean",
      "inputs": {
        "value": false
      },
      "_meta": {
        "title": "Switch to Text to Video?"
      }
    },
    "320:303": {
      "class_type": "CLIPTextEncode",
      "inputs": {
        "text": [
          "320:327",
          0
        ],
        "clip": [
          "320:317",
          0
        ]
      },
      "_meta": {
        "title": "CLIP Text Encode (Prompt)"
      }
    },
    "320:304": {
      "class_type": "LTXVConditioning",
      "inputs": {
        "positive": [
          "320:303",
          0
        ],
        "negative": [
          "320:313",
          0
        ],
        "frame_rate": [
          "320:298",
          0
        ]
      },
      "_meta": {
        "title": "LTXVConditioning"
      }
    },
    "320:305": {
      "class_type": "LTXVEmptyLatentAudio",
      "inputs": {
        "batch_size": 1,
        "frames_number": [
          "320:323",
          1
        ],
        "frame_rate": [
          "320:298",
          1
        ],
        "audio_vae": [
          "320:279",
          0
        ]
      },
      "_meta": {
        "title": "Empty LTXV Latent Audio"
      }
    },
    "320:306": {
      "class_type": "ManualSigmas",
      "inputs": {
        "sigmas": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"
      },
      "_meta": {
        "title": "ManualSigmas"
      }
    },
    "320:307": {
      "class_type": "LTXVSeparateAVLatent",
      "inputs": {
        "av_latent": [
          "320:283",
          0
        ]
      },
      "_meta": {
        "title": "Separate AV Latent"
      }
    },
    "320:308": {
      "class_type": "SamplerCustomAdvanced",
      "inputs": {
        "noise": [
          "320:276",
          0
        ],
        "guider": [
          "320:282",
          0
        ],
        "sampler": [
          "320:280",
          0
        ],
        "sigmas": [
          "320:281",
          0
        ],
        "latent_image": [
          "320:278",
          0
        ]
      },
      "_meta": {
        "title": "SamplerCustomAdvanced"
      }
    },
    "320:309": {
      "class_type": "LTXVSeparateAVLatent",
      "inputs": {
        "av_latent": [
          "320:308",
          0
        ]
      },
      "_meta": {
        "title": "Separate AV Latent"
      }
    },
    "320:310": {
      "class_type": "CreateVideo",
      "inputs": {
        "bit_depth": 8,
        "color_space": "sRGB",
        "codec": "none",
        "images": [
          "320:315",
          0
        ],
        "fps": [
          "320:298",
          0
        ],
        "audio": [
          "320:297",
          0
        ]
      },
      "_meta": {
        "title": "Create Video"
      }
    },
    "320:311": {
      "class_type": "LatentUpscaleModelLoader",
      "inputs": {
        "model_name": "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
      },
      "_meta": {
        "title": "Load Latent Upscale Model"
      }
    },
    "320:312": {
      "class_type": "PrimitiveInt",
      "inputs": {
        "value": 1280
      },
      "_meta": {
        "title": "Width"
      }
    },
    "320:313": {
      "class_type": "CLIPTextEncode",
      "inputs": {
        "text": "pc game, console game, video game, cartoon, childish, ugly",
        "clip": [
          "320:317",
          0
        ]
      },
      "_meta": {
        "title": "CLIP Text Encode (Prompt)"
      }
    },
    "320:314": {
      "class_type": "CFGGuider",
      "inputs": {
        "cfg": 1,
        "model": [
          "320:285",
          0
        ],
        "positive": [
          "320:304",
          0
        ],
        "negative": [
          "320:304",
          1
        ]
      },
      "_meta": {
        "title": "CFG Guider"
      }
    },
    "320:315": {
      "class_type": "VAEDecodeTiled",
      "inputs": {
        "tile_size": 768,
        "overlap": 64,
        "temporal_size": 4096,
        "temporal_overlap": 4,
        "samples": [
          "320:309",
          0
        ],
        "vae": [
          "320:316",
          2
        ]
      },
      "_meta": {
        "title": "VAE Decode (Tiled)"
      }
    },
    "320:316": {
      "class_type": "CheckpointLoaderSimple",
      "inputs": {
        "ckpt_name": "ltx-2.3-22b-dev-fp8.safetensors"
      },
      "_meta": {
        "title": "Load Checkpoint"
      }
    },
    "320:317": {
      "class_type": "LTXAVTextEncoderLoader",
      "inputs": {
        "text_encoder": "gemma_3_12B_it_fp4_mixed.safetensors",
        "ckpt_name": "ltx-2.3-22b-dev-fp8.safetensors",
        "device": "default"
      },
      "_meta": {
        "title": "Load LTXV Audio Text Encoder"
      }
    },
    "320:318": {
      "class_type": "LTXVConcatAVLatent",
      "inputs": {
        "video_latent": [
          "320:296",
          0
        ],
        "audio_latent": [
          "320:305",
          0
        ]
      },
      "_meta": {
        "title": "Concat AV Latent"
      }
    },
    "320:319": {
      "class_type": "PrimitiveStringMultiline",
      "inputs": {
        "value": "Egyptian royal in blue-and-gold headdress and high collar, white dress with golden embroidery and armbands, desert, robot soldiers in formation left and right. She walks steadily forward, head held level and gaze fixed ahead—no dipping or lowering of the head. The camera performs a single, smooth push-in only: starting in a wider shot of her, the robots, and the desert, it moves steadily forward until she is in a medium or medium-close frame, then holds. She stops, posture and head still upright, and says: “The old gods are silent. I am not.” Robot soldiers shift or march in place; sand and fabric move with the wind. No pull-back; the only camera move is the continuous push-in."
      },
      "_meta": {
        "title": "Prompt"
      }
    },
    "320:323": {
      "class_type": "ComfyMathExpression",
      "inputs": {
        "expression": "a * b + 1",
        "values.a": [
          "320:301",
          0
        ],
        "values.b": [
          "320:300",
          0
        ]
      },
      "_meta": {
        "title": "Math Expression (length)"
      }
    },
    "320:324": {
      "class_type": "LoraLoader",
      "inputs": {
        "lora_name": "gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors",
        "strength_model": 1,
        "strength_clip": 1,
        "model": [
          "320:285",
          0
        ],
        "clip": [
          "320:317",
          0
        ]
      },
      "_meta": {
        "title": "Load LoRA (Model and CLIP)"
      }
    },
    "320:325": {
      "class_type": "TextGenerateLTX2Prompt",
      "inputs": {
        "max_length": 2048,
        "sampling_mode": "on",
        "thinking": false,
        "use_default_template": true,
        "mtp": "auto",
        "clip": [
          "320:324",
          1
        ],
        "prompt": [
          "320:319",
          0
        ],
        "image": [
          "320:330",
          0
        ],
        "sampling_mode.temperature": 0.7,
        "sampling_mode.top_k": 64,
        "sampling_mode.top_p": 0.95,
        "sampling_mode.min_p": 0.05,
        "sampling_mode.repetition_penalty": 1.05,
        "sampling_mode.seed": 0,
        "sampling_mode.presence_penalty": 0
      },
      "_meta": {
        "title": "Generate LTX2 Prompt"
      }
    },
    "320:326": {
      "class_type": "PreviewAny",
      "inputs": {
        "source": [
          "320:327",
          0
        ]
      },
      "_meta": {
        "title": "Preview as Text"
      }
    },
    "320:327": {
      "class_type": "ComfySwitchNode",
      "inputs": {
        "switch": [
          "320:328",
          0
        ],
        "on_false": [
          "320:319",
          0
        ],
        "on_true": [
          "320:325",
          0
        ]
      },
      "_meta": {
        "title": "If/Else Switch"
      }
    },
    "320:328": {
      "class_type": "PrimitiveBoolean",
      "inputs": {
        "value": false
      },
      "_meta": {
        "title": "Boolean (Enable Prompt Enhance)"
      }
    },
    "320:330": {
      "class_type": "ResizeImageMaskNode",
      "inputs": {
        "resize_type": "scale longer dimension",
        "scale_method": "area",
        "input": [
          "320:290",
          0
        ],
        "resize_type.longer_size": 1536
      },
      "_meta": {
        "title": "Resize Image/Mask"
      }
    }
  },
  "extra_data": {
    "api_key_comfy_org": "YOUR_API_KEY"
  }
}'

