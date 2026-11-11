# Pausio Studio — local UX testing guide

## Start in one command

With Python 3.11+, FFmpeg and FFprobe on PATH, install once (`pip install -e .`) and launch `pausio studio`. A browser opens `http://127.0.0.1:8765` if available. When occupied, Pausio binds the next free loopback port (`8766`, `8767`, ...), prints the actual URL and opens that URL. `--port 8877` changes the starting port; `--no-open` disables browser launch. Port fallback does not bypass the one-process-per-workspace lock: stop an existing Pausio instance using the same saved session or explicitly select another data directory. Stop with Ctrl+C. The session remains privately stored on disk until explicitly deleted. No Node.js, internet, account, CDN or app-server framework is required.

## Creator workflow

1. **Importa** — choose or drag a video up to 2 GiB (MP4 / MOV / M4V / MKV / WebM). Browser uploads to the loopback-only Python server, which retains a private local copy for autosave and crash recovery. Inspect duration, codec, dimensions and audio presence in the project panel. The original imported file is not mutated by editing.
2. **Analizza** — select **Naturale**, **Bilanciato**, or **Dinamico** in **Impostazioni tagli** (left rail). Expand **Parametri avanzati** to edit the silence threshold (dB), minimum pause, minimum removal, speech padding and minimum retained clip (milliseconds); editing any parameter changes the preset to **Personalizzato**. Click **Analizza le pause** or **Rianalizza le pause** to apply the selection. The result box shows how many silences FFmpeg detected and how many seconds would be excluded. If no time is saved, try a more sensitive preset. The signal-based policy proposes a versioned KEEP timeline, not semantic speech edits. Reanalysis replaces the current review proposal, resets approval and can be undone. The applied settings and count are stored in the portable `analysis.propose` command; previously exported v1/v2 projects without settings continue to import.
3. **Rivedi** — inspect the retained intervals in the right inspector and timeline. Change start/end numeric seconds, exclude a retained interval, bring back the largest excluded gap, restore the initial suggestion, or keep everything. Browser-side preview has **Originale** vs **Montaggio** modes. The latter seeks across the original clip and is an approximate preview, not a final audio master.
**Salva e riprendi:** ogni modifica e cambio nella cronologia viene salvato automaticamente sul Mac. Riaprendo `pausio studio` nella stessa cartella dati ritrovi il progetto e il video; non è necessario reimportarli. Puoi usare **Annulla** / **Ripeti** (anche ⌘Z / ⌘⇧Z) per navigare la cronologia. Per spostare il progetto su un altro computer, clicca **Esporta progetto** per scaricare `.pausio.json`. In quel caso importa prima **lo stesso video originale**, poi clicca **Importa progetto**. Pausio confronta lo SHA-256 e ricostruisce il montaggio riproducendo le istruzioni salvate. Il file non contiene il video o trascrizioni. Vedi [Formato progetto](PROJECT_FORMAT.md).

4. **Conferma montaggio** — explicit approval. The backend blocks rendering until this action. Every change after approval resets the approval and invalidates prior export.
5. **Esporta MP4** — asynchronous FFmpeg render and direct download. Final output is 1080x1920, 30 fps H.264/AAC (if source has audio), aspect ratio preserved with padding. Inspect the saved file for quality and A/V synchronization before publishing.
6. **Trascrivi il parlato** — optional parallel action: requires the existing ClosedRoom local service running on the same Mac. A normalized, timestamped transcript appears in the inspector. The transcription does not change KEEP intervals and is not yet used to generate subtitles.

## UX layout

- **Top:** recognizable Pausio brand and local processing indicator; no fake cloud-login state.
- **Left:** four-step flow, selected video metadata and real action buttons.
- **Center:** large vertical preview and direct playback controls. Desktop / mobile responsive layout.
- **Right:** decision inspector showing every KEEP interval, editable numeric boundaries and explicit confirmation; optional transcript tab.
- **Bottom:** waveform extracted locally from the actual audio track, kept/excluded source-time regions, draggable and keyboard-adjustable cut handles, zoom 1×–8× and a synchronized playhead. Edits always dispatch one validated `segment.update` command and invalidate stale preview/export. Direct export/download remains approval-gated.

Design language: cinematic neutral ink surfaces, warm amber action, mint kept spans, clear typography and persistent state text. The visual palette is encoded as semantic variables in `studio_static/styles.css`, not scattered hardcoded colors.

## Precise review options

- **Originale** plays the imported clip.
- **Simulazione** skips excluded segments using browser seeks; this is fast but can jump at keyframes and should not be used for final audio decisions.
- **Genera preview** uses **the exact same FFmpeg trim/atrim/concat timeline as the master render**, encoded at 540×960 for faster iteration. It does **not** need approval and does **not** modify the project. Once rendered, select **Preview FFmpeg** to hear actual transitions. Source and output playback clocks are mapped to the same source-time cut timeline.
- Waveform is computed asynchronously after import, from downsampled local audio. It never uploads content or invokes ClosedRoom; it is a media visualization only. For clips longer than 15 minutes, waveform is unavailable instead of scanning unbounded recordings. If no audio exists, the waveform is blank.
- Drag the **left/right grip** of a green retained interval to change its original-time boundaries. Keyboard users can focus a grip and use Left/Right for ±100 ms, Shift+Left/Right for ±500 ms. Adjacent intervals cannot overlap; a minimum 50 ms interval is maintained.
- Use **Zoom 1×, 2×, 4× or 8×** for detailed review. Zoom and playback position are viewing state only, not output-affecting project commands.
- Every trim is saved as a typed `segment.update` event in `.pausio.json`; Undo/Redo and local autosave apply as before. Preview files and waveform are derived caches, not canonical editing data.

## Shortcuts and accessibility

- Space toggles playback when focus is not inside an input/button/interactive control.
- Left/right arrows jump ±5 seconds; timeline itself supports arrows and Home/End.
- **Cmd/Ctrl+Z** annulla; **Cmd/Ctrl+Shift+Z** o **Ctrl+Y** ripristina. Nei campi di testo i comandi Undo/Redo restano gestiti nativamente dal browser.
- All editing controls use native buttons and labeled number inputs, visible keyboard focus, semantic tabs, polite status messages and reduced-motion support.
- On browser codecs that cannot be decoded (some phone MOV/HEVC files), the preview shows an error; use an H.264 MP4 for testing. Export can still work if FFmpeg can decode the source.

## Persistence and privacy

- HTTP server listens **only on 127.0.0.1**. Mutating endpoints require a custom `X-Pausio-Client` header and reject foreign `Origin` values; no CORS, no remote assets, external analytics or user login.
- Imported video and command project are retained in a **private, persistent local workspace** to enable automatic recovery after restart/crash. Default macOS path: `~/Library/Application Support/Pausio/Studio` (configurable via `--data-dir`); Linux: XDG data home or `~/.local/share/pausio/studio`. A one-step older checkpoint is kept for recovery if the latest fails. A single-process file lock prevents simultaneous editors corrupting the session. Files are 0600 and directory 0700 on POSIX.
- **Closing Studio no longer deletes the video or saved project.** Use **Elimina dati locali** to erase the managed media, active project and backup. The rendered MP4 is still a working artifact, not a guaranteed persistent deliverable: download the final export. The ClosedRoom transcript is still only in memory and will not be restored after a restart. No media or transcripts are committed to Git.
- Browser upload (`application/octet-stream`) is streamed to disk with a 2 GiB cap; fixed-file-name processing paths are not accepted from untrusted browser JSON.
- ClosedRoom is external, separately running, and is the sole ASR engine. Pausio does not install ASR weights; keep upstream model downloads explicit.
- Local-only does not mean hostile multi-user isolation: do not expose the port with reverse proxies or host forwarding. The v0 Studio is not designed for shared-machine access.

## Known limits / honest quality boundaries

- Audio-level silencedetect cannot distinguish quiet speech from silence; all proposals demand listening review.
- Preview of selected cuts is a browser seek simulation; it can jump roughly at keyframes. Judge real synchronization and cut quality in the downloaded MP4, not the preview.
- No automated subtitles, waveform extraction, proxy transcoding, semantic cut scoring, narration denoising or CapCut exporter yet.
- The current UI is a **single active-project test bench** with one video at a time. Closing the process retains an autosaved private session; users can explicitly clear it. Unfinished background rendering/transcription is not resumed automatically.
- Running ClosedRoom ASR on actual real video has not yet passed a documented end-to-end compatibility test.
- Browser-assisted responsive screenshots, screen reader QA, and user sessions with real A56 recordings are still required before describing this as production ready.

## Testing

`python scripts/validate_skills.py`
`python -m unittest discover -s tests -v`
`python -m pausio studio --no-open --port 8765`

Key HTTP regression test: import a synthetic MP4, GET media Range, analyze silence, reject invalid overlap, confirm manually, render, download, probe output and check original unaffected. Additional QA: macOS/Chrome and Safari with A56 VFR/rotation and mic audio.

Upstream design inspirations (our implementation and four UI skills are original):
- https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md
- https://github.com/vercel-labs/agent-skills/blob/main/skills/web-design-guidelines/SKILL.md
- https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
