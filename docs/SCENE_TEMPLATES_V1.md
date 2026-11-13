# Scene templates v1 — Pausio Studio + ChatGPT MCP

Status: implemented in `daniele/scene-templates-v1`; consider this shipped
only after CI, browser audit and PR merge.

## What it does

This is the first concrete Scene Composer slice for the proposed 9-scene
password/GitHub storyboard. Three **full-screen** illustrative templates
are rendered with the existing FFmpeg/libass pipeline while preserving the
source voice and existing audio mix:

| Scene | Template ID | Editable content |
|---|---|---|
| 03 — 1.379 secrets | `stat_reveal` | eyebrow, number, label, verified detail |
| 04 — Don't ask again | `permission_dialog` | title, command description, two button labels, explanatory detail |
| 05 — Configuration | `code_highlight` | title, filename, up to five bounded code lines, highlighted line, detail |

The permission dialogue is always labeled **SIMULAZIONE • NON È UNO
SCREENSHOT**, preventing an illustrative UI recreation from masquerading as
an authentic screenshot. Code uses safe fullwidth braces/backslashes to
avoid interpreting untrusted ASS overrides.

These templates are intentionally modest, purposeful compositing building
blocks — **not** a general HTML canvas, arbitrary SVG, animations system or
claim to match the final supplied storyboard pixel by pixel.

## In Studio

Import/analyze a video, open **Video FX → Scene grafiche a schermo intero**,
choose a template, edit its fields, choose a 2.5–12 s duration and insert
at the output-time playhead. Each scene appears in a list with its exact
edited-video timing, **Vai al punto**, **Guarda 5 s**, **Modifica testo e durata**
and **Rimuovi scena**. Full-screen scenes intentionally cover the face/video
while speech/music continue. Captions are layered above scenes.

A scene is a single edit event: undo/redo, recovery, portable JSON export/
import and approval invalidation all use the existing ProjectTape.

## In ChatGPT via MCP

After updating Pausio and restarting Studio **and tunnel** to refresh tools,
call `pausio_get_scene_templates`. It returns the exact allowed names,
fields, defaults and duration bounds. Then read `pausio_get_project`,
choose a nonoverlapping **edited output** interval and submit
`pausio_apply_command` with a revision precondition.

Example command, ready for the existing `pausio_apply_command` MCP tool:

```json
{
  "revision": 73,
  "type": "scene.template.add",
  "payload": {
    "scene": {
      "id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "template": "stat_reveal",
      "start_ms": 12000,
      "duration_ms": 8000,
      "accent": "orange",
      "content": {
        "eyebrow": "UNA RICERCA HA TROVATO",
        "number": "1.379",
        "label": "SEGRETI",
        "detail": "in 1.122 file pubblici"
      }
    }
  }
}
```

*The revision above is illustrative: fetch the current revision before
applying. Use a fresh 32-char hex ID for each new scene. If the example
overlaps an existing full-screen scene or extends beyond output duration,
the reducer rejects it without changing the project.*

All values are bounded and strictly typed; no arbitrary FFmpeg filters,
CSS, HTML, JS, shell commands or URLs. Maximum nine scenes. Scenes are
`timebase: output` by contract (not implicit source timestamps). Source-time
camera/graphics and output-time scenes are different layers by design.

Render with `pausio_preview_range` or full `pausio_render_preview`;
then review in Studio before manual confirmation/final render.

## Implementation boundaries and next steps

- Pure `src/pausio/scene_templates.py` owns validation, catalog, template
  schedules and ASS events. No external runtime dependency.
- `project_commands.py` accepts `scene.template.add/update/remove` as
  replayable version **v8** project events. Legacy v1–v7 import remains valid.
- `graphic_overlays.py` composes scenes in the existing ASS document;
  `media.py` uses the exact same graph for preview and export;
  `studio.py` passes the current view and scene catalog.
- `scene_template_ui.js/css` own the Studio form; no new frontend framework.
- `mcp_tool_catalog.py` and `local_mcp.py` expose the same catalog/events.

Future separate milestones: animated chart data and timeline keyframes,
scene-by-scene draft previews returned to the chat agent, visual/audio
inspection, actual imported video B-roll, audio ducking, atomic editing
batches, and richer popup/code layout (without unrestricted CSS/JS).
Do not claim these are implemented here.

## Acceptance

Python pure replay and invalid inputs, scene timing and import from legacy
v7, deterministic ASS escape and caption layering, real FFmpeg with synthetic
source voice, Studio HTTP and Playwright edit/preview/undo. User still reviews
the rendered A56/Mac video for typography and audio before approving.
