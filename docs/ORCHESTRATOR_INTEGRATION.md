# Connecting the orchestrator to doc-gen

This is the guide for the QM Orchestrator on the VPS. It covers everything needed to queue a documentary request, start the EC2 instance, send the job, follow it to the end and collect the files. It describes the service as deployed on 2026-10-11; the reasoning behind the design is in `DOCKER_SERVICE_DESIGN.md`.

## 1. What you are talking to

| Item | Value |
|---|---|
| API base URL | `https://doc-gen.ai-storystudio.com` |
| Transport | HTTPS only, through CloudFront. Plain HTTP is refused. |
| Authentication | `Authorization: Bearer <DOCGEN_API_TOKEN>` on every call |
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

**AWS permissions** to start and stop the instance. Not created yet: make an IAM user or role for the orchestrator with only this policy.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["ec2:StartInstances", "ec2:StopInstances"],
     "Resource": "arn:aws:ec2:us-east-1:<account-id>:instance/i-0a6c5182dd9377129"},
    {"Effect": "Allow", "Action": "ec2:DescribeInstances", "Resource": "*"}
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
8. Finish                   on job.succeeded: download or record the outputs. On job.failed: store the error.
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
- `storyblocks_mcp` can be `connected`, `needs_login`, `not_configured` or `unknown`. Anything other than `connected` needs a person to sign in on the instance desktop; the orchestrator cannot fix it. As of 2026-10-11 the sign-in has not been done, so `ready` is false.
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
              "animated_stills": 10, "dramatised_character": true, "allow_graphic_archive": false},
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
| `review_mode` | `checkpoints` (default) or `auto` | `auto` runs to the end without pausing |
| `limits.max_runtime_minutes` | 30 to 300, default 150 | Counted from acceptance, including time spent waiting at checkpoints. The job fails with `timeout` when it is exceeded. |
| `limits.max_llm_turns` | 20 to 2,000, default 400 | |
| `output.prefix` | default `docgen/<request_id>/` | Key prefix in the output bucket, when one is configured |
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

## 7. Collecting the outputs

On `job.succeeded`, `status.outputs` lists the finished files:

```json
[
  {"kind": "long_video", "path": "out/the-treaty-of-versailles.mp4", "bytes": 184220331},
  {"kind": "short", "path": "shorts/a_spark/out/a_spark.mp4", "bytes": 21877002},
  {"kind": "thumbnail", "path": "thumb/thumbnail.jpg", "bytes": 412004},
  {"kind": "metadata", "path": "out/youtube_metadata.md", "bytes": 6120},
  {"kind": "credits", "path": "out/credits.md", "bytes": 2210}
]
```

The `kind` names are written by the producing run and are not a fixed list; `path` is always relative to the job's run folder.

- **No output bucket is configured yet.** The files stay on the instance, and the job carries the warning "Outputs were not uploaded". Download each one with `GET /v1/documentaries/{job_id}/files/<path>` **before stopping the instance**. Run folders survive a stop, so a missed download can be recovered by starting the instance again.
- When a bucket is configured, each entry also has `bucket` and `key`, and the orchestrator can read the files from there instead.

## 8. Tables on the VPS

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

## 9. Trying it by hand

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

## 10. Not in place yet

- **Storyblocks sign-in** on the instance desktop. Until it is done, health reports `ready: false` and only requests with `visuals.stock: false` are accepted.
- **A real job has not been run on the instance.** The API, webhooks, checkpoints and cancel were tested with a mock runner; the production path with Claude has not been exercised end to end.
- **No restriction on who can call the URL.** The bearer token is the only gate. A firewall rule limiting callers to the VPS address can be added once that address is known.
- **The orchestrator's IAM identity** (section 2) has not been created.
- **Output bucket** not chosen; outputs are downloaded through the API for now.
- **Restart behaviour of the CloudFront connection** after a stop and start has not been tested.
