# Visual FX QA and proposal gate

| Test fixture | Expected |
| --- | --- |
| Talking head 1080x1920, 3 edited cuts | Hard cuts preserved; 1-2 subtle punch-ins only after explicit acceptance |
| Landscape phone video composed to 9:16 | Zoom always within visible image; crop does not expose invalid margins |
| VFR speech 29.97/60 variable | No drift between source-anchored effects and real ASR words; CFR export stable |
| 540x960 preview / 1080x1920 final | Same normalized transform trajectory and stable subtitles |
| Off-center face / head motion | Smooth face anchor, no jitter/eyes outside safe area, fallback when missing |
| Two KEEP segments with no overlap handles | Transition rejected or user-approved hard-cut fallback; no frozen/duplicated audio |
| Mid-effect cut removal | Reject/re-split affected effect with explicit UI warning, not silently remap to wrong words |
| Zero audio in source | Can propose cut-based FX; cannot pretend speech emphasis or beat detection worked |
| Too many candidate points | Deterministic caps, spacing, one proposal per region; manual review |
| Injected FFmpeg expression in command | Schema rejects; renderer only generates hardcoded filter family |

### Suggested initial defaults (experiments, not objective rules)

- `subtle`: 1.1–1.2x, 180–300ms ramp, 3–5 sec gap between *accepted* moves, <=6 suggestions/min.
- `balanced`: 1.1–1.25x, >=2.5sec spacing, <=10 suggestions/min.
- `dynamic`: creator opt-in, not the default.
- `transition`: hard cut default; 120–250ms dissolve only for contextual B-roll and valid handles, never mandatory for each pause cut.

Require actual speech/audio + face-tracking provenance when suggesting prosody/face-driven effects; report missing signals rather than making them up.

### Threat and safety
- Video filters from validated numeric input only, not user strings; cap keyframe count, transitions/minute, pixel dimensions and render resources.
- No remote image/model upload or shell. Do not assume FFmpeg's native codecs are harmless; follow `pausio-input-media-defense`.
- Film-like flashes/strobes and violent shakes should not be selected by default.
