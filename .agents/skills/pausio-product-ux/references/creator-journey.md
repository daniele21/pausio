# Primary creator journey

**Persona**: social creator filming a 40–90 s Italian explanation outdoors with a smartphone. May be new to technical editing; high priority: speech not clipped, natural breathing, minimal effort.

| Stage | UI question | Acceptable outcome | Failure recovery |
| --- | --- | --- | --- |
| Import | "Quale video lavoro?" | file name, duration, preview; original preserved | unsupported codec/error, choose another video |
| Analyze | "Quali pause posso ridurre?" | proposed keep intervals, time saved, caveat on signal-based silence | try again or keep original |
| Review | "Quale voce resta?" | edit start/end, seek, restore, original vs montaggio preview | invalid range gets explicit validation |
| Approve | "Ho davvero verificato i tagli?" | explicit confirmation required for export | any edit invalidates approval |
| Export | "Posso vedere/salvare il risultato?" | async render, completion, direct MP4 download | source/plan untouched on failure |
| Optional transcript | "Cosa è stato detto?" | actual ClosedRoom local transcript when server running | clear service-not-running error |

Avoid showing raw JSON unless in an advanced troubleshooting view. A distinct "Montaggio" mode is a simulated seek-preview, not a frame-perfect proof. Always have users inspect the final MP4.

Design inspirations (principles only): https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md
