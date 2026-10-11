# Documentary generator as a Docker service: design

Date: 2026-10-11. Status: design agreed, nothing built yet. Decisions: Approach 1 (one `c9g.xlarge` started on demand), arm64 image built by CodeBuild and stored in ECR, the QM Orchestrator on the VPS queues requests, starts the instance, calls the container API and stores status in Postgres. Sections 4 and 13 are the contract.

## 1. Short answer

Yes, this can be packaged as one Docker image: Ubuntu 24.04 with a desktop you open in your own browser, a browser inside it for the Storyblocks sign-in, Claude Code running on Sonnet 5.5 as the orchestrator, and a small HTTP API to start a documentary and poll its status.

Two things need to be understood before building it:

1. **There is no single "current script" yet.** The three episodes were produced by a Claude Code session following the playbook (`docs/CLAUDE_SESSION_STOCK_DOCUMENTARY_PROMPTS.md`) and writing helper scripts as it went. Those helpers are copied per episode and have episode-specific values hardcoded. The container therefore needs two parts: the LLM orchestrator, and a cleaned-up, config-driven version of the helpers. Section 6 lists the work.
2. **Put the Anthropic key in an environment variable, not in the reference document.** The reason and the alternative are in section 5.

## 2. What the pipeline is today

| Stage | Done by | Where it runs |
|---|---|---|
| Script (long + 3 Shorts), fact flags | LLM (the Claude Code session) | Anthropic API |
| Stock video and images | Storyblocks MCP (`https://mcp.storyblocks.com/mcp`, HTTP, browser sign-in) | Storyblocks |
| Archive images | Wikimedia Commons API (`fetch_*.py`) | Local HTTP calls |
| Narration | Gemini TTS, voice Charon | Google AI Studio |
| Character voices, word timings, images, music, ambience | Kokoro, Whisper, Qwen-Image, ACE-Step, MMAudio | RunPod serverless |
| Talking characters | InfiniteTalk | RunPod Hub |
| Animated stills and talking shots | LTX on ComfyUI Cloud (`build/ltx.py`) | cloud.comfy.org |
| Thumbnail | Gemini image model | Google AI Studio |
| Assembly, captions, loudness | `gen_assemble.py`, `gen_short.py`, ffmpeg | Local CPU |
| Metadata, credits | Python generators | Local |

All generation is remote. The container needs CPU, disk and network only; no GPU.

Measured on this machine (8 cores, 7 GB RAM, ffmpeg 6.1.1, Python 3.12.3, Node 24, Claude Code 2.1.296):

- Long-video assembly: about 9 minutes per episode (4 segments in parallel).
- Each Short: 1 to 2 minutes.
- Disk: 1.4 to 1.7 GB per episode run folder.
- InfiniteTalk: up to about 15 minutes on a cold endpoint; LTX about 40 seconds per 5-second clip.

## 3. Proposed architecture

```
your laptop
  |-- browser --> https://host/desktop   (noVNC: the Ubuntu desktop)
  QM Orchestrator (VPS, Postgres queue) --> https://host/v1/...  (REST API)
                    |
        +-----------+--------------------------------------+
        |  container: docgen (Ubuntu 24.04)                |
        |                                                  |
        |  XFCE desktop + VNC server + noVNC               |
        |    Firefox, terminal, VS Code                    |
        |                                                  |
        |  API server (FastAPI, port 8080)                 |
        |    one job at a time -> worker                   |
        |                                                  |
        |  worker: `claude -p` (Sonnet 5.5)                |
        |    Storyblocks MCP (HTTP, OAuth token on disk)   |
        |    docgen toolkit (python + ffmpeg)              |
        |                                                  |
        |  volumes: /data/runs  /data/claude  /app (code)  |
        +--------------------------------------------------+
                    |
   Anthropic, Storyblocks, Google AI Studio, RunPod, ComfyUI Cloud, Wikimedia
```

One process supervisor (supervisord or s6) starts the VNC server, noVNC, and the API server.

### 3.1 The desktop

- XFCE with TigerVNC and noVNC, so the desktop opens as a web page. No VNC client is needed.
- Firefox from Mozilla's apt repository. Google Chrome has no Linux arm64 build, and the chosen instance type is arm64 (section 13.1). Ubuntu's own Chromium and Firefox packages are snaps, and snaps do not run in a normal container.
- A terminal, git, and VS Code (the `.deb`) for maintaining the scripts.
- A ready-made alternative is to base the image on `linuxserver/webtop:ubuntu-xfce`, which already provides the web desktop. Building on plain `ubuntu:24.04` gives more control and a smaller image.

### 3.2 Why the browser must be inside the container

The Storyblocks MCP is an HTTP server that authorises through a browser sign-in. Claude Code opens the sign-in page and then waits for the redirect on a `localhost` port. That redirect only reaches Claude Code if the browser runs on the same machine, which here means inside the container. This is the real reason for the desktop, and it works.

One-time setup, done from the desktop terminal:

```bash
claude mcp add --transport http storyblocks https://mcp.storyblocks.com/mcp --scope user
claude            # then /mcp, choose storyblocks, Authenticate; Firefox opens
claude mcp list   # expect: storyblocks ... Connected
```

The token is stored in Claude Code's config (`~/.claude/` and `~/.claude.json`). Both must be on a persistent volume, otherwise every container restart needs a new sign-in.

### 3.3 The orchestrator

The API worker starts a headless Claude Code run per job:

```bash
cd /data/runs/<job_id>
claude -p "$(cat /app/prompts/produce.md)" \
  --model claude-sonnet-5-5 \
  --output-format stream-json \
  --max-turns 400 \
  --permission-mode acceptEdits \
  --allowedTools "Bash,Read,Write,Edit,mcp__storyblocks__*"
```

- `ANTHROPIC_API_KEY` in the environment makes Claude Code bill the API key instead of a subscription login.
- `produce.md` is the playbook turned into one instruction file: inputs, stage order, the rules learned so far (plain-text TTS, licence each Storyblocks item once, queue cold endpoints, write `status.json` after each stage).
- The run's `session_id` is saved, so an approval or correction continues the same session with `claude -p --resume <session_id> "<instruction>"`.

Using Claude Code as the orchestrator keeps what worked in the three episodes: it inspects frames, replaces wrong images, and adapts when an endpoint fails. A fully scripted pipeline with the LLM only writing the script would be cheaper and more predictable, but it would lose that judgement. Start with Claude Code; move stages into plain code as they stabilise.

## 4. The container API (contract for the orchestrator)

The API server runs inside the container on the EC2 instance (FastAPI, port 8080) and is published through a CloudFront distribution, which provides the HTTPS endpoint (13.3). The orchestrator is its only client. The orchestrator owns the queue; the container runs **one job at a time** and refuses a second.

Base URL: `https://<distribution>.cloudfront.net/v1` (or a custom domain on the distribution; see 13.3). While the instance is stopped, CloudFront answers 502 or 504; the orchestrator treats that as "not up yet".
Every request carries `Authorization: Bearer <DOCGEN_API_TOKEN>`. Bodies are JSON, UTF-8. Times are ISO 8601 UTC.

### 4.1 Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/health` | Is the container ready, and are the credentials valid? Call after starting the instance. |
| POST | `/v1/documentaries` | Start a documentary. Returns 202 with `job_id`. |
| GET | `/v1/documentaries/{job_id}` | Current status object (4.4). The pull path. |
| GET | `/v1/documentaries/{job_id}/events?after_seq=N` | Status events after sequence N, for catching up on missed webhooks. |
| POST | `/v1/documentaries/{job_id}/respond` | Answer a checkpoint (4.6). |
| POST | `/v1/documentaries/{job_id}/cancel` | Stop the job. |
| GET | `/v1/documentaries/{job_id}/files/{path}` | Fetch a file from the run folder (scripts for review, small outputs). |

Status reaches the orchestrator in two ways. Use both:

- **Push (primary):** the container POSTs a signed event to the orchestrator's `callback.url` on every state or stage change, plus a heartbeat every 60 seconds while a job runs (4.5).
- **Pull (fallback):** the orchestrator calls `GET /v1/documentaries/{job_id}` if no event has arrived for 3 minutes, and `.../events?after_seq=N` to fill gaps.

### 4.2 `POST /v1/documentaries`: request payload

Minimal request:

```json
{
  "request_id": "qm-docgen-000123",
  "topic": "The Thirty Years' War",
  "synopsis": "How a religious war in central Europe created the modern system of sovereign states.",
  "callback": {"url": "https://orchestrator.example.com/v1/webhooks/docgen"}
}
```

Full request, with defaults shown:

```json
{
  "request_id": "qm-docgen-000123",
  "topic": "The Thirty Years' War",
  "synopsis": "How a religious war in central Europe created the modern system of sovereign states.",
  "series": {
    "name": "Wars That Shaped the World",
    "episode": 7,
    "previous_episode_title": "The Empire That Connected Asia and Europe",
    "previous_episode_url": "https://youtu.be/...",
    "next_episode_title": "The War That Made France and England",
    "playlist_url": "https://www.youtube.com/playlist?list=..."
  },
  "long": {
    "enabled": true,
    "aspect": "16:9",
    "target_seconds": 480,
    "narrator_voice": "Charon"
  },
  "shorts": {
    "count": 3,
    "aspect": "9:16",
    "angles": ["spark", "myth", "legacy"]
  },
  "visuals": {
    "archive": true,
    "stock": true,
    "image_gen": true,
    "talking_clips": 3,
    "animated_stills": 10,
    "dramatised_character": true,
    "allow_graphic_archive": false
  },
  "review_mode": "checkpoints",
  "model": "claude-sonnet-5-5",
  "limits": {"max_runtime_minutes": 150, "max_llm_turns": 400},
  "output": {"prefix": "docgen/qm-docgen-000123/"},
  "callback": {"url": "https://orchestrator.example.com/v1/webhooks/docgen"}
}
```

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `request_id` | string, 1 to 64 chars, `[A-Za-z0-9_-]` | yes | | The orchestrator's own id. Idempotency key: posting the same `request_id` again returns the existing job and starts nothing. |
| `topic` | string, up to 200 chars | yes | | Working title. |
| `synopsis` | string, up to 1,000 chars | yes | | Angle, audience and tone, 2 to 3 sentences. |
| `series.*` | object | no | none | Used for the end card, description links and "next episode" line. Missing URLs become placeholders in the metadata and are reported in `warnings`. |
| `long.enabled` | bool | no | `true` | |
| `long.aspect` | `16:9` | no | `16:9` | Only 16:9 is built today. |
| `long.target_seconds` | int, 240 to 720 | no | `480` | About 2.5 narrated words per second. |
| `long.narrator_voice` | string | no | `Charon` | Gemini TTS voice name. |
| `shorts.count` | int, 0 to 3 | no | `3` | |
| `shorts.angles` | array of `spark`, `myth`, `legacy` | no | all three | One Short per angle. |
| `visuals.archive` | bool | no | `true` | Wikimedia Commons and Library of Congress images. |
| `visuals.stock` | bool | no | `true` | Storyblocks MCP. If `true` and the sign-in has expired, the job is rejected with 503. |
| `visuals.image_gen` | bool | no | `true` | Qwen-Image for scenes with no archive picture. |
| `visuals.talking_clips` | int, 0 to 5 | no | `3` | InfiniteTalk narrator clips, each up to 45 seconds. |
| `visuals.animated_stills` | int, 0 to 15 | no | `10` | LTX clips of 5 seconds each. |
| `visuals.dramatised_character` | bool | no | `true` | One invented talking character (10-second LTX clip). Labelled as a dramatisation in the description. |
| `visuals.allow_graphic_archive` | bool | no | `false` | If `false`, archive photos showing the dead are avoided. |
| `review_mode` | `checkpoints` or `auto` | no | `checkpoints` | See 4.6. |
| `model` | string | no | `claude-sonnet-5-5` | |
| `limits.max_runtime_minutes` | int, 30 to 300 | no | `150` | Hard stop; the job fails with `timeout`. |
| `limits.max_llm_turns` | int | no | `400` | |
| `output.prefix` | string | no | `docgen/<request_id>/` | Key prefix in the output bucket. |
| `callback.url` | https URL | yes | | Where status events are POSTed (4.5). |

API keys are never part of the payload. The webhook signing secret is shared out of band (`DOCGEN_CALLBACK_SECRET` on both sides).

### 4.3 `POST /v1/documentaries`: responses

| Status | Meaning | Body |
|---|---|---|
| 202 | Accepted, job started | `{"job_id": "dg_01J...", "request_id": "...", "state": "running", "status_url": "/v1/documentaries/dg_01J..."}` |
| 200 | Same `request_id` already known | Same body, current `state`. Nothing new is started. |
| 400 | Validation error | `{"error": {"code": "invalid_field", "field": "long.target_seconds", "message": "..."}}` |
| 401 | Bad or missing token | `{"error": {"code": "unauthorized"}}` |
| 403 | The request did not come through CloudFront (origin header missing or wrong) | `{"error": {"code": "forbidden"}}` |
| 409 | Another job is running | `{"error": {"code": "busy", "current_job_id": "dg_..."}}`. The orchestrator keeps the request queued. |
| 503 | Not ready | `{"error": {"code": "not_ready", "checks": {...}}}`, the same `checks` as `/v1/health`. |

`GET /v1/health`:

```json
{
  "ready": true,
  "image": "docgen:3f2a91c",
  "runner": "claude",
  "busy": false,
  "current_job_id": null,
  "checks": {
    "storyblocks_mcp": "connected",
    "anthropic": "set",
    "gemini": "set",
    "runpod": "set",
    "comfy": "set",
    "callback_secret": "set",
    "disk_free_gb": 71
  },
  "uptime_seconds": 94,
  "idle_seconds": 12
}
```

The key checks report `set` or `missing`: they confirm the key is present, not that it is valid. A bad key shows up as a job failure. `idle_seconds` is the time since the last authenticated call when no job is running; the instance's dead-man timer uses it. `storyblocks_mcp` is `connected`, `needs_login` or `not_configured`. `needs_login` means someone must open the desktop and sign in again; the orchestrator should alert and hold `visuals.stock: true` jobs.

### 4.4 The status object

Returned by `GET /v1/documentaries/{job_id}` and embedded in every webhook event.

```json
{
  "job_id": "dg_01JB2M8Q",
  "request_id": "qm-docgen-000123",
  "seq": 14,
  "state": "running",
  "stage": "build_long",
  "stages_done": ["setup", "script", "assets_queued", "assets_ready", "narration", "timings"],
  "progress": 0.72,
  "message": "Assembling the long video: 18 of 29 segments rendered.",
  "next_steps": ["Build 3 Shorts", "Write metadata, credits and thumbnail"],
  "awaiting": null,
  "warnings": [
    "14 claims flagged verify",
    "No audio has been listened to"
  ],
  "outputs": [],
  "costs": {"infinitetalk_clips": 5, "ltx_clips": 12, "llm_input_tokens": 0, "llm_output_tokens": 0},
  "error": null,
  "created_at": "2026-10-11T12:02:11Z",
  "stage_started_at": "2026-10-11T12:41:50Z",
  "updated_at": "2026-10-11T12:44:03Z"
}
```

| Field | Values |
|---|---|
| `state` | `running`, `awaiting_input`, `succeeded`, `failed`, `cancelled` |
| `stage` | `setup`, `script`, `assets_queued`, `assets_ready`, `narration`, `timings`, `build_long`, `build_shorts`, `metadata`, `upload_outputs`, `done` |
| `seq` | Integer that increases by one on every change. Use it to order and de-duplicate events. |
| `progress` | 0 to 1, a rough estimate from stage weights. |
| `awaiting` | `null`, or `{"checkpoint_id": "cp_script", "question": "...", "review_files": ["script/script.json", "..."]}` |
| `error` | `null`, or `{"code": "timeout" | "storyblocks_auth" | "generation_failed" | "llm_error" | "internal", "stage": "...", "message": "...", "retryable": true}` |
| `outputs` | On success, a list of `{"kind", "key", "bytes", "seconds"}`. Kinds: `long_video`, `short_video`, `thumbnail`, `metadata_long`, `metadata_shorts`, `credits`, `script`. `key` is the object key under `output.prefix`. |

### 4.5 The endpoint that receives status: the orchestrator webhook

This is the endpoint you asked about. It lives on the orchestrator, not in the container. The container calls it:

```
POST {callback.url}          e.g. https://orchestrator.example.com/v1/webhooks/docgen
Content-Type: application/json
X-Docgen-Event: stage.completed
X-Docgen-Delivery: 7b1d0c1e-...            (unique per delivery attempt group)
X-Docgen-Signature: sha256=<hex HMAC-SHA256 of the raw body with DOCGEN_CALLBACK_SECRET>
```

```json
{
  "event": "stage.completed",
  "job_id": "dg_01JB2M8Q",
  "request_id": "qm-docgen-000123",
  "seq": 14,
  "sent_at": "2026-10-11T12:44:03Z",
  "status": { "...the full status object from 4.4..." }
}
```

| `event` | When |
|---|---|
| `job.accepted` | Right after the 202. |
| `stage.started`, `stage.completed` | At each stage boundary. |
| `checkpoint.awaiting_input` | The job has paused for a decision (4.6). |
| `status.updated` | The status changed inside a stage (new message, warning, output or cost). |
| `job.heartbeat` | Every 60 seconds while `running`. Same `seq` as the last change. |
| `job.succeeded`, `job.failed`, `job.cancelled` | Terminal. Sent once; no events follow. |

Rules for the orchestrator's handler:

- Verify the signature against the raw body before parsing. Reject with 401 if it fails.
- Reply 2xx within 10 seconds. Anything else is retried: 5 attempts at 5 s, 15 s, 60 s, 3 min, 5 min.
- Delivery is at-least-once and may arrive out of order. Apply an event only if its `seq` is greater than the stored `seq` for that job; always record `last_heartbeat_at`.
- If no event of any kind arrives for 3 minutes, poll `GET /v1/documentaries/{job_id}`. If the API does not answer for 10 minutes, mark the job `failed` with `instance_unreachable` and stop the instance.

Suggested Postgres tables on the VPS:

```sql
create table docgen_jobs (
  request_id        text primary key,
  job_id            text unique,
  state             text not null default 'queued',  -- queued | starting_instance | running | awaiting_input | succeeded | failed | cancelled
  stage             text,
  seq               integer not null default 0,
  progress          real,
  message           text,
  request           jsonb not null,                  -- the payload sent to the container
  status            jsonb,                           -- the last status object received
  outputs           jsonb,
  error             jsonb,
  attempts          integer not null default 0,
  queued_at         timestamptz not null default now(),
  started_at        timestamptz,
  finished_at       timestamptz,
  last_heartbeat_at timestamptz,
  updated_at        timestamptz not null default now()
);
create index on docgen_jobs (state, queued_at);

create table docgen_events (
  id          bigserial primary key,
  request_id  text not null references docgen_jobs,
  seq         integer not null,
  event       text not null,
  body        jsonb not null,
  received_at timestamptz not null default now(),
  unique (request_id, seq, event)
);
```

`queued` and `starting_instance` exist only in the orchestrator; the container never reports them.

### 4.6 Checkpoints

With `review_mode: "checkpoints"` the job pauses twice and sends `checkpoint.awaiting_input`:

| `checkpoint_id` | When | What to review |
|---|---|---|
| `cp_script` | After the long and Shorts scripts are written, before any paid generation | `script/script.json`, `shorts/*/script.json` |
| `cp_final` | After everything is built, before outputs are published as final | The videos, metadata and the `warnings` list |

Answer with:

```json
POST /v1/documentaries/{job_id}/respond
{
  "checkpoint_id": "cp_script",
  "action": "approve",
  "instructions": ""
}
```

`action` is `approve`, `revise` (with free-text `instructions`, for example "cut the second Russia scene, make Short B about X"), or `abort`. A `revise` returns the job to `running` and later raises the same checkpoint again. A checkpoint left unanswered for 24 hours fails the job with `checkpoint_timeout`; the orchestrator should stop the instance while it waits and restart it to deliver the answer, because the job state is on the disk and survives a stop.

With `review_mode: "auto"` there are no pauses. The `warnings` list still carries the fact-check flags.

### 4.7 Status of the image build (CodeBuild)

If "status on the build" meant the Docker image build and not the documentary job: CodeBuild reports that itself, the container is not involved.

- Poll: `aws codebuild batch-get-builds --ids <build-id> --query 'builds[0].[buildStatus,currentPhase]'`. `buildStatus` is `IN_PROGRESS`, `SUCCEEDED`, `FAILED`, `FAULT`, `STOPPED` or `TIMED_OUT`.
- Push: an EventBridge rule on `CodeBuild Build State Change` for project `docgen-image`, with an API destination that POSTs to an orchestrator endpoint such as `/v1/webhooks/codebuild`.
- The running container reports which image it is in `GET /v1/health` (`"image": "docgen:<git sha>"`), so the orchestrator can confirm a new build is actually deployed.

## 5. Secrets

You proposed adding the Anthropic key to the reference document. I recommend against it:

- That document is an instruction file that gets read into the model's context and copied between folders. A key in it ends up in transcripts and logs.
- The file already holds the Gemini, RunPod and ComfyUI keys as an uncommitted local edit. Baking it into an image would put every key into an image layer, where it stays even if a later layer deletes it.

Use environment variables instead, supplied by a `.env` file that is not in git and not in the image:

```
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-5-5
GEMINI_API_KEY=
RUNPOD_API_KEY=
COMFY_API_KEY=
API_TOKEN=
VNC_PASSWORD=
```

The helpers currently read keys from the document with a regex and an absolute path (`/home/roman-antony/local-gen-documentary/docs/...`). They need a small change to read the environment first. If you still want the document route, mount the document at runtime as a read-only file and never copy it into the image.

## 6. Work needed on the scripts

The helpers work, but they are per-episode copies. Before they can run for an arbitrary topic they need these changes:

| Problem today | Change |
|---|---|
| Keys parsed from the doc at an absolute home path (`rp.py`, `ltx.py`, `tts_long.py`) | Read env vars; paths relative to the run folder |
| `gen_assemble.py` hardcodes scene order, the character-clip map, the soldier asset name, output filename | Read them from `script/script.json` (per-scene `kind`, `clip`, `order`) |
| One batch script per episode (`rp_e2_batch1.py`, `rp_e3_batch1.py`, ...) with prompts inline | One `queue_assets.py` driven by an `assets.json` the LLM writes |
| `fetch_e2.py`, `fetch_e3.py` with query lists inline | One `fetch_archive.py --queries queries.json` |
| `make_cards.py` end-card text edited by hand | Take text and background as arguments |
| Metadata and credits generated by one-off inline Python | Proper `make_metadata.py` and `make_credits.py` |
| No status file | Each stage writes `status.json` |
| Scripts live in run folders, not in their own git repository | Move to `/app/docgen/` in a dedicated repo |

Known weak points to carry into the design, because the orchestrator should check them itself:

- Commons search picks wrong images (a 1909 parade for a plantation, a 2002 salvage photo for the USS Monitor). Every archive image needs a visual check before use.
- Loudness lands 1.5 to 3 dB under the -14 LUFS target.
- Nothing in the pipeline can hear audio. A human listen is still required before publishing.

## 7. Image contents

```dockerfile
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    xfce4 xfce4-terminal dbus-x11 tigervnc-standalone-server novnc websockify \
    ffmpeg python3 python3-pip python3-pil git curl ca-certificates supervisor \
    fonts-dejavu-core fonts-noto-color-emoji \
 && rm -rf /var/lib/apt/lists/*
# Firefox from Mozilla's apt repo (not the snap), Node 24, VS Code .deb
# npm install -g @anthropic-ai/claude-code
# pip install fastapi uvicorn
RUN useradd -m -s /bin/bash docgen
COPY docgen/ /app/docgen/
COPY api/ /app/api/
COPY prompts/ /app/prompts/
COPY supervisord.conf /etc/supervisor/conf.d/docgen.conf
USER docgen
EXPOSE 6080 8080
CMD ["supervisord", "-n"]
```

The two fonts are required: the caption and end-card code uses DejaVu Sans Bold and Noto Color Emoji by path.

```yaml
services:
  docgen:
    build: .
    env_file: .env
    ports:
      - "127.0.0.1:6080:6080"   # desktop (noVNC)
      - "127.0.0.1:8080:8080"   # API
    volumes:
      - runs:/data/runs                    # outputs, 1.5 GB per episode
      - claude:/home/docgen/.claude        # MCP token, sessions
      - ./claude.json:/home/docgen/.claude.json
      - ./docgen:/app/docgen               # scripts, editable from the desktop
    shm_size: 1gb                          # Firefox needs it
volumes: {runs: {}, claude: {}}
```

Sizing: 4 or more cores, 8 GB RAM, 50 GB disk for a few dozen episodes. Run one job at a time; assembly already uses all cores.

## 8. Security

- Bind both ports to localhost and reach them through a VPN, an SSH tunnel, or a reverse proxy with TLS. The desktop is a logged-in session holding every credential, so it must not be open to the internet behind only a VNC password.
- Run as a non-root user. If the orchestrator is given `--dangerously-skip-permissions` for unattended runs, the container is the only boundary, so do not mount anything from the host beyond the three volumes.
- API token on every request; rate-limit job creation, because each job spends money on five services.
- Per-job limits: `--max-turns`, a wall-clock timeout, and a cap on generated clips taken from the request.

## 9. Licensing and cost points

- Storyblocks: `get_download_url` licenses the item on every call. The toolkit must cache downloads and never re-request. Check that your Storyblocks plan allows automated use through the MCP; I have not verified this.
- MMAudio weights are CC BY-NC. Episode 1's Shorts use MMAudio ambience. Confirm this is acceptable for a monetised channel, or use only LTX and ACE-Step audio.
- Some Commons images are CC BY-SA and need attribution; the credits generator already lists them.
- Costs I can state: InfiniteTalk is $0.25 per 480p clip per the reference document. I have no measured figures for the other RunPod endpoints, ComfyUI Cloud, Gemini, or Sonnet 5.5 token use per episode. The first containerised runs should record these per job and return them in the status response.

## 10. What is verified and what is not

Verified on this machine:

- The Storyblocks MCP is configured as HTTP at `https://mcp.storyblocks.com/mcp`.
- The full pipeline ran three times with the tools and versions listed in section 2.
- RunPod, ComfyUI Cloud and Gemini calls work with plain HTTP from Python's standard library.

Not verified, to test first:

- That the Storyblocks sign-in completes inside a container desktop and the token survives a restart.
- How long that token lasts, and whether a headless run refreshes it or fails.
- That a headless `claude -p` run can carry a whole episode (about an hour, hundreds of tool calls) without stalling, and how it behaves at context limits.
- Sonnet 5.5 quality on this workflow. The three episodes were not all produced on that model.

## 11. Build order

1. **Repository.** Create a dedicated git repository `docgen` holding the Dockerfile, `buildspec.yml`, the API server, `prompts/produce.md` and the toolkit. The scripts currently live in per-episode run folders and are not versioned on their own.
2. **Image pipeline.** ECR repository `docgen`, CodeBuild project `docgen-image` on an ARM runner (13.2). First successful push proves the arm64 build, including Firefox.
3. **Instance and sign-in test.** Launch the `c9g.xlarge`, pull the image, open the desktop, authenticate the Storyblocks MCP, stop and start the instance, confirm it still says Connected. This removes the largest unknown.
4. **Toolkit clean-up.** Section 6. Re-render Episode 3 from its existing assets with the generic scripts to prove nothing regressed, and time the assembly on Graviton.
5. **API and headless run.** The endpoints in section 4, `status.json`, webhooks, and one short test topic end to end with Sonnet 5.5.
6. **Orchestrator integration.** Postgres tables, the queue, instance start and stop, the webhook handler, alerts.
7. **Hardening.** Dead-man stop, uptime alarm, disk clean-up, cost recording.

### 11.1 Implementation status (2026-10-11)

Code is in `~/docgen` (a local git repository, nothing committed or pushed yet).

| Item | State |
|---|---|
| Generic toolkit `docgen/` (status, archive fetch, asset queue, narration, timings, long and Short builders, cards, thumbnail, metadata, upload) | Written. The long and Short builders were regression-tested against Episode 3: render commands, captions and segment lists are byte-identical to the per-episode scripts. |
| API server `api/server.py` | Written. 27 contract checks pass against a mock runner: auth, CloudFront origin header, validation, idempotency, busy, both checkpoints with revise, signed webhooks with ordered `seq`, heartbeats, events, file download, failure, cancel. |
| `prompts/produce.md` | Written. Not yet exercised by a real Claude run. |
| Image | Builds locally for amd64 (4.0 GB). In the container: desktop reachable over noVNC, Firefox loads pages, Claude Code 2.1.296, ffmpeg renders a segment with captions, the API runs a mock job to success. |
| arm64 build | Done by CodeBuild on 2026-10-11: build `docgen-image:3042422a` succeeded in about 3 minutes from commit `64db9c5`. The in-build smoke test printed `aarch64`, ffmpeg 6.1.1 and Firefox 157. Image in ECR as `docgen:latest` and `docgen:64db9c5`, 1.01 GB compressed. Rebuilt from `7577d07`. |
| Paid calls through the ported toolkit, Storyblocks sign-in in the container, a real end-to-end job | Not done. |
| AWS resources | Created in us-east-1 (profile `default`): ECR repository `docgen` (scan on push, keep last 10 images), IAM role `docgen-codebuild-role` (push to that repository and its own logs only), CodeBuild project `docgen-image` (ARM, large, privileged, source: the public GitHub repository, branch `main`, started by hand). IAM role `docgen-instance-role` with instance profile `docgen-instance-profile` (SSM, pull from the repository, read parameters under `/docgen/`, stop itself), security group `docgen-instance` (no inbound rules). Not created: CloudFront, the parameters under `/docgen/`, an output bucket. |
| ECR scan | 18 critical and 194 high findings, unchanged after adding `apt-get upgrade` (image `7577d07`). The critical ones are in ffmpeg 6.1.1 and `libcjson1`, which come from Ubuntu's `universe` component and get security fixes only through Ubuntu Pro. Options: a current static ffmpeg build in place of the Ubuntu package, or Ubuntu Pro. ffmpeg here only reads files the pipeline fetched itself. Not fixed. |
| Instance | Launched 2026-10-11: `c9g.xlarge`, Ubuntu 24.04 arm64, us-east-1a, 100 GB encrypted gp3, public IP, no inbound rules, user data `deploy/setup-instance.sh`. Setup finished in 78 seconds: Docker, compose, the systemd unit and dead-man timer are active and the image was pulled from ECR. The eight `/docgen/` parameters were stored with `deploy/put-params.py`; the API and desktop then came up and health reports every key as `set`. `ready` stays false until Storyblocks is signed in. |
| CloudFront | Created 2026-10-11. **API base URL: `https://doc-gen.ai-storystudio.com`** (distribution `E3RSXC7W2L5H0P`, ACM certificate for that name, Route 53 alias records). Origin: a CloudFront VPC origin to the instance on port 8080; the security group admits only CloudFront's VPC-origin security group. HTTPS only, caching disabled, all headers except `Host` forwarded, `X-Origin-Verify` added from `/docgen/DOCGEN_ORIGIN_SECRET`. Tested: health 200 with the token, 401 without, plain HTTP refused (403), direct connection to the instance's public IP times out. Callers are limited to the orchestrator's address `129.121.78.38` by the CloudFront function `docgen-allow-orchestrator` (viewer request); IPv6 is off so the caller always arrives over IPv4. From any other address the URL returns 403, including from a developer machine. IAM user `docgen-orchestrator` can start, stop and describe the instance; its access key is not created. Not done: a test after a stop and start. When the instance is stopped the URL returns a CloudFront 502/504, so the orchestrator must start the instance first and poll health. If the origin secret is rotated, update the distribution's origin header too. |

## 12. Decisions still needed from you

1. Where do finished files go: the existing S3 bucket, a new one, or R2 with the `storystudio/...` naming convention your other workers use?
2. The VPS's fixed outbound IP, if you want a WAF rule restricting the CloudFront distribution to it. Optionally a custom domain for the distribution.
3. `checkpoints` or `auto` as the orchestrator's default?
4. Should the orchestrator stop the instance while a checkpoint is waiting for you (cheaper), or leave it running (faster to resume)?
5. Which GitHub repository should CodeBuild build from?

## 13. Hosting: Approach 1, as agreed

Checked against the AWS account on 2026-10-11 (us-east-1): `c9g.xlarge` exists with 4 vCPU, 8 GB, arm64, at 0.17388 USD per hour on demand. An episode takes roughly 1 to 1.5 hours, so compute is about 0.20 to 0.30 USD per episode. The generation services will cost far more than this.

### 13.1 Consequence of Graviton: the image is arm64

- Google Chrome has no Linux arm64 build. The desktop uses Firefox; Mozilla's apt repository carries arm64 packages as far as I know, to be confirmed in the first build. Chromium is the fallback.
- ffmpeg, Python, Node, Claude Code and VS Code all have arm64 builds.
- Timings in section 2 were measured on an 8-core x86 machine. Expect assembly on 4 Graviton vCPUs to take longer than 9 minutes.

### 13.2 Building the image with CodeBuild, storing it in ECR

- **ECR:** private repository `docgen`, scan on push, lifecycle policy keeping the last 10 images. Tags: the git commit SHA, plus `latest`.
- **CodeBuild project `docgen-image`:**
  - Environment type `ARM_CONTAINER`, image `aws/codebuild/amazonlinux-aarch64-standard:3.0`, compute `BUILD_GENERAL1_LARGE`, privileged mode on (needed to run Docker).
  - Source: the `docgen` GitHub repository, built on push to `main` or started by hand.
  - Service role: push to the one ECR repository, write its own CloudWatch logs. Nothing else.
  - No API keys in the build. The image must contain no secrets and no `.claude` folder.

```yaml
# buildspec.yml
version: 0.2
env:
  variables:
    REPO: docgen
phases:
  pre_build:
    commands:
      - ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
      - REGISTRY=$ACCOUNT.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com
      - aws ecr get-login-password | docker login --username AWS --password-stdin $REGISTRY
      - TAG=${CODEBUILD_RESOLVED_SOURCE_VERSION:0:7}
  build:
    commands:
      - docker build --build-arg GIT_SHA=$TAG -t $REGISTRY/$REPO:$TAG -t $REGISTRY/$REPO:latest .
  post_build:
    commands:
      - docker push $REGISTRY/$REPO:$TAG
      - docker push $REGISTRY/$REPO:latest
      - printf '{"image":"%s/%s:%s"}' $REGISTRY $REPO $TAG > image.json
artifacts:
  files: [image.json]
```

Deploying a new image: the instance runs `docker compose pull && docker compose up -d` at boot, so the next start picks up `latest`. Pin a SHA tag in the compose file when you want a controlled roll-out. Build status: see 4.7.

### 13.3 The instance

- Ubuntu 24.04 arm64, `c9g.xlarge`, one 100 GB gp3 volume. Tags `Name=docgen`, `Purpose=docgen`, `ManagedBy=qm-orchestrator`.
- The volume persists across stop and start, so the Storyblocks token, Claude sessions, run folders and scripts edited from the desktop all survive.
- Docker plus the compose file from section 7, started by a systemd unit at boot. `/app/docgen` is bind-mounted from the volume so desktop edits persist; commit them back to git, otherwise the next image build will not contain them.
- **Network: the API is exposed through CloudFront.**
  - CloudFront gives the orchestrator a stable HTTPS address and a managed certificate, so the instance needs no Elastic IP, no DNS record and no TLS setup of its own.
  - Preferred origin: a **CloudFront VPC origin** pointing at the instance on port 8080. The instance can then sit in a private subnet with no public IP, and its private IP does not change across stop and start. I believe VPC origins accept EC2 instances directly; confirm when creating it. Fallback: a public instance with an Elastic IP as a custom origin, and a security group that admits only the CloudFront origin-facing managed prefix list.
  - A private instance still needs outbound internet for Anthropic, Storyblocks, Google, RunPod, ComfyUI and Wikimedia. That means a NAT gateway (a fixed monthly cost) or a public IP on the instance. A public IP with no inbound rule other than CloudFront is the cheaper choice.
  - Distribution settings: caching disabled (`CachingDisabled` policy), all headers except `Host` forwarded so `Authorization` reaches the API (`AllViewerExceptHostHeader`), all HTTP methods allowed, and a custom origin header `X-Origin-Verify: <secret>`. The API rejects any request without that header with 403 (`DOCGEN_ORIGIN_SECRET`), so the instance cannot be called around CloudFront.
  - CloudFront's origin response timeout is 30 seconds by default. Every API call returns in well under that, because jobs run in the background.
  - Restricting callers to the VPS: a WAF IP-set rule on the distribution. Without it, the bearer token is the only gate, since a CloudFront URL is reachable by anyone.
  - Webhooks go the other way (instance to orchestrator) and are not affected.
  - The desktop (port 6080) is not put behind CloudFront. Reach it with SSM port forwarding:
    `aws ssm start-session --target i-... --document-name AWS-StartPortForwardingSession --parameters portNumber=6080,localPortNumber=6080`
- **Instance profile:** SSM core, pull from ECR, read the secrets, write to the output bucket, and `ec2:StopInstances` on itself.
- **Keys:** read from Secrets Manager or SSM Parameter Store at boot into the container environment. Not in the image, not in the reference document.

### 13.4 Lifecycle, driven by the orchestrator

```
request arrives at the orchestrator  -> insert docgen_jobs (state = queued)
dispatcher: no job running?          -> take the oldest queued job, state = starting_instance
ec2:StartInstances                   -> wait for "running"
GET /v1/health until ready = true    -> give up after 5 minutes, re-queue, alert
POST /v1/documentaries               -> 202, store job_id, state = running
webhooks update the row              -> stage, seq, progress, message, last_heartbeat_at
terminal event                       -> store outputs or error
queue empty?                         -> ec2:StopInstances; otherwise POST the next job
```

- The orchestrator needs an IAM identity limited to `ec2:StartInstances`, `ec2:StopInstances` and `ec2:DescribeInstances` on this one instance.
- **Dead-man stop on the instance:** if no job is running, no `keep-awake` tag is set, and no authenticated API call has arrived for 20 minutes, the instance stops itself. This covers an orchestrator crash.
- **Uptime alarm:** a CloudWatch alarm when the instance has been running for more than 6 hours. Left running all month it costs about 127 USD.
- **Maintenance:** set the `keep-awake` tag, start the instance, open the desktop through SSM, remove the tag when done.
- **Start failures:** if the zone has no `c9g.xlarge` capacity, `StartInstances` fails. Retry with backoff and keep the job `queued`.
- **Disk:** each run folder is about 1.5 GB. Delete it after outputs are uploaded and the job is terminal, keeping the last three for debugging.

A lesson from your own account applies here: two stopped instances from the old doc-finalize mechanism were found still billing for their volumes months later. This instance is meant to stay stopped between jobs, so its volume cost (about 8 USD a month for 100 GB of gp3 at the rate I remember) is expected. Tag it clearly so it is not mistaken for an orphan, and consider terminating the old `documentary-basic-finalize` instance once you have confirmed nothing uses it; it is x86 and cannot run this image.

### 13.5 Alternative considered: the instance pulls work

The instance could call the orchestrator for its next job instead of being called. That needs no inbound port, no Elastic IP and no TLS certificate on the instance. You chose to call the instance from the orchestrator, which this document follows; the pull design is the fallback if exposing port 443 becomes a problem.

### 13.6 Later: Approach 2 (ECS task per documentary)

Not being built now. The same ECR image can later run as one Fargate ARM task per job (about 0.158 USD per hour for 4 vCPU and 8 GB), with EFS for the Storyblocks token. The API contract in section 4 stays the same, so the orchestrator would only change how it starts compute. The open risks are browser shared memory on Fargate, two tasks sharing one Storyblocks token, and losing desktop edits between tasks.
