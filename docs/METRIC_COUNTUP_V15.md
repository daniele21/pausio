# Pausio · Metric Count-up Scene v15

**Status:** development branch `feat/metric-countup-v15`; stacked on
`daniele/social-media-motion-v1` (PR #87, project schema v14).
Not yet on `main`, not part of v0.1.0 downloadable package.

## A real, editable, deterministic Motion Graphics component

`metric_countup` is a separate, typed, output-timed Scene Template
with precisely the same editable fields as the existing
`metric_spotlight`: heading, number, unit, detail and source note.
The **new template** renders the literal integer `number`
as a short easing count-up inside the existing native libass
scene composition pipeline. Every other label and the underlying
voice audio is handled exactly as in the current scene renderer.

In Studio, open **Composizione editoriale modulare**, choose
**Metrica animata (count-up)**, enter a literal verified integer,
set duration and timing, add it as a normal `scene.template.add`.
Undo/Redo, project import/export, preview and final MP4 all reuse
the same canonical typed commands and the same FFmpeg compositor.

There is **no** new JSX/HTML scene engine, remote media dependency,
arbitrary formula or screen capture. The effect is native and
versioned: old `metric_spotlight` retains its previous render
identically; only explicit new `metric_countup` instructions animate.

## Format and validation

- `pausio.project` now writes **schema_version 15**.
- `schemas/pausio-project-v15.schema.json` accepts exactly the new
  additive `metric_countup` scene alongside all historical v14 types.
- Import of v1–v14 `ProjectTape` documents remains supported.
- Counted values: **unsigned whole numbers** from `0` to
  `9.999.999`, optionally with Italian thousands grouping
  (`1.379`, `12.345`, `1.234.567`).
- Decimals, percentages, negative values and malformed fields
  are **rejected by new-scene validation**; legacy scene rendering
  is unchanged.
- Number labels remain caller-supplied; Pausio does not infer the
  actual statistic or check an external source.
- Count-up uses a bounded 12-frame easing curve and exact supplied
  end value; safe libass override escaping is enforced.
- The input must fit within the output clip and cannot overlap other
  scene templates under the existing limits.

## Validation gates

```bash
python -m unittest discover -s tests -p 'test_motion_metric.py' -v
python -m unittest discover -s tests -p 'test_metric_countup_scene.py' -v
python -m unittest discover -s tests -v
```

Tests verify numeric parsing, ASS-escape behavior, valid and invalid
scene payloads, v14 import, deterministic replay, legacy visual parity
and a synthetic FFmpeg video render preserving audio and geometry.

Production acceptance additionally requires viewing the actual
1080×1920 graphic on a phone: typography, face/caption safe areas,
number pacing and pixel-perfect interpolation must be inspected.
No creator footage should be committed to a public repository.

## Dependency and integration

The PR stays stacked on PR #87 to avoid competing project v11–v14
migrations already staged in #84–#87. Once those are merged and the
separate three-variant PR #89 is rebased safely, the new template
will be available in each independently editable video variant.
