# 3D scenes for docgen (Three.js in Remotion): implementation brief

Status: proposal, nothing built in docgen yet. Written 2026-10-24 after the same feature was built and tested in infogen.

## 1. Goal

Add three 3D scene kinds to docgen so a documentary can show one or two "reveal" moments that stock footage cannot: a ranking where one bar towers (`bars3d`), a journey or places around the world (`globe`), a system whose parts connect (`network3d`). They are rendered by Remotion with Three.js, in software (no GPU), and used the way docgen already uses data charts: a clip plus a last-frame still, referenced from the script as an animated asset.

Camera and timing are designed by **Claude Opus 5.5** (`claude-opus-5-5`), which may never change a number, label or source.

## 2. What exists in infogen (reference implementation)

Repo `github.com/romantony/storystudio-infographics`, commit `12f5741` (pushed to `main`; image built by CodeBuild 2026-10-24). Read these files and port them:

| File | What it is |
|---|---|
| `remotion/src/templates/Three.tsx` | The three templates, camera rig, label projection. About 260 lines. |
| `infogen/scene3d.py` | Spec check (`check`), planner (`ask`, `parse`, `merge`), CLI `scene3d <n>`. |
| `prompts/scene3d.md` | The Opus planner prompt (what it may set, what it may not). |
| `tests/test_scene3d.py` | Spec check and merge tests, planner mocked. |
| `docs/SCENES.md` (section "bars3d, globe, network3d") | The scene JSON, field by field. |

Tested there: stills at 1920x1080 and 1080x1920 for all three, and 6 s videos in 27 to 52 s each on an 8-core x86 machine.

## 3. Differences in docgen that the port must handle

1. **Different Remotion layout.** docgen's `remotion/` has one `Overlay` composition (transparent ProRes clips for text) and a `Chart` composition (opaque, drawn from a data file); infogen has a `Scene` router plus `kit.tsx` (Backdrop, Heading, StageBox, Footnote, `beatAt`, `pop`, `prog`, `useStage`) and `theme.ts` (palette). `Three.tsx` imports all of those. Either port the few helpers it uses into a small `remotion/src/kit3d.tsx`, or restyle to docgen's look (Anton font, the series palette). Do not copy infogen's flat-vector backdrop; give the 3D scenes an opaque background from the theme palette.
2. **Add a `Scene3D` composition** to `Root.tsx` (props: `kind`, `width`, `height`, `fps`, `seconds`, the scene fields, `palette`), with `calculateMetadata` like the others, so one bundle serves 16:9 and 9:16.
3. **Dependencies** (`remotion/package.json`, exact pins, tested together with React 19.3.0 and Remotion 4.0.534): `three@0.186.1`, `@react-three/fiber@9.8.2` (9.6.1 refuses React 19.3), `@remotion/three@4.0.534`, `@types/three@0.186.0`. For `globe` also `d3-geo@3.1.1`, `topojson-client@3.1.0`, `world-atlas@2.0.2` (infogen uses the 110m country file for the texture and 50m for name lookup; `findCountry` lives in infogen's `MapScene.tsx`, copy the alias table and lookup).
4. **WebGL needs software GL.** `overlay.py` runs `npx remotion render` with no GL flag. Three.js needs `--gl=swangle` (infogen's `render.mjs` opens the browser with `chromiumOptions: {gl: 'swangle'}`). Pass `--gl=swangle` for the 3D composition only. Output is opaque H.264 (`--codec=h264 --crf=18`), not ProRes.
5. **Numbers are facts here.** Every 3D bar must come from a data file made by `docgen data` (like `chart`), never typed in. Reuse the `chart` pattern: `docgen scene3d` takes `--data data/<file>.json` for `bars3d`, prints the source on screen, and the data file's `url` goes in the fact sheet for the Fact Checker. A `globe` or `network3d` that states a fact (a route, a connection) is flagged `verify` in the script like `quote` and `stat` overlays.
6. **The instance is arm64 and small** (`c9g.xlarge`, 4 vCPU). Expect roughly 2x infogen's render times (about 1 to 2 minutes for a 6 s scene). Confirm Chrome headless shell with SwiftShader works on arm64 before building anything else (section 6, step 1). If it does not, the fallback is rendering 3D scenes on the infogen ECS task or locally, not a GPU.

## 4. Design

**Command** (mirror `chart.py`): `python3 -m docgen scene3d <id> --kind bars3d|globe|network3d --spec spec.json [--data data/x.json] [--seconds 8] [--size 1920x1080]`. Writes `<assets>/ltx_scene3d_<id>.mp4` (the animation, then it holds the last frame) and `<assets>/scene3d_<id>.png` (last frame), cached by content hash. Script entry, same as charts:

```json
{"n": 14, "asset": "scene3d_<id>", "kind": "animated", "narration": "...", "note": "[3D: bars3d]"}
```
The builder plays the clip then crossfades to the still. Hold the scene at least as long as the narration reads it (8 s minimum).

**Spec** per kind (`bars3d`, `globe`, `network3d`): copy the JSON in infogen's `docs/SCENES.md` unchanged so the two services stay interchangeable. Shared field `camera`: `"orbit"` | `"push_in"` | `"rise"` | `"still"` | `{az, el, dist}` ranges.

**Beats/cues.** infogen reveals each item on a narration word (`cue`). docgen has narration word timings (`build/` timing files from the TTS step); use the same lookup the overlays use for `at`, else spread evenly. If docgen has no word timings for a scene at render time, accept `at` seconds only.

**Opus planner.** Port `scene3d.py` (`check`, `merge`, `parse`) and `prompts/scene3d.md`. `python3 -m docgen scene3d <id> --plan --narration "<text>"` (or `--scene <n>` reading `script/script.json`) sends the narration and the spec to `claude -p --model claude-opus-5-5 --max-turns 2 --allowedTools ""` and merges back only: `camera`, `focus`, `spin`, and per item `cue`, `at`, `color`, `highlight`. Lists must keep their length; anything else is ignored, and an invalid result aborts without writing. Model override env: `DOCGEN_ANIM_MODEL`. docgen already runs Claude sessions with an API key on the instance; this is one more short call (cost: a few cents at most).

**Prompting the producer.** Add a short section to `prompts/produce.md` and `documentary_format.md`: 3D scenes are rare (at most one per five minutes), used for the one moment the verdict or origin hangs on; `[3D: bars3d|globe|network3d]` marker in `note`; run `docgen scene3d` then the planner; charts stay the default for data. Never use a 3D bar chart where a line chart over time is the honest picture.

## 5. Files to add or change

- `remotion/package.json`, `package-lock.json`: dependencies above.
- `remotion/src/Scene3D.tsx` (port of `Three.tsx` plus the helpers), `remotion/src/Root.tsx` (new composition).
- `docgen/scene3d.py` (command, render, spec check, planner), `docgen/__main__.py` (register `scene3d`).
- `prompts/scene3d.md`, `prompts/produce.md`, `prompts/documentary_format.md`.
- `docs/ORCHESTRATOR_INTEGRATION.md`: one paragraph in section 7 noting 3D scenes exist, are not requestable per scene, and are steered at `cp_script` like overlays.
- `tests/test_scene3d.py` (copy infogen's; add a render smoke test that is skipped when Chrome is missing).
- `Dockerfile`: nothing new expected (Remotion's browser is already ensured); confirm `npm ci` picks up the new packages. Delete `remotion/bundle` after changing templates so it is rebuilt.

## 6. Steps

1. **Feasibility on the instance (arm64).** Start the instance, run a 90-frame `bars3d` still and clip with `--gl=swangle`, record the time and check the picture. Go no further if it fails.
2. Port the templates, add the `Scene3D` composition, render stills in 16:9 and 9:16 for all three kinds and look at them (infogen needed several framing fixes: camera distance fitted to the frame width for 9:16, a heading band at the top, flat layout for the network).
3. `docgen scene3d` command with caching and the data-file requirement for `bars3d`.
4. Planner and tests (mocked). Then one real Opus call on a sample scene.
5. Producer prompts, orchestrator doc paragraph.
6. Commit and push as separate commands, run CodeBuild `docgen-image` (about 3 min), start the instance, health check, render one of each kind from inside the container, stop the instance. Ask before starting the instance or running paid steps.

## 7. Acceptance

- Each kind renders at 1920x1080 and 1080x1920 without a GPU; times recorded in this file.
- A `bars3d` cannot be made without a data file; its source is on screen and in the fact sheet.
- Planner output with a bad camera, a wrong list length, or an attempt to change a value is rejected or ignored (tests).
- The long builder and the Shorts builder both play a `scene3d_` asset like a chart asset.
- No change to scenes that do not use 3D.

## 8. Known issues carried over from infogen

- Labels are HTML laid over the canvas, positioned by projecting 3D points, so they do not depth-sort with the 3D objects; on a network, nodes can overlap and hide a label at some camera angles.
- Three.js prints a harmless "THREE.Clock deprecated" warning from react-three-fiber.
- infogen's `render.mjs` fails on PNG stills (passes `jpegQuality` to a non-JPEG render). Pre-existing there; use `remotion still` for stills.
- Real Opus planning has not been run end to end in infogen yet (only mocked).
