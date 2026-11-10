# Studio UI quality matrix

| Area | Test | Expected |
| --- | --- | --- |
| Import | video file, bad extension, empty, >limit | no source corruption; helpful errors |
| Workflow | analyze→edit→approve→export | job state accurate; export gated |
| Plan | overlap, inverted range, reset original | invalid rejected, prior preserved |
| Preview | source vs montaggio, play/pause, seek | no hidden source mutations |
| Browser | cannot decode MOV/HEVC | actionable fallback; final output separate |
| Transcript | ClosedRoom absent, mocked local response | clear failure and honest alignment status |
| Privacy | foreign Origin, no X-Pausio-Client, remote scripts | rejected/no remote load |
| Keyboard | Tab, Space, arrows, timeline Home/End | predictable focus/seek |
| Responsive | 1440, 1024, 390, 200% zoom | no essential control overlap |
| Media quality | real A56 VFR/outdoor audio | no clipped speech, AV drift, noise discontinuity |

In CI: Python unittest + static skill validation + FFmpeg synthetic videos. Browser screenshots and human listening are separate real-world acceptance gates.

Reference: https://github.com/vercel-labs/agent-skills/blob/main/skills/web-design-guidelines/SKILL.md
