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
6. **Trascrivi il parlato** — optional Pausio-local ASR; no ClosedRoom server needed. A timestamped transcript appears in the inspector, and is saved atomically into the user-private local session (including real word alignments) for automatic restoration on app restart. It is bound to the imported media SHA-256 and is deleted on explicit session clear or a new video import; it is intentionally not included in the portable `.pausio.json`.
7. **Aggiungi sottotitoli** — under **Trascrizione** click **+ Aggiungi sottotitoli**, choose Social, Minimal or Riquadro, expand **Posizione e aspetto** to select the font family (Arial, Helvetica Neue, Avenir Next, Verdana, Georgia, Courier New, Impact, Times New Roman), set X/Y, font size, colors, outline and background, or click **Sposta sull'anteprima** to drag the caption (keyboard arrows ±1%, Shift ±5%). Each adjustment records a typed `caption.configure` command and invalidates approval. Edit individual captions and click **Salva testo**. Original/Simulazione show an overlay; **Preview FFmpeg** and exported MP4 burn actual subtitles after remapping to the edited output timeline. Any caption edit requires re-approval; caption text/styles persist in portable project commands.

## UX layout

### Desktop editor (viewport maggiore di 1000 px)

La prima iterazione desktop usa una barra modalità compatta a sinistra:
**Media**, **Tagli AI**, **Trascrizione**, **Sottotitoli**, **Audio**,
**Impostazioni**. Le modalità riutilizzano lo stesso stato del video e
la stessa cronologia: cambiare modalità non esegue comandi né altera
playhead, clip o preview.

La timeline rimane nel dock inferiore; il mixer delle tracce voce/FX
è affiancato alla timeline quando esiste un video. Il divisore
orizzontale sopra la timeline è trascinabile e si può regolare con
**↑/↓** dopo averlo messo a fuoco. Le preferenze sono salvate solo
localmente nel browser, non nel progetto portabile.

La toolbar desktop riporta **Annulla**, **Ripeti**, **Conferma montaggio**
ed **Esporta/Scarica MP4**, collegati alle azioni reali già presenti:
se il montaggio non è confermato l'export resta bloccato. In modalità
Audio gli effetti importati sono gestiti nel pannello inspector, usando
gli stessi controlli della versione precedente.

Il pannello strumenti Audio ora elenca gli effetti **realmente importati**,
permette di selezionarli e di aggiungerne altri tramite l'import esistente.
Il click su un FX nella timeline o nella lista seleziona l'effetto e mostra
l'inspector corrispondente, senza registrare un comando di modifica.

In modalità Sottotitoli, a sinistra c'è una lista delle frasi reali,
ricercabile per contenuto. La timeline mostra inoltre una traccia di
cue con gli intervalli **sulla scala temporale del video sorgente**.
Selezionare una frase nella lista o nella traccia porta al suo campo
di correzione già esistente; i timestamp della traccia non sono ancora
modificabili trascinando i blocchi. Per modificare il testo usa «Salva
testo», che registra un comando `caption.correct` versionato.

Il click su un intervallo video seleziona invece il KEEP segment e
apre i relativi campi Da/A. Su desktop l'inspector rimane contestuale;
la selezione e il ridimensionamento dei pannelli non vengono esportati
nel `.pausio.json` e non invalidano l'approvazione del montaggio.

Su tablet/mobile l'interfaccia esistente resta attiva, con timeline dopo
il player e prima dell'inspector. La versione desktop non replica ancora
tutte le funzioni raffigurate nei mockup: consulta
[il piano UX desktop](DESKTOP_EDITOR_UX.md) per limiti e milestone.


- **Top:** recognizable Pausio brand and local processing indicator; no fake cloud-login state.
- **Left:** four-step flow, selected video metadata and real action buttons.
- **Center:** large vertical preview and direct playback controls. Desktop / mobile responsive layout.
- **Right:** decision inspector showing every KEEP interval, editable numeric boundaries and explicit confirmation; optional transcript tab.
- **Bottom:** waveform extracted locally from the actual audio track, kept/excluded source-time regions, draggable and keyboard-adjustable cut handles, zoom 1×–8× and a synchronized playhead. Edits always dispatch one validated `segment.update` command and invalidate stale preview/export. Direct export/download remains approval-gated.

Design language: cinematic neutral ink surfaces, warm amber action, mint kept spans, clear typography and persistent state text. The visual palette is encoded as semantic variables in `studio_static/styles.css`, not scattered hardcoded colors.

## Precise review options

- **Originale** plays the imported clip.
- **Simulazione** skips excluded segments using browser seeks monitored on every animation frame during playback, plus a `timeupdate` fallback; this handles brief gaps more reliably than `timeupdate` alone. Seeking into an excluded interval resumes at the next kept clip, not at the beginning. If analysis has not excluded any time, the Simulation button is disabled. As browser seek accuracy varies with codec/keyframes, this fast simulation still must not be used for final audio decisions.
- **Genera preview** uses **the exact same FFmpeg trim/atrim/concat timeline as the master render**, encoded at 540×960 for faster iteration. It does **not** need approval and does **not** modify the project. Once rendered, select **Preview FFmpeg** to hear actual transitions. Source and output playback clocks are mapped to the same source-time cut timeline.
- Waveform is computed asynchronously after import, from downsampled local audio. It never uploads content or invokes the ASR runtime; it is a media visualization only. For clips longer than 15 minutes, waveform is unavailable instead of scanning unbounded recordings. If no audio exists, the waveform is blank.
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
- **Closing Studio no longer deletes the video or saved project.** Use **Elimina dati locali** to erase the managed media, active project and backup. The rendered MP4 is still a working artifact, not a guaranteed persistent deliverable: download the final export. The Pausio ASR transcript is now saved in the private local session, tied to its video hash and restored after restart; portable exports deliberately exclude it. No media or transcripts are committed to Git.
- Browser upload (`application/octet-stream`) is streamed to disk with a 2 GiB cap; fixed-file-name processing paths are not accepted from untrusted browser JSON.
- Caption fonts are system font family names, not bundled assets; preview HTML may substitute missing fonts differently from FFmpeg/libass. Generate the rendered FFmpeg preview to verify actual typography, especially across machines. Old `caption.configure` events without `font_family` normalize to Arial.
- Pausio implements its own independent on-device MLX Whisper engine on Apple Silicon. It does not require ClosedRoom to run; optional ASR dependencies and model download consent are managed locally.
- Local-only does not mean hostile multi-user isolation: do not expose the port with reverse proxies or host forwarding. The v0 Studio is not designed for shared-machine access.

## Expected browser disconnects

Studio uses a local HTTP/1.1 server. If the browser abandons a keep-alive connection (for example after navigation or cancelling media playback), Pausio closes that connection without printing a noisy `ConnectionResetError` or `BrokenPipeError` traceback. This does **not** swallow application errors; failed jobs remain visible in the UI. Browsers probing `/favicon.ico` receive an empty HTTP 204 instead of a misleading 404. Python 3.11–3.13 are exercised in CI; newer Python versions are not yet part of the tested matrix.

## Known limits / honest quality boundaries

- Audio-level silencedetect cannot distinguish quiet speech from silence; all proposals demand listening review.
- Preview of selected cuts is a browser seek simulation; it can jump roughly at keyframes. Judge real synchronization and cut quality in the downloaded MP4, not the preview.
- No automated subtitles, waveform extraction, proxy transcoding, semantic cut scoring, narration denoising or CapCut exporter yet.
- The current UI is a **single active-project test bench** with one video at a time. Closing the process retains an autosaved private session; users can explicitly clear it. Unfinished background rendering/transcription is not resumed automatically.
- Real local MLX Whisper on Apple Silicon with Italian A56 footage, memory use, time offsets and Python 3.15 remain unverified.not yet passed a documented end-to-end compatibility test.
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

## Ascolto live degli effetti nella preview del video

La presenza della waveform viola **non basta** a far ascoltare un riser: ora il player sovrappone l'audio importato alla voce originale durante Play in modalità **Originale** o **Simulazione**, senza dover creare ogni volta un MP4. Il controllo **♫ FX attivi/spenti** disabilita soltanto l'ascolto live, **non** rimuove l'effetto dal rendering. Le clip FX rispettano posizione, durata, guadagno in dB, velocità, play/pause e seek del video, oltre ai tagli esclusi. In modalità **Preview FFmpeg** il monitor FX è disabilitato per evitare il raddoppio dei suoni: l'MP4 renderizzato ha già il mix incorporato. Un formato non riproducibile nel browser viene segnalato con indicazione di generare una preview FFmpeg. Per decidere il volume finale, ascolta sempre la preview renderizzata, non soltanto l'ascolto live che può avere piccoli ritardi alle transizioni.

## FX audio locali

La traccia FX opzionale permette di importare riser e altri effetti in MP3/WAV/M4A/AAC/FLAC/OGG (60 MB e 3 minuti massimo). Un effetto è aggiunto al momento del playhead (la fine si allinea al punto selezionato), e può essere ascoltato isolatamente, spostato in secondi, modificato in dB o rimosso. Preview e export FFmpeg mixano la voce originale e gli effetti. Undo/Redo e l'export `.pausio.json` conservano i comandi, ma non i byte degli audio. Alla riapertura sulla stessa macchina i file privati sono recuperati; su un altro Mac occorre reimportare lo stesso audio, verificato tramite SHA-256. Render bloccato per file mancanti o alterati.

### Tracce audio sovrapposte e riferimenti temporali

La waveform superiore continua a rappresentare i **timestamp del video originale**, perché le maniglie dei tagli agiscono sul sorgente. La seconda traccia **FX**, direttamente sotto la waveform nello stesso scroller, riutilizza il medesimo righello, zoom e playhead. Gli effetti sono salvati in **tempo montato** e la loro visualizzazione viene proiettata sui segmenti KEEP della prima traccia: se un riser attraversa un salto di montaggio, appare suddiviso in più porzioni, senza introdurre una pausa nel suo audio. La waveform FX è ottenuta da FFmpeg e non simulata. Trascina una clip per spostarla oppure usa le frecce (100 ms, con ⇧ 500 ms); il risultato viene registrato come `audio.update`, quindi può essere annullato e riprodotto da progetto esportato. La preview FFmpeg rimane l'autorità sull'audio mixato, perché la timeline è una rappresentazione per il montaggio e non una DAW.


## Mixer audio Voce / FX

Subito sotto la timeline è visibile il **Mixer audio**: una corsia per **Voce originale** e una per **Effetti FX**. Entrambe offrono uno slider -36/+12 dB, percentuale equivalente (100% = 0 dB), un pulsante **Silenzia/Riattiva** e reset a 100%. Gli FX dispongono anche di uno slider specifico per ogni riser, con input numerico in dB per precisione, mute e reset al volume predefinito del riser (-12 dB). FX generale × volume clip = livello effettivo. Un valore superiore a 100% amplifica il segnale, ma può introdurre distorsione in ascolto live: FFmpeg applica il limiter al mix finale. Il mixer non modifica il file originale.

Durante il drag degli slider il **monitor live** aggiorna immediatamente il volume della voce e del riser, senza creare decine di comandi. Al rilascio viene emesso **un evento strutturato**. Lo stato finale è conservato nel progetto, recuperato al riavvio, esportato nel JSON e supporta Undo/Redo. I comandi sono `audio.mixer.configure` per i due bus e `audio.clip.mix` per un singolo effetto. Il controllo "♫ FX attivi" è invece una *preferenza temporanea di ascolto live*: non deve essere confuso con **Silenzia** del bus FX, che rende muti gli effetti anche in export. La preview FFmpeg applica il mix in modo definitivo e non riproduce i suoni una seconda volta dal monitor browser. Cambiando il mixer durante una preview FFmpeg si ritorna al lettore originale, evitando di ascoltare una preview non aggiornata.

Per i progetti precedenti al mixer, voce e bus FX partono da 100%, non silenziati, mentre ciascun riser mantiene il proprio gain precedente (-12 dB quando appena importato). Il JSON `.pausio.json` conserva i parametri ma non incorpora i file audio (che devono essere reimportati su altri dispositivi).
