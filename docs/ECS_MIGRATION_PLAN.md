# Moving doc-gen from EC2 to ECS, and starting the Decoded Economy series from the UI

> **Decision, 2026-10-21 (later the same day).** Storyblocks stays on its MCP, which needs a person's browser sign-in, and there is no Storyblocks API key. So **doc-gen stays on the EC2 instance for now, and the move to ECS waits for a Storyblocks API key** (§3 option B); the ECS pieces below (task entry point, task definition) are built and tested but not deployed. The documentary series is **planned outside doc-gen**: doc-gen only researches and generates one episode per request, so the season catalogue and the series UI (§5.4-5.5) are out of scope here. What ships now is an updated image (§2a).

## 2a. What the updated image adds (playbook, "Pipeline changes before 2 Nov")

| Playbook item | In the image |
|---|---|
| Runtime limit 720 → 900 s | `long.target_seconds` up to 1800; `long.format: "documentary"` needs 600+ |
| Beat markers, 15/30-min templates | `prompts/documentary_format.md`, appended for the documentary format only |
| Separate fact-validation pass | `docgen factcheck` (fresh Claude session, WebSearch/WebFetch, claims table) |
| Charts from FRED, BLS, EIA, IMF | `docgen data` (fetchers) and `docgen chart` (Remotion `Chart` template: animated line or bar, source printed, clip + still); built in doc-gen's own Remotion instead of the infographic image, so there is no cross-service call. Needs `FRED_API_KEY` and `EIA_API_KEY` (free) in `/docgen/`, `BLS_API_KEY` optional; IMF needs none. `put-params.py` stores them from the environment. |
| Reference image per person per theme | `series.refs` (person → URL) in the request; the prompt tells the run to use them for portraits, reconstructions and thumbnails |
| Description template | `comment_question`, `watch_next`, source list from the fact check, hook chapters (already) |
| Thumbnails for the long video **and every Short** | Already built (`docgen thumbnail`, 16:9 and 9:16, Nano Banana 2.1 on KIE, exact headline typeset by Remotion, analyst scoring with the 25/25/20/15/10/5 weights, pick at 80+, Short cover frame). The StoryStudio guidelines you pasted match its prompt templates, presets and Shorts layout (headline in the 10–35 % band, hero in the middle); the documentary prompt now also asks for number-led headlines and chooses the preset by theme. |

Not done: updating the About page and banner (not code); the pilot episode.


Written 2026-10-21, revised the same day. Sources: `Decoded Economy — Documentary Series Playbook.md` (the playbook), the infogen port to Fargate (`~/code/storystudio-infographics/docs/ECS_STEP_FUNCTIONS.md`, the template for this one), and the current doc-gen and StoryStudio code.
First episode publishes **2 Nov 2026**; the pilot (History of Money 1, Gate 1) has to be produced before that.

## 1. Where things stand

| Piece | Today | Target |
|---|---|---|
| Runtime | One `c9g.xlarge` EC2 instance (stopped when idle), FastAPI server, one job at a time | Fargate task per run of the Claude session, no server, jobs in parallel |
| Trigger | StoryStudio (Convex) → QM orchestrator on Bluehost → CloudFront → instance. **MCP-created projects only**; the UI is excluded (`docgenRoute`: "not MCP") | StoryStudio UI / API / MCP → Convex action → Step Functions → ECS (the infographic path) |
| State between runs | Instance disk (`/data/runs`, `/data/claude`) | EFS access points `/runs`, `/claude` |
| Review checkpoints | Orchestrator polls the instance, posts `respond` | State machine waits on a task token; the UI answers (as for infographics) |
| Length | `long.target_seconds` 240–720; Convex caps documentary-basic at 12 min | 900 s (15 min) now, 1800 s (30 min) later |
| Storyblocks | OAuth done once in Firefox on the instance desktop | **open problem, section 3** |
| Cost when idle | EC2 stopped, ~$8/month for the 100 GB disk | Zero compute; EFS storage only |

## 2. What is already built (this session, in `~/docgen`, uncommitted, mock-tested)

| Change | Files | Tests |
|---|---|---|
| ECS entry point: starts or resumes a job, follows the Claude run, uploads review files and outputs, sends `SendTaskSuccess/Failure/Heartbeat`, waits for webhooks. Ported from infogen. | `api/task.py`; `server.py`: `HOOKS.task_done()` | `tests/test_task.py` (21 checks) |
| Task definition `docgen-worker` (ARM64, 2 vCPU / 8 GB / 100 GB scratch, EFS `/data/runs` and `/data/claude`, SSM secrets, S3 + CDN env). EFS ids are placeholders. | `deploy/ecs-task-definition.json` | – |
| Documentary format on the request: `long.format: "documentary"`, `long.target_seconds` up to 1800 (documentary needs ≥ 600), `series.theme/part/total_parts/next_episode_url`; default limits 240 min / 800 turns for the format. The default `explainer` format is unchanged. | `api/server.py` | `tests/test_api.py` (27 checks, still pass) |
| Playbook beat templates (15 and 30 min), writing rules, markers (`[CHAPTER]`, `[SHORT: …]`, `[CHART: …]`, `[RECON: …]`, `[ARCHIVE]`, `[STOCK]`), visual mix, ad-safety rule, packaging; appended to the job prompt only for the documentary format. | `prompts/documentary_format.md` | – |
| Research brief → script from the fact sheet → **separate fact-check session** (`python3 -m docgen factcheck [--verify]`) that extracts every claim and checks it against a primary source with WebSearch/WebFetch, writes `review/claims.md`; the producer cuts, hedges or labels; second pass verifies. | `docgen/factcheck.py`, `prompts/factcheck.md` | `tests/test_factcheck.py` |
| Description: hook chapters (already), `comment_question`, `watch_next`, and a **Sources** list from the fact check. | `docgen/metadata.py` | covered in factcheck test only partly |

Not run against a real model: the prompts have never produced an episode. They are a first draft and the pilot is where they get tuned.

## 3. The blocker: Storyblocks on Fargate

The Storyblocks MCP server uses OAuth. Today a person signs in once in Firefox on the instance desktop and Claude Code keeps the tokens in `/data/claude`. A Fargate task has no desktop. The tokens are only files, so there are three ways:

| Option | How | Risk |
|---|---|---|
| **A. Sign in elsewhere, keep the tokens on EFS** (recommended first try) | Mount the `/claude` EFS access point on the existing EC2 instance (or any box), sign in there with `CLAUDE_CONFIG_DIR` pointing at it, tasks read the same folder | Does Claude Code refresh the token headlessly, and survive two tasks refreshing at once? Unknown; needs a spike. Re-sign-in is a manual step every time the refresh token dies (lifetime unknown). |
| B. Storyblocks REST API keys | Replace the MCP calls with a small `docgen stock` command (search, license, download) using the account's API key + HMAC | No OAuth. But needs API access on the Storyblocks plan, which I have not checked, and the prompt changes from MCP tools to a command. |
| C. Keep a small EC2 only for sign-in | A is the same plus an always-available desktop | Only an admin box, not in the job path |

**Spike (half a day, before anything else):** create the EFS, mount it on the current instance, sign in with `CLAUDE_CONFIG_DIR=/mnt/docgen/claude`, run two `docgen-worker` tasks at the same time with `claude mcp list` and one `search_videos`, wait past the access-token lifetime, repeat. If refresh works and the two tasks do not corrupt the token file, take A. If not, ask the user whether the Storyblocks plan includes API keys (B). The health check already reports `storyblocks_mcp`; the task refuses to start a job with stock footage when it is not `connected` (`not_ready`).

Note for the pilot: jobs can run with `visuals.stock: false` until this is settled. The playbook wants Storyblocks for "why it touches your money" and calm verdict b-roll, so this is not optional for the series.

## 4. AWS resources (us-east-1, tag `Purpose=docgen`)

Same shape as infogen; each needs the user's go-ahead (they cost money or create IAM).

| Resource | Name | Notes |
|---|---|---|
| ECS cluster | `docgen` | Fargate only |
| EFS | `docgen-data` + access points `/runs` → `/data/runs`, `/claude` → `/data/claude` (uid/gid 1000) | Mount targets in the two subnets infogen uses; the Claude sessions and `_rubrics` live here |
| Security groups | `docgen-task` (no inbound), `docgen-efs` (NFS 2049 from `docgen-task`, and from the sign-in box for spike A) | |
| Roles | `docgen-task-execution` (ECR pull, logs `/ecs/docgen`, read `/docgen/*` params), `docgen-task` (`s3:PutObject` on `…/docgen/*`, `states:SendTask*`, EFS client mount/write) | Today's `docgen-instance-role` is the model |
| Log group | `/ecs/docgen` | |
| Task definition | `docgen-worker` | From `deploy/ecs-task-definition.json`; fill the EFS ids |
| SSM parameters | `/docgen/*` already exist | The task needs `ANTHROPIC_API_KEY, GEMINI_API_KEY, RUNPOD_API_KEY, COMFY_API_KEY, KIE_API_KEY, DOCGEN_CALLBACK_SECRET`. Not used on ECS: `DOCGEN_API_TOKEN, DOCGEN_ORIGIN_SECRET, VNC_PASSWORD`. The user stores secrets; I cannot write to Parameter Store. |
| Image | ECR `docgen` (exists), CodeBuild `docgen-image` (exists) | No Dockerfile change: the task overrides the entry point; the desktop stays in the image for the sign-in box. Rebuild to ship the new code. |
| State machine | `E2E-VideoGenerationPipeline-Docgen` | Copy of the infographic one (`infrastructure/stepfunctions/deploy-infographic-sfn.py`) with cluster/task/SG names changed and Docgen sizes |
| Review lambda | `E2E-docgen-review` | As `E2E-infogen-review`: posts the checkpoint to Convex with the task token |

**Sizing** (to measure on the pilot, not guessed): the start task (research, fact check, script) is mostly waiting on Claude, so 2 vCPU / 8 GB. The task after `cp_script` generates assets and builds a 15-minute video with ffmpeg and Remotion, so start at 8 vCPU / 16 GB, and 16 / 32 for 30-minute specials (infogen's large task is about $0.64/h). Expect 1.5–3 h per 15-minute episode; `limits.max_runtime_minutes` (240 for the format) counts per task, not the wait at a checkpoint.
**Cost shape:** the pilot will show the real figure; Fargate for one 15-minute episode is a few dollars, the Claude turns and the GPU generations (Wan, LTX, Qwen) are the larger part, as today.

## 5. StoryStudio changes (separate repo, `~/storystudio-unified`; not started)

Modelled on `backend/convex/e2e/infographic.ts` (7 commits of precedent). File-level plan:

1. **`convex/e2e/docgen.ts`**: `startDocgenPipeline` (owner), `…ForUser` (server side), `startDocgenForProject` (create_project / MCP), `recordReviewFromLambda`, `answerDocgenReview`, `handleDocgenWebhook` (verifies `X-Docgen-Signature`), and `applyDocgenOutputs` which **reuses** `lib/docgen.ts` (`parseDocgenMetadata`, `parseDocgenShortsMetadata`, `buildIntakeFromMetadata`, `classifySynopsis`). Env: `E2E_STEP_FUNCTION_DOCGEN_ARN`, `DOCGEN_CALLBACK_SECRET`.
2. **`convex/http.ts`**: `/api/pipeline/docgen/review` and `/webhook`. **`e2e/status.ts`**: completion hook calls `applyDocgenOutputs`.
3. **Routing** (`lib/orchestratorRouting.ts`): `docgenRoute` stops saying "not MCP"; with `QM_DOCGEN_MODE=live` the UI and MCP both start the state machine. Raise `DOCGEN_MAX_TARGET_MINUTES` from 12 to 15, then 30 (this is the playbook's first blocker: it removes the premium-tier detour). `targetSecondsFromMinutes` clamps to the new range and sends `long.format: "documentary"` for series episodes.
4. **UI**: a **"Documentary series"** card in `ProjectTypeSelector.tsx` (like the infographic card) opening a form: theme, part, title, synopsis, length 15 / 30 min, narrator voice, Shorts count, review mode, thumbnail style. Fields map one-to-one to the doc-gen request.
5. **Season catalogue**: the playbook's 23 episodes and 3 specials (title, synopsis, theme, part, duration) as `shared/decodedEconomySeason1.ts`. The form gets an "Episodes" picker that fills it in, and each start sets `series.previous_episode_title`, `next_episode_title`, `part`, `total_parts` from the catalogue. This is what makes "start it via UI" one click per episode. The release calendar stays out of the code (dates are assumptions in the playbook).
6. **Review screen**: the existing infographic checkpoint UI, plus `review/claims.md` listed first for `cp_script`.
7. **Retire** the orchestrator's doc-gen outbox path (`orchestrator/docgen.ts`, `postProcessDocgen.ts`) after cutover, not before.

## 6. Playbook checklist, item by item

| Playbook item ("Pipeline changes before 2 Nov") | Status | Where |
|---|---|---|
| Raise runtime limit 720 → ≥ 900 s | doc-gen side **done** (≤ 1800); StoryStudio cap not yet | §2, §5.3 |
| Beat markers and 15/30-min templates in the script prompt | **done**, untested on a real run | `prompts/documentary_format.md` |
| Separate fact-validation pass with claims table | **done**, mock-tested; web-search quality unknown | `docgen/factcheck.py` |
| Description template (hook chapters, sources, comment question, watch next) | **done** (`metadata.py`); the one-line identity is in the prompt | §2 |
| Code-generated charts from FRED, BLS, EIA, IMF | **not started** | Phase 3 below |
| Reference image per real person per theme | **not started** | Phase 3 below |
| Update About page and banner | not code; the user | – |
| Produce History of Money 1 as the pilot | **blocked** on the spike and the cutover | Phase 4 |

**Charts (design choice for you).** The playbook says "into the infographic Docker image". The two images do not talk to each other, so that would mean a cross-service call per chart scene. Recommended instead: add a `docgen data` command (FRED, BLS, EIA, IMF fetchers; keys `FRED_API_KEY`, `EIA_API_KEY`, `BLS_API_KEY` are free to register, IMF needs none) and copy infogen's `bar_chart` / line / map Remotion templates into doc-gen's Remotion project, which already renders overlays. The script marker `[CHART: dataset]` then becomes a scene whose clip is rendered in the same container, with the source printed on the chart and added to the description.
**Reference images.** Store at `s3://…/docgen/series/<theme>/refs/<person>.png`, pass them as `series.refs` (name → URL) so every part of a theme uses the same likeness through Qwen-Edit.

## 7. Phases

| Phase | Work | Needs | Gate |
|---|---|---|---|
| 0 (today) | Review this plan; answer the decisions in §9; commit and push the docgen changes | you | – |
| 1 | **Spike Storyblocks auth** (§3). Create EFS, SGs, roles, log group, cluster (§4) | go-ahead for AWS resources | Token refresh works headless, or option B chosen |
| 2 | Rebuild image (CodeBuild), register `docgen-worker`, run a **mock** task by hand (`DOCGEN_RUNNER=mock`, then one real `explainer` run with `review_mode: auto`) | Phase 1 | A real 8-minute run succeeds on Fargate with outputs on the CDN |
| 3 | State machine + review lambda; Convex `e2e/docgen.ts`, routes, form, catalogue (§5); charts and reference images (§6) in parallel | Phase 2 | A project started from the UI reaches `cp_script` and `cp_final` |
| 4 | **Pilot: History of Money 1**, 15 min, checkpoints on, listen to the audio, read `claims.md`, tune the prompts | Phase 3; ~2 days wall-clock | Playbook Gate 1 |
| 5 | Cutover: `QM_DOCGEN_MODE=live` routes UI and MCP to the state machine; keep the EC2 stopped for a week as rollback; then remove the instance, CloudFront distribution, VPC origin and the Bluehost route | Phase 4 passed | Two more episodes without a manual fix |

Dates: if the spike passes on 22 Oct, Phases 2–3 fit by about 28 Oct and the pilot lands 29–30 Oct, which leaves a margin of a few days for 2 Nov. If the spike fails and option B is needed, that margin is gone and the pilot should run with `visuals.stock: false` plus archival and generated visuals, or move.

## 8. Risks

- **Storyblocks auth** (§3), the one that can change the design.
- **Claude session on EFS**: `--resume` needs the session file from the previous task. It works for infogen (same mechanism); NFS latency is the only difference.
- **The 15-minute script quality**: 2,200 words, 150–220 cuts, a fact-check loop of up to three rounds. The first runs will be over budget on turns; `max_llm_turns` 800 is a guess.
- **Cold-start time**: each resume pulls the image (large, with Firefox, VS Code and Chrome for Remotion). Fargate caches nothing between tasks; expect 1–2 minutes. Slimming the image (drop VS Code and the desktop for the worker, keep them for a separate `docgen-admin` tag) is a later optimisation.
- **ECR scan** (18 critical / 194 high, ffmpeg and libcjson1 from Ubuntu universe) is unchanged and still open.
- **Public CDN URLs** for review files and finished outputs (open point from 2026-10-12) now apply to every checkpoint as well.
- **Ad safety** for the drug and war themes is prompt-level only. The thumbnail analyst rubric does not check it yet.
- **Concurrency**: parallel tasks share `index.json` (locked) and the thumbnail rubric (locked); the Storyblocks licence call is per item on the account, so two episodes at once double-count nothing but also share the account quota.

## 9. Decisions I need from you

1. **Storyblocks**: run the spike (option A) first, and do you know whether your Storyblocks plan has API keys (option B fallback)?
2. **AWS go-ahead** for the new resources in §4 (EFS, cluster, roles, SGs, state machine, lambda). I will create them with scripts in `deploy/` and show you each command first, as with infogen.
3. **UI shape**: a new project type "Documentary series" (recommended, section 5.4) or extend documentary-premium? The playbook mentions premium as the alternative to raising the cap.
4. **Charts**: build them inside doc-gen's Remotion (recommended) or call the infographic image?
5. **Push**: may I commit and push the docgen changes (the repo is public: they contain no keys)? And start the StoryStudio work in `~/storystudio-unified`, which I have so far only read?
