# docgen

Documentary generator as a service: an Ubuntu desktop image with Claude Code, a config-driven toolkit and a small API.
Design and API contract: `docs/DOCKER_SERVICE_DESIGN.md` (sections 4 and 13).

| Path | What |
|---|---|
| `docgen/` | Toolkit. Run from a run folder: `python3 -m docgen <command>`. Each module's docstring is the format reference. |
| `api/server.py` | FastAPI server: one job at a time, status from `status.json`, signed webhooks, checkpoints. |
| `api/mock_runner.py` | Stand-in for the Claude run; walks the stages without spending anything. |
| `prompts/produce.md` | Instructions for the Claude Code run that produces a documentary. |
| `docs/ORCHESTRATOR_INTEGRATION.md` | How the orchestrator connects: URL, auth, payload, webhooks, checkpoints, outputs. |
| `remotion/`, `docgen/overlay.py` | Animated text overlays (lower third, place/date stamp, title, quote, statistic): Remotion renders a transparent clip, ffmpeg composites it under the captions. Remotion is free for individuals and companies of up to three people; larger companies need a company licence. |
| `Dockerfile`, `deploy/` | Image, supervisord, compose file, systemd units, first-boot setup (`setup-instance.sh`), `.env` from Parameter Store (`fetch-env.sh`), dead-man stop. |
| `buildspec.yml` | CodeBuild (ARM) build that pushes to ECR. |
| `tests/test_api.py` | Contract test against the mock runner. |

## Local test

```bash
python3 -m venv .venv && .venv/bin/pip install fastapi uvicorn pydantic boto3 pillow
.venv/bin/python tests/test_api.py

docker build -t docgen:local .
docker run --rm -e VNC_PASSWORD=changeme -e DOCGEN_API_TOKEN=t -e DOCGEN_CALLBACK_SECRET=s -e DOCGEN_RUNNER=mock \
  -e GEMINI_API_KEY=x -e RUNPOD_API_KEY=x -e COMFY_API_KEY=x --shm-size 1g -p 127.0.0.1:6080:6080 -p 127.0.0.1:8080:8080 docgen:local
# desktop: http://127.0.0.1:6080/vnc.html      API: curl -H "Authorization: Bearer t" http://127.0.0.1:8080/v1/health
```

## First-time setup on the instance (from the desktop terminal)

```bash
claude mcp add --transport http storyblocks https://mcp.storyblocks.com/mcp --scope user
claude          # /mcp -> storyblocks -> Authenticate (Firefox opens)
claude mcp list # storyblocks ... Connected
```

The sign-in is stored under `/data/claude` (`CLAUDE_CONFIG_DIR`), which is on the instance's volume.

## Not yet verified

- The arm64 build (only amd64 has been built locally).
- Storyblocks sign-in inside the container and its survival across restarts.
- A real end-to-end run with `DOCGEN_RUNNER=claude`. Only the mock runner has been exercised through the API.
- `docgen queue`, `tts`, `timings`, `thumb`, `fetch-archive` (download) and `upload` are ports of scripts that ran for three episodes, but the ported versions have not made paid calls yet.

## Also in this repository

| Path | What |
|---|---|
| `docs/` | Service design and API contract, the Shorts plan, the series plan, the to-do list, and the session playbook (API keys removed). |
| `episodes/<slug>/` | The three episodes made so far, text only: scripts, Shorts scripts, YouTube metadata, credits, archive-image records and the per-episode build scripts the toolkit was generalised from. |

Media is not in the repository: no video, audio or images. Generated and downloaded assets stay in the run folders.
