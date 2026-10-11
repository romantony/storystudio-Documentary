# Connecting the orchestrator to doc-gen

This is the guide for the QM Orchestrator on the VPS. It covers everything needed to queue a documentary request, start the EC2 instance, send the job, follow it to the end and collect the files. It describes the service as deployed on 2026-10-11; the reasoning behind the design is in `DOCKER_SERVICE_DESIGN.md`.

## 1. What you are talking to

| Item | Value |
|---|---|
| API base URL | `https://doc-gen.ai-storystudio.com` |
| Transport | HTTPS only, through CloudFront. Plain HTTP is refused. |
| Authentication | `Authorization: Bearer <DOCGEN_API_TOKEN>` on every call |
| Allowed caller | Only `129.121.78.38` (the orchestrator on Bluehost), over IPv4. Every other address gets 403 from CloudFront. |
| EC2 instance | `i-0a6c5182dd9377129`, `c9g.xlarge`, region `us-east-1` |
| Concurrency | One job at a time. The orchestrator owns the queue. |
| Instance state between jobs | Stopped. The orchestrator starts it for a job and stops it afterwards. |

While the instance is stopped or booting, the URL answers with a CloudFront error (502 or 504). That is expected; treat it as "not up yet".

## 2. Secrets and permissions the orchestrator needs

**Two secrets**, both stored in AWS Systems Manager Parameter Store (us-east-1) as encrypted parameters. Copy their values into the orchestrator's own secret store.

| Parameter | Used for |
|---|---|
| `/docgen/DOCGEN_API_TOKEN` | The bearer token for every API call |
| `/docgen/DOCGEN_CALLBACK_SECRET` | Verifying the signature on webhooks (section 6) |

```
aws ssm get-parameter --name /docgen/DOCGEN_API_TOKEN --with-decryption --query Parameter.Value --output text
```

**AWS permissions** to start and stop the instance. The IAM user `docgen-orchestrator` exists with only the policy below. It has no access key yet: create one in the IAM console (user `docgen-orchestrator`, Security credentials, Create access key) and put it in the orchestrator's configuration.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["ec2:StartInstances", "ec2:StopInstances"],
     "Resource": "arn:aws:ec2:us-east-1:<account-id>:instance/i-0a6c5182dd9377129"},
    {"Effect": "Allow", "Action": ["ec2:DescribeInstances", "ec2:DescribeInstanceStatus"], "Resource": "*"}
  ]
}
```

## 3. The life of one job

```
1. Request arrives          insert a row in docgen_jobs, state = queued
2. Dispatcher               if no job is running or awaiting input, take the oldest queued row
3. Start the instance       ec2:StartInstances, state = starting_instance
4. Wait for the API         GET /v1/health every 10 s until HTTP 200 and "ready": true (give up after 5 minutes)
5. Send the job             POST /v1/documentaries -> 202, store job_id, state = running
6. Follow it                webhooks update the row; poll GET /v1/documentaries/{job_id} as a fallback
7. Checkpoints              on checkpoint.awaiting_input, show the files to a reviewer, then POST .../respond
8. Finish                   on job.succeeded: store the output URLs. On job.failed: store the error.
9. Next job or stop         if the queue is empty, ec2:StopInstances; otherwise go to step 5
```

Rules that follow from how the service works:

- **Do not stop the instance while a job is `running`.** The process is lost, and on the next start the job is reported as `failed` with code `internal` and `retryable: true`.
- **Stopping during `awaiting_input` is allowed.** The job and its Claude session are on disk. Start the instance again before calling `respond`. This path has been tested with the mock runner only, not yet with a real run.
- **The instance protects itself.** If no job is running or awaiting input and no authenticated API call has arrived for 20 minutes, it stops itself. A job waiting at a checkpoint counts as busy, so the instance stays up (and keeps billing) until someone responds or the orchestrator stops it.
- **Starting can fail** when the zone has no capacity for this instance type. Retry with backoff and leave the job `queued`.

## 4. Endpoints

All paths are under `https://doc-gen.ai-storystudio.com`. All need the bearer token. Bodies are JSON.

| Method and path | Purpose | Success |
|---|---|---|
| `GET /v1/health` | Is the service up and able to take a job | 200 |
| `POST /v1/documentaries` | Start a job | 202 (new), 200 (same `request_id` sent before) |
| `GET /v1/documentaries` | All jobs known to the instance | 200 |
| `GET /v1/documentaries/{job_id}` | Current status object | 200 |
| `GET /v1/documentaries/{job_id}/events?after_seq=N` | Events with `seq` greater than N, for catching up after missed webhooks | 200 |
| `POST /v1/documentaries/{job_id}/respond` | Answer a checkpoint | 200 |
| `POST /v1/documentaries/{job_id}/cancel` | Stop a job | 200 |
| `GET /v1/documentaries/{job_id}/files/{path}` | Download a file from the job's run folder | 200 |

### Errors

Every error has the same shape:

```json
{"error": {"code": "busy", "current_job_id": "dg_3f9a1c2b7d4e"}}
```

| HTTP | `code` | Meaning | What to do |
|---|---|---|---|
| 400 | `invalid_field` | Payload failed validation; `field` and `message` say where | Fix the request; do not retry as is |
| 401 | `unauthorized` | Missing or wrong bearer token | Check the token |
| 403 | `forbidden` | The call did not come through CloudFront | Use the base URL above |
| 403 | (CloudFront page, not JSON) | The caller's address is not the allowed one | Call from the orchestrator host; see section 1 |
| 404 | `not_found` | Unknown job or file | |
| 409 | `busy` | Another job is running or awaiting input; `current_job_id` names it | Keep the request queued |
| 409 | `not_awaiting_input` | `respond` called when the job is not paused | Re-read the status |
| 409 | `wrong_checkpoint` | `checkpoint_id` does not match; `expected` gives the right one | Re-read the status |
| 503 | `not_ready` | A key is missing or Storyblocks is not signed in; `checks` shows which | Alert a person |
| 502, 504 | (CloudFront page, not JSON) | Instance stopped, booting, or slow | Retry |

### Health

```json
{
  "ready": false,
  "image": "docgen:7577d07",
  "runner": "claude",
  "busy": false,
  "current_job_id": null,
  "checks": {"storyblocks_mcp": "not_configured", "anthropic": "set", "gemini": "set", "runpod": "set",
             "comfy": "set", "callback_secret": "set", "disk_free_gb": 95.9},
  "uptime_seconds": 1555,
  "idle_seconds": 0
}
```

- `ready` is true when every key is `set`, at least 5 GB of disk is free, and `storyblocks_mcp` is `connected`.
- `storyblocks_mcp` can be `connected`, `needs_login`, `not_configured` or `unknown`. Anything other than `connected` needs a person to sign in on the instance desktop; the orchestrator cannot fix it. The sign-in was done on 2026-10-11 and survives a stop and start; the steps for repeating it are in `INSTANCE_ACCESS.md`.
- A request with `visuals.stock: false` is accepted even when Storyblocks is not connected.
- The Storyblocks check can take longer than CloudFront's 30 second limit the first time after a boot. A 504 on the first health call is not a failure; call again.
- The checks confirm that keys are present, not that they are valid. An invalid key shows up as a failed job.

## 5. Starting a job

`POST /v1/documentaries`

```json
{
  "request_id": "qm-2026-10-12-0001",
  "topic": "The Treaty of Versailles",
  "synopsis": "How the 1919 peace settlement was negotiated, what it imposed on Germany, and why it failed to hold.",
  "series": {
    "name": "Wars That Shaped the World",
    "episode": 4,
    "previous_episode_title": "The War That Ended Slavery",
    "previous_episode_url": "https://youtu.be/...",
    "next_episode_title": "The Second World War",
    "playlist_url": "https://www.youtube.com/playlist?list=..."
  },
  "long":   {"enabled": true, "target_seconds": 480, "narrator_voice": "Charon"},
  "shorts": {"count": 3, "angles": ["spark", "myth", "legacy"]},
  "visuals": {"archive": true, "stock": true, "image_gen": true, "talking_clips": 3,
              "animated_stills": 10, "dramatised_character": true, "allow_graphic_archive": false,
              "text_overlays": true},
  "review_mode": "checkpoints",
  "model": "claude-sonnet-5-5",
  "limits": {"max_runtime_minutes": 150, "max_llm_turns": 400},
  "output": {"prefix": "docgen/qm-2026-10-12-0001/"},
  "callback": {"url": "https://<orchestrator-host>/webhooks/docgen"}
}
```

Only `request_id`, `topic`, `synopsis` and `callback.url` are required. Everything else has the default shown above.

| Field | Type and limits | Notes |
|---|---|---|
| `request_id` | string, 1 to 64 characters, letters, digits, `_` and `-` | The orchestrator's own id, and the idempotency key |
| `topic` | string, up to 200 characters | |
| `synopsis` | string, up to 1,000 characters | The angle and scope of the episode |
| `series.*` | all optional | Used in the sign-off, end card and description. Missing URLs become placeholders flagged in `warnings`. |
| `long.target_seconds` | 240 to 720, default 480 | |
| `long.narrator_voice` | default `Charon` | A Gemini TTS voice name |
| `shorts.count` | 0 to 3, default 3 | |
| `shorts.angles` | any of `spark`, `myth`, `legacy` | |
| `visuals.talking_clips` | 0 to 5, default 3 | Each is a paid generation |
| `visuals.animated_stills` | 0 to 15, default 10 | Each is a paid generation |
| `visuals.allow_graphic_archive` | default false | When false, photographs showing the dead are not used |
| `visuals.text_overlays` | default true | Animated on-screen text (names, dates, numbers, quotations). Set false for videos with captions only. See section 7. |
| `review_mode` | `checkpoints` (default) or `auto` | `auto` runs to the end without pausing |
| `limits.max_runtime_minutes` | 30 to 300, default 150 | Counted from acceptance, including time spent waiting at checkpoints. The job fails with `timeout` when it is exceeded. |
| `limits.max_llm_turns` | 20 to 2,000, default 400 | |
| `output.prefix` | default `docgen/<request_id>/` | Key prefix in the output bucket, and so the path part of the public URLs. Must start with `docgen/`; the instance may not write elsewhere in the bucket. |
| `callback.url` | must start with `https://` | Where webhooks are sent |

Response, 202:

```json
{"job_id": "dg_3f9a1c2b7d4e", "request_id": "qm-2026-10-12-0001", "state": "running",
 "status_url": "/v1/documentaries/dg_3f9a1c2b7d4e"}
```

**Idempotency.** Sending a `request_id` the instance has already seen returns 200 with the existing job and starts nothing, whatever state that job is in. It is safe to repeat the POST after a network error. To run a failed request again, send it with a new `request_id` (for example a `-r2` suffix).

## 6. Following a job

### The status object

Returned by `GET /v1/documentaries/{job_id}` and carried inside every webhook.

```json
{
  "job_id": "dg_3f9a1c2b7d4e",
  "request_id": "qm-2026-10-12-0001",
  "seq": 14,
  "state": "running",
  "stage": "build_long",
  "stages_done": ["setup", "script", "assets_queued", "assets_ready", "narration", "timings"],
  "progress": 0.52,
  "message": "Assembling the long video: 29 scenes.",
  "next_steps": ["Build the three Shorts"],
  "awaiting": null,
  "warnings": ["No audio has been listened to"],
  "outputs": [],
  "costs": {"infinitetalk_clips": 3, "ltx_clips": 10},
  "error": null,
  "created_at": "2026-10-12T09:00:04Z",
  "stage_started_at": "2026-10-12T09:41:10Z",
  "updated_at": "2026-10-12T09:41:10Z"
}
```

- `state`: `running`, `awaiting_input`, `succeeded`, `failed` or `cancelled`. The last three are final.
- `stage`, in order: `setup`, `script`, `assets_queued`, `assets_ready`, `narration`, `timings`, `build_long`, `build_shorts`, `metadata`, `upload_outputs`, `done`.
- `progress`: 0 to 1, a weighted count of finished stages. It is 1.0 only when the job has succeeded.
- `message`, `next_steps`, `warnings`: plain text written for a person. Show `warnings` to whoever publishes the video.
- `costs`: counts of paid generations, not money.

### Webhooks

The instance sends `POST {callback.url}` for every change.

```
Content-Type: application/json
X-Docgen-Event: stage.started
X-Docgen-Delivery: 5b0c6e0e-...            (unique per delivery attempt)
X-Docgen-Signature: sha256=<hex HMAC-SHA256 of the raw body, keyed with DOCGEN_CALLBACK_SECRET>
```

```json
{
  "event": "stage.started",
  "job_id": "dg_3f9a1c2b7d4e",
  "request_id": "qm-2026-10-12-0001",
  "seq": 14,
  "sent_at": "2026-10-12T09:41:10Z",
  "status": { "...the status object above..." }
}
```

| Event | When |
|---|---|
| `job.accepted` | The job was created |
| `stage.started`, `stage.completed` | The stage changed. Both are sent at the moment of the change, so `status.stage` in both already names the new stage. |
| `status.updated` | Message, warnings, outputs or costs changed within a stage; also sent when a checkpoint answer is accepted |
| `checkpoint.awaiting_input` | The job paused; `status.awaiting` says what to review |
| `job.heartbeat` | Every 60 seconds while the job process runs. Carries the `seq` of the last real event. |
| `job.succeeded`, `job.failed`, `job.cancelled` | Final |

How the receiving endpoint should behave:

1. **Verify the signature** over the raw request body before parsing it, with a constant-time comparison. Reject with 401 if it does not match.
2. **Answer 2xx within 10 seconds.** Do the work after answering.
3. **Expect repeats and reordering.** Delivery is at least once. A failed delivery is retried after 5, 15, 60, 180 and 300 seconds, then dropped. Heartbeats are never retried.
4. **Apply an event only if its `seq` is greater than the stored `seq`.** The `status` inside is a full snapshot, so the newest event alone is enough to update the row. For heartbeats, only update `last_heartbeat_at`.
5. **Catch up when a gap appears** or a webhook is overdue: call `GET .../events?after_seq=<stored seq>` and apply what comes back. Heartbeats are not in that list.
6. **Treat silence as a problem.** No heartbeat or event for 5 minutes while the row says `running` means the instance or the job is in trouble: poll the status, and check the instance state.

Signature check in Python:

```python
import hashlib, hmac

def valid(raw_body: bytes, header: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header or "", expected)
```

### Checkpoints

With `review_mode: "checkpoints"` the job pauses twice.

| `checkpoint_id` | When | What the reviewer looks at |
|---|---|---|
| `cp_script` | Scripts written, nothing paid generated yet | The scripts listed in `awaiting.review_files` |
| `cp_final` | Everything built | The videos, the metadata and the `warnings` list |

`status.awaiting` while paused:

```json
{"checkpoint_id": "cp_script", "question": "Approve the scripts, or send changes?",
 "review_files": ["script/script.json", "shorts/a_spark/script.json"]}
```

Fetch each file with `GET /v1/documentaries/{job_id}/files/<path>`, then answer:

`POST /v1/documentaries/{job_id}/respond`

```json
{"checkpoint_id": "cp_script", "action": "revise", "instructions": "Shorten the cold open and drop scene 12."}
```

- `action`: `approve` continues, `revise` applies `instructions` and raises the same checkpoint again, `abort` ends the job as `cancelled`.
- The response is the status object, now `running` (or `cancelled`).

### Failures

`status.error` on a failed job:

```json
{"code": "timeout", "stage": "build_long", "message": "max_runtime_minutes exceeded", "retryable": true}
```

| `code` | Meaning | Retry |
|---|---|---|
| `timeout` | Ran past `limits.max_runtime_minutes` | Yes, with a new `request_id` |
| `llm_error` | The Claude process exited abnormally | Yes |
| `internal` | The server restarted mid-job, or the process ended without a result | Yes |
| `generation_failed` | A generation step failed and could not be replaced | Look at `message` first |
| `storyblocks_auth` | Storyblocks sign-in is missing or expired | No; a person must sign in |

Use `retryable` to decide, cap attempts (two is reasonable), and remember that a retry starts from nothing and pays for generation again.

## 7. Text overlays

The service can put animated text over a scene: a person's name, a place and date, a chapter heading, a quotation or a number. The text is rendered by Remotion inside the instance and drawn under the captions. Nothing extra has to be installed or called by the orchestrator.

**What the orchestrator controls**

- `visuals.text_overlays` in the request: `true` (the default) lets the producing run add overlays where they help; `false` gives a video with captions only.
- There is no field for specifying individual overlays in the request. Which scenes get one is decided when the script is written. The way to steer it is the script checkpoint, below.

**What an overlay looks like in the script**

Overlays are part of the script files a reviewer sees at `cp_script` (`script/script.json` for the long video, `shorts/<id>/script.json` for each Short). A scene or segment that has one carries an `overlay` entry, a single object or a list:

```json
{"n": 6, "narration": "Lincoln was a self-taught lawyer...", "asset": "inaug",
 "overlay": {"type": "lower_third", "title": "Abraham Lincoln", "subtitle": "16th President of the United States"}}
```

| `type` | Fields | Shows |
|---|---|---|
| `lower_third` | `title`, optional `subtitle` | A person's name and role |
| `stamp` | `text` | Place and date, typed out |
| `title` | `title`, optional `subtitle` | A chapter heading |
| `quote` | `text`, optional `attribution` | A quotation and its source |
| `stat` | `value`, optional `label` | A number that counts up, with a label |

Optional on any of them: `at` (seconds after the scene starts, default 0.8), `seconds` (how long it stays, default 4.5, shortened to fit the scene) and `zone` (`top` or `bottom`; normally left out so the builder avoids the captions).

**Reviewing and changing overlays**

- If the orchestrator shows scripts to a reviewer, it should display the `overlay` text along with the narration. Overlay text is on screen in the final video and needs the same proofreading.
- To change them, answer `cp_script` with `revise` and say what is wanted in `instructions`, for example: "Remove the overlay from scene 9. Add a lower third naming Ulysses S. Grant in scene 14. No quote overlays." The run applies the changes and raises the checkpoint again.
- A scene with a `quote` or `stat` overlay is always flagged `verify` in the script, so it appears on the fact-check list.

**Effect on a job**

- No generation cost: overlays do not appear in `costs`.
- Time: about 10 seconds of rendering per overlay on the instance, so a typical episode gains a minute or two.
- The instructions given to the producing run ask for restraint: roughly one scene in four at most, and one or two per Short.

## 8. Collecting the outputs

Finished outputs are uploaded to S3 and served through the CDN. On `job.succeeded`, every entry in `status.outputs` carries a public `url`:

```json
[
  {"kind": "long_video", "path": "out/the-treaty-of-versailles.mp4", "bytes": 184220331,
   "bucket": "storystudio-unified-storage-prod", "key": "docgen/qm-2026-10-12-0001/out/the-treaty-of-versailles.mp4",
   "url": "https://cdn-v2.ai-storystudio.com/docgen/qm-2026-10-12-0001/out/the-treaty-of-versailles.mp4"},
  {"kind": "short", "path": "shorts/a_spark/out/a_spark.mp4", "bytes": 21877002,
   "bucket": "storystudio-unified-storage-prod", "key": "docgen/qm-2026-10-12-0001/shorts/a_spark/out/a_spark.mp4",
   "url": "https://cdn-v2.ai-storystudio.com/docgen/qm-2026-10-12-0001/shorts/a_spark/out/a_spark.mp4"},
  {"kind": "thumbnail", "path": "thumb/thumbnail.jpg", "bytes": 412004, "bucket": "...", "key": "...", "url": "..."},
  {"kind": "metadata", "path": "out/youtube_metadata.md", "bytes": 6120, "bucket": "...", "key": "...", "url": "..."}
]
```

| `kind` | What it is | How many |
|---|---|---|
| `long_video` | The 16:9 video | 1 |
| `short` | A 9:16 Short; the Short's id is in the path (`a_spark`, `b_myth`, `c_matters`) | up to 3 |
| `thumbnail` | Thumbnail image for the long video | 1 |
| `metadata` | Title, description, chapters and tags for the long video | 1 |
| `shorts_metadata` | Titles and descriptions for the Shorts | 1 |
| `credits` | Image credits and licences | 1 |

- **URL pattern:** `https://cdn-v2.ai-storystudio.com/<output.prefix><path>`. With the default prefix that is `https://cdn-v2.ai-storystudio.com/docgen/<request_id>/<path>`. Do not build URLs yourself; read `url` from the status, because the file name of the long video is chosen during the job.
- **The URLs are public.** Anyone who has one can open it, with no token, and it works whether the instance is running or stopped. Treat a URL as published the moment the job reports it.
- **Only finished outputs are uploaded.** Scripts, generated images, archive photographs, narration audio and intermediate files stay on the instance and can be fetched with `GET /v1/documentaries/{job_id}/files/<path>` while the instance is running.
- **Store `outputs` in `docgen_jobs.outputs`** when the final event arrives. The orchestrator does not need to download anything before stopping the instance.
- **When an upload fails,** the job still finishes, the affected entry has no `url`, and `warnings` says which file was not uploaded. Fetch that file through the `files` endpoint before stopping the instance.
- **With checkpoints on,** the upload happens before `cp_final`, so the reviewer can open the URLs from `status.outputs` while deciding. An aborted job leaves its uploaded files in the bucket.
- **Disk on the instance:** full run folders are kept for the three most recent finished jobs. Older ones lose their media and working files when a new job starts (their status stays available through the API). A succeeded job is only cleaned up once all its outputs are uploaded.

## 9. Tables on the VPS

```sql
create table docgen_jobs (
  request_id        text primary key,
  job_id            text unique,
  state             text not null default 'queued',  -- queued | starting_instance | running | awaiting_input | succeeded | failed | cancelled
  stage             text,
  seq               integer not null default 0,
  progress          real,
  message           text,
  request           jsonb not null,                  -- the payload sent to the instance
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

`queued` and `starting_instance` exist only in the orchestrator. The instance never reports them.

## 10. Trying it by hand

The API calls below work only from the orchestrator host, because of the address restriction.

```bash
BASE=https://doc-gen.ai-storystudio.com
TOKEN=$(aws ssm get-parameter --name /docgen/DOCGEN_API_TOKEN --with-decryption --query Parameter.Value --output text)

aws ec2 start-instances --instance-ids i-0a6c5182dd9377129
curl -s -H "Authorization: Bearer $TOKEN" $BASE/v1/health                       # repeat until it returns JSON
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d @request.json $BASE/v1/documentaries
curl -s -H "Authorization: Bearer $TOKEN" $BASE/v1/documentaries/dg_xxxxxxxxxxxx
aws ec2 stop-instances --instance-ids i-0a6c5182dd9377129
```

## 11. Not in place yet

- **Overlays have not been produced by a real job.** The rendering and placement are tested with hand-written scripts; how well the producing run chooses and words them is not yet known.
- **A real job has not been run on the instance.** The API, webhooks, checkpoints and cancel were tested with a mock runner; the production path with Claude has not been exercised end to end.
- **The access key** for `docgen-orchestrator` (section 2) has not been created.
- **If the orchestrator's address changes,** edit the list in the CloudFront function `docgen-allow-orchestrator` and publish it; until then every call gets 403.
- **The upload has not been run by a real job on the instance.** A test file uploaded from inside the instance's container was readable through the CDN, and writing outside `docgen/` was refused.
- **A call through the public URL after a stop and start** has not been checked from the orchestrator. On the instance itself the service came back ready after a restart.
