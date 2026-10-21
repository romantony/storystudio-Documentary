
## Documentary format (this request has `long.format: "documentary"`)

This job follows the Decoded Economy series playbook. Everything above still applies except where this section says otherwise: the story structure below replaces the "structure that has worked" paragraph, the research and fact-check stages below are added, and the length is `long.target_seconds` (900 for a 15-minute episode, 1800 for a 30-minute one). Read `series` in `request.json`: `theme`, `part`, `total_parts`, `name`, and the previous and next episode fields. The episode is one part of a mini-season on that theme, told through its economic impact.

### Words and scenes

About 150 words per minute: roughly 2,200 words of narration for 900 s and 4,500 for 1,800 s. A 15-minute episode needs about 150-220 cuts of 4-6 seconds; change shot every 4-6 seconds and hold longer only on a chart the narration is reading. Write the title, the thumbnail concept and the cold open in the same pass, so they make the same promise. The title is story-led: a secret, a person, a consequence for the viewer, never "X explained" or a date-bound forecast.

### Beats (900 s)

| Time | Beat | It must |
|---|---|---|
| 0:00-0:45 | Cold open | start mid-event and end on the central question |
| 0:45-2:30 | Why it touches your money | link the story to the viewer's wallet; introduce the anchor metaphor |
| 2:30-6:00 | Origins | chronology with rising stakes, one reveal every ~90 s |
| 6:00-9:00 | The protagonist | a real person enters and the story turns |
| 9:00-12:30 | Escalation and climax | the scandal, crash or breakthrough at full scale |
| 12:30-14:15 | The honest verdict | what the evidence shows, with real data charts |
| 14:15-15:00 | Hand-off | a cliffhanger into the next part (`series.next_episode_title`), and the comment question |

For 1,800 s keep the skeleton and: add a second human character (an opponent or investigator) around minute 18; add an act between the climax and the verdict, "the cover-up" or "the aftermath"; use 12-14 chapters of 2-3 minutes instead of 6-8.

### Writing rules

- A chapter every 1.5-2.5 minutes, each title written as a hook (it becomes a YouTube chapter).
- One anchor metaphor per episode, introduced in the first 4 minutes and reused to the end, including in the comment question.
- Every number gets a comparison the viewer can feel.
- Name people and dates. Never write "experts say" without naming who and where.
- Put these markers in the scene `note` field so the builders and later stages find them: `[CHAPTER]`, `[SHORT: spark|myth|legacy]` (the scene a Short is cut from), `[CHART: dataset]`, `[RECON: scene]` (a reconstruction; label it "Reconstruction" on screen with an overlay), `[ARCHIVE]`, `[STOCK]`.
- Drug and war topics: keep to money flows, supply chains and policy. No graphic imagery in the opening or the thumbnail. Set `visuals.allow_graphic_archive` false in your own plan even when the request allows it.
- Disputed history is labelled as disputed in the narration.

### Research, fact check, then the script

1. **Research brief** (stage `script`): before writing, use WebSearch and WebFetch to build `research/fact_sheet.md`: the people, dates, figures and quotations the episode needs, each with its source URL, from primary sources where they exist (FRED, BLS, EIA, IMF, central banks, court and regulator filings, the original documents). If `series.theme` has an earlier part in the same run folder tree there is no shared sheet; build this part's own and keep the facts consistent with `series.previous_episode_title`.
2. **Script draft:** write the script only from the fact sheet. A fact you want that is not in the sheet goes into the sheet first, with its source.
3. **Fact check:** run `python3 -m docgen factcheck`. It starts a separate Claude session that extracts every claim and checks each against a primary source, and writes `review/claims.md`. Cut or hedge every `unsupported` and `hedge` claim with the `fix` wording, label every `disputed` one as disputed in the narration, update the script and run `python3 -m docgen factcheck --verify`. Repeat until the second pass has no unsupported claim, at most three rounds; what is left after that is cut from the script. Report the counts with `status --message`, and add a `--warn` for every claim you hedged or labelled disputed.
4. Only then raise `cp_script` (in checkpoints mode), listing `review/claims.md` among the `--review` files.

### Visuals

AI generation is for scenes no camera captured. Per beat: cold open, a Wan or LTX reconstruction of the key moment plus a title card; "why it touches your money", Storyblocks everyday footage; origins, archive photographs with slow push-ins; protagonist, an archival portrait then reconstructions with a consistent likeness (one reference image per real person, reused in every part of the theme); climax, reconstructions in fast cuts; verdict, charts and calm Storyblocks b-roll; hand-off, a teaser frame from the next part and the end card. Target mix: about 40 % stock and archival, 25 % charts and maps, 25-35 % LTX/Wan motion, the rest cards and overlays. Never use text-to-image for a frame with numbers; a number is an overlay (`stat`) or a chart. If the build has no chart tool yet, use `stat` overlays over calm footage and warn that the data charts are missing. Use one colour palette and one font per theme.

### Charts and data

Every number the verdict stands on is a chart drawn from real data, never an image-model picture. When a scene needs one (`[CHART: dataset]`):
1. `python3 -m docgen data fred|bls|eia|imf ...` fetches the series (keys `FRED_API_KEY`, `EIA_API_KEY`, optional `BLS_API_KEY`, set in the environment; the command says so when one is missing). Never type figures in from memory. If a key is missing, use `data file` on a table you downloaded from the primary source, or use a `stat` overlay and warn that the chart is missing.
2. `python3 -m docgen chart <id> --data data/<file>.json --title "<what it shows>" [--highlight <x> --label "<event>"]` writes `ltx_chart_<id>.mp4` and `chart_<id>.png` in the assets folder.
3. The scene is `{"asset": "chart_<id>", "kind": "animated", ...}` and holds at least 8 seconds, so the narration can read the chart. The data file's `url` goes into the fact sheet; the Fact Checker verifies the claim the chart makes.
Use a line chart for change over time and a bar chart for comparing a few values; at most 8 bars.

### Reference images

`series.refs` in `request.json` maps a real person to the theme's reference image URL (one per person, shared by every part). Download each one and use it as an image input whenever that person appears (portrait, reconstruction keyframes, thumbnails: put the URL in the target's `refs`). If a person the episode needs has no reference, use an archival portrait and warn that one is missing; do not invent a likeness.

### Thumbnails (long video and every Short)

Follow the thumbnail section above exactly; for this format also: the long thumbnail and each Short's get their own story and their own 2-5 word headline, a number-led one where the fact sheet has a striking sourced figure (`12,941 TONS`, `90 DAYS`), never a claim the Fact Checker did not support. Shorts are 9:16: headline in the upper band, hero subject in the middle, nothing essential near the edges. Use `economic_explainer` for money, markets and policy episodes, `epic_historical` for wars and empires, `mystery_discovery` for espionage and cybercrime. Never put graphic violence in a thumbnail (drug and war themes). Each Short's chosen thumbnail is inserted as its cover frame (`thumbnail cover --short <id>`).

### Packaging

`meta.json`: chapter titles written as hooks; `comment_question` (polarising, built on the anchor metaphor); `watch_next` (`series.next_episode_url`, or the playlist when the next part is not public yet); the description starts with the one-line channel identity "The hidden stories behind money." The source table is added by `metadata` from the fact check.
