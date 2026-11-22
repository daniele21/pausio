# Pausio · Three Style Packs and Motion Graphics spike (v1)

**Status:** development branch \`feat/editorial-style-packs\` (not an installed Studio feature).
This slice is deliberately compatible with the existing \`pausio.project\` v10
command tape. It does not add a new render runtime, change old scene templates,
migrate schema, apply edits automatically or export real creator footage.

## Objective

One reviewed source edit -> three **different proposals** for the same
edited-output timeline: **Authority**, **Visual Explainer**, **Social Impact**.
The style is a policy, not just a skin: it controls density, layout selection,
caption preset and suggested zoom/editorial presets.

| Policy | Authority | Visual Explainer | Social Impact |
| --- | --- | --- | --- |
| Narrative goal | Credibility, emphasis | Explain causal steps | Strong hook, fast comprehension |
| Suggested captions | \`minimal\` | \`word_focus\` | \`kinetic\` |
| Suggested camera preset | \`naturale\` | \`educativo\` | \`dinamico\` |
| Existing editorial preset | \`clean_tech\` | \`educational\` | \`dynamic_social\` |
| Scene budget / min | 2 | 6 | 8 |
| Min gap between scenes | 3000 ms | 900 ms | 450 ms |
| Maximum single scene | 3500 ms | 4700 ms | 2600 ms |
| Color accent | Mint | Mint | Orange |

The numbers are **initial product parameters**, not claims about platform algorithms
or recommended edit frequency. They must be measured on real creator videos.
No style requires continuous split screen or mandatory visual coverage.

## Implemented API — read-only proposed storyboard

\`pausio.style_packs.catalog()\` returns the three versioned configurations.
\`propose_variant(beats, output_ms, style_id)\` returns one proposal.
\`propose_three_variants(beats, output_ms)\` returns all three.

A beat is a human- or agent-reviewed structure with exactly:

- \`start_ms\`, \`end_ms\` — **edited OUTPUT time**, integers.
- \`purpose\` — \`hook\`, \`problem\`, \`evidence\`, \`explanation\`, \`takeaway\`.
- \`visuals\` — a mapping from existing registered scene template IDs to a
  **fully populated, reviewed** content object. The planner will never
  populate fields from the illustrative template defaults.
- \`evidence_verified\` — explicit editorial attestation. This is **not**
  a factual source verifier; a \`metric_spotlight\` is not proposed unless true.

The output contains an ordered list of \`scene.template.add\` candidates
(each with scene ID, original beat index and strict scene payload), plus
\`skipped\` reasons and suggested camera/caption/editorial preset IDs.

**This does NOT modify Pausio**. To turn candidates into a real edit, Studio or
the agent must first read current project revision and transcript, check cuts
and overlays/safe areas, then apply each proposed command through the
existing validated \`pausio_apply_command\` / \`ProjectTape\` mechanism with
explicit review. Local project revision and media fingerprint still govern.
One \`scene.template.add\` command at a time until an atomic batch protocol is
implemented. Only the creator can approve final export in Studio.

The planner preserves content verbatim after strict schema validation. It
rejects out-of-bounds/overlapping beats, excess beats, invalid scene types
and uncertain numeric evidence. If a requested visual does not fit in the
beat, the output records a skip rather than silently extending the scene.

## Studio API (read-only, not yet an editor panel)

The existing local Studio snapshot now includes `style_pack_catalog`. A
revision-guarded `POST /api/editorial/variants` endpoint accepts a JSON
object containing exactly `revision` and `beats` and returns three
independent storyboard proposals plus `base_revision` and
`media_sha256`. It requires the same local-host, content-type, client
header and origin checks as existing Studio editing requests.

The endpoint does **not** call any generative service, inspect private audio,
change `ProjectTape`, add scene templates, start a preview or approve edits.
The caller must supply all reviewed beats and complete scene copy. It is
intentionally a foundation for a future Studio compare/editor panel.

## Motion Graphics primitive: count-up (technical spike)

\`pausio.motion_metric.countup_frames\` converts an **already-approved**
integer label (e.g. \`1.379\`) into a bounded count-up schedule using cubic
ease-out. It only supports unsigned integer labels with optional Italian
thousands grouping. Decimals, percentages and arbitrary text are kept static.
The last frame always contains the original exact value.

\`compose_counter_events\` emits allowlisted ASS dialogue rows through
Pausio's existing scene events. It accepts no FFmpeg expression, script,
remote URL, arbitrary font or unescaped override from user copy.

To see it **without any private input video**:

\`\`\`bash
python -m pip install -e .
python scripts/demo_metric_motion.py --output /tmp/pausio-metric-demo.mp4
\`\`\`

Requires FFmpeg with libass and H.264 encoder, same as Pausio Studio.
The video is a 540×960 synthetic 3.2-second graphic marked
\`PROTOTIPO · DATI ILLUSTRATIVI\`. It is a motion/render test, **not**
a newly exposed Scene Template or a new command in v10. Do not present
it as an integrated, selectable Studio feature.

## Compatibility and security boundaries

1. No edit to \`project_commands.py\`, JSON schemas or existing scene render
   paths. Old v1–v10 projects retain their old meaning and scene appearance.
2. Output of this module is a *proposal*, never an implicit approved edit.
3. The exact numeric value is supplied by the human/agent, not fabricated
   by the algorithm; no online source verification is claimed.
4. Media remains local. No public repo attachment of real creator footage,
   screenshots, transcripts, credentials or generated private preview.
5. All new text paths ultimately use Pausio's ASS-escaping mechanism.
6. No background network service, arbitrary script injection, URLs or remote
   asset import.

## Tests

\`\`\`bash
python -m unittest discover -s tests -p 'test_style_packs.py'
python -m unittest discover -s tests -p 'test_motion_metric.py'
python -m unittest discover -s tests -p 'test_style_packs_studio.py'
\`\`\`

Verify deterministic candidate IDs, distinct policies, nonmutation,
schema validation, missing copy, unsigned integers, frame boundaries,
ASS escaping and invalid inputs. Run the synthetic FFmpeg demo and
visually inspect frames and final still on the target Mac before merging.

## Integration roadmap

1. **This PR:** typed Style Packs, three read-only storyboard plans, safe
   counter rendering prototype, regression tests and documentation.
2. **Next:** review plan in Studio and store style variant identities as
   first-class versioned project instructions (schema migration required);
   allow switching variant with independent undo and approval.
3. Integrate new graphic components under stable identifiers and typed
   validated fields; preflight face/caption-safe regions and inspect rendered
   frames. Avoid altering legacy template rendering.
4. Connect an AI Editorial Director via MCP: semantic beat selection and
   optional exact edit batch after user review; never fabricate facts or
   assume a screenshot is real.
5. Benchmark a dedicated motion renderer (Remotion vs Motion Canvas),
   including license, frame accuracy, alpha, reproducibility, performance
   and local-only deployment. FFmpeg remains the final compositor.
6. After PR #84–#87 are merged/retargeted safely, integrate B-roll video,
   caption emphasis and media/graphic motion without duplicating work.

**Acceptance for production:** three independently reviewable timelines,
high-quality visual checks on a real phone, end-to-end voice sync, no clipped
captions/face, exact source-to-output timing, Undo/Redo, import/export
round trip and manual approval per variant.
