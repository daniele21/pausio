# Pausio

**Edit the noise. Keep the voice.**

A local-first toolkit for natural-sounding, talking-head social videos. Pausio is designed to make post-production **reviewable**, not fully automatic at the expense of speech or pacing.

> **Status: v0.1.0 Early Access (technical preview).** The current CLI inspects videos, suggests cuts using FFmpeg's signal-level silence detection, writes a human-editable JSON timeline, and exports a vertical 1080x1920 MP4. It now has optional standalone MLX Whisper ASR on Apple Silicon (no ClosedRoom app or service required), but does not yet make semantic cuts, denoise or export CapCut projects; its on-device transcripts can now drive **editable burned-in captions**.

## Download — GitHub Early Access v0.1.0

**[Scarica Pausio v0.1.0 da GitHub Releases](https://github.com/daniele21/pausio/releases/tag/v0.1.0)**. I file disponibili sono un pacchetto Python `.whl`, una distribuzione sorgente `.tar.gz` e `SHA256SUMS.txt`. **Non è ancora un'app `.dmg` installabile con doppio clic.**

Su macOS puoi installare il pacchetto senza clonare GitHub (scarica prima il file wheel negli Assets della release):

```bash
brew install python@3.12 ffmpeg
python3.12 -m venv ~/.local/share/pausio/venv
source ~/.local/share/pausio/venv/bin/activate
python -m pip install ~/Downloads/pausio-0.1.0-py3-none-any.whl
# opzionale su Apple Silicon: python -m pip install mlx-whisper "huggingface-hub>=0.26"
pausio studio
```

Segui le [note ufficiali della release](.github/release/v0.1.0.md) per i limiti e le istruzioni complete; il flusso via `git clone` qui sotto resta utile a chi vuole sviluppare il progetto.

## Provare la velocità del gobbo prima di REC

Da `/capture`, incolla il copione e premi **▶ Prova gobbo**: il testo
scorre anche senza fotocamera. Cambia `Velocità gobbo` durante la prova,
metti in pausa, riprendi dallo stesso punto oppure usa **↺ Dall'inizio**.
La modalità PROVA non registra audio o video e non crea file; **Registra**
riparte invece dalla prima riga dopo il countdown. Vale sia per PC sia
per smartphone. Maggiori dettagli in
[Capture: guida e test](docs/MOBILE_CAPTURE.md).

## Risolvere l'errore FFmpeg `No such filter: ass` (macOS)

Pausio usa il filtro `ass` di FFmpeg (compilato con `libass`) per
imprimere i sottotitoli, in preview e nell'export. La build Homebrew
`ffmpeg` 9.0.x può essere priva di questo filtro anche quando
`ffmpeg -version` funziona. Installa **ffmpeg-full** (keg-only) senza
sostituire globalmente la versione standard:

```bash
brew install ffmpeg-full
export PATH="$(brew --prefix ffmpeg-full)/bin:$PATH"
which ffmpeg
ffmpeg -hide_banner -filters | grep ' ass '
pausio doctor
pausio studio
```

Chiudi prima il processo `pausio studio` avviato con il vecchio
`PATH`. Usa lo stesso terminale, con il `.venv` esistente: nessun
nuovo virtualenv è necessario. `pausio doctor` ora restituisce
`captions_ass: false` e istruzioni utili se manca il filtro;
il render con sottotitoli fallisce *prima* di eseguire FFmpeg
con un errore comprensibile. Senza sottotitoli questo filtro non serve.

## Pausio Capture su PC e telefono (verticale 9:16)

Usa **lo stesso recorder** su desktop e smartphone con anteprima 9:16, gobbo
sovrapposto soltanto nell'interfaccia, scelta di webcam/microfono, monitoraggio
audio e salvataggio del take. Su PC una webcam 16:9 viene **realmente ritagliata**
in 9:16 prima di MediaRecorder tramite canvas; un semplice `object-fit:cover`
non basterebbe. Il crop è regolabile (orizzontale, verticale e zoom) e puoi
scegliere 540×960, 720×1280 o 1080×1920 come dimensione di composizione.
La qualità ottica effettiva dipende comunque dai pixel della webcam.

Sul Mac, dal **repository e virtualenv già esistenti**:
```bash
source .venv/bin/activate
pausio studio
# Apri http://127.0.0.1:8765/capture (o la porta stampata)
```

Dopo la registrazione premi **Scarica video** oppure, soltanto sulla pagina
servita da Pausio Studio su 127.0.0.1, **Usa questo take in Pausio Studio**.
Quest'ultima azione chiede conferma se stai sostituendo un progetto e utilizza
l'API locale esistente. Sul sito statico HTTPS GitHub Pages si scarica il file,
senza comunicazione con un server Mac. Il file può essere MP4 oppure WebM
secondo il supporto browser; controlla audio, dimensioni e codec sul take reale.

## Registra dal telefono con il gobbo (Mobile Capture, in sviluppo)

È disponibile una **pagina web mobile indipendente** per registrare video parlati con teleprompter. Il copione rimane visibile sul display ma **non compare nel video**. Dopo ogni take puoi guardare l'anteprima, **scaricare il file sul telefono** o usare la condivisione di sistema quando disponibile; poi lo trasferisci sul PC e lo importi in Studio.

- Da Pausio Studio sul Mac: apri **Registra con gobbo** oppure `http://127.0.0.1:8765/capture` (porta effettiva riportata nel terminale).
- Da smartphone: una volta attivato il deploy GitHub Pages da `main`, apri `https://daniele21.github.io/pausio/` in **HTTPS**. Il server locale Mac non è accessibile dal telefono e non va esposto in LAN.
- Il filmato registrato è un **originale** MP4 o WebM secondo il browser, non un render già montato; il download richiede conferma nell'app File/Download prima di chiudere la pagina. Non vengono eseguiti upload, pairing, sincronizzazioni o rendering cloud.

La funzione resta da validare su Safari iOS e Samsung A56 reali. Consulta [Mobile Capture: guida, privacy, deploy e test](docs/MOBILE_CAPTURE.md).

## Pausio Studio — interfaccia per test reali

Un editor web locale senza npm, cloud o account. L'area di lavoro offre anteprima 9:16, **waveform reale, zoom timeline, maniglie di trim modificabili con mouse/tastiera, preview FFmpeg a 540×960**, trascrizione locale MLX Whisper opzionale, **sottotitoli editabili nel video**, e download MP4.

```bash
brew install ffmpeg
git clone https://github.com/daniele21/pausio.git
cd pausio
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
pausio studio
```

Il browser si apre su **http://127.0.0.1:8765** quando la porta è libera. Se è occupata da un altro servizio, Studio prova automaticamente **8766, 8767, ...**, senza terminare il processo esistente; il terminale mostra l'indirizzo effettivo e il browser apre quello corretto. Puoi scegliere la porta iniziale con `pausio studio --port 8877 --no-open`. Il blocco di sicurezza della cartella della sessione resta attivo: una seconda istanza non può usare contemporaneamente gli stessi dati locali. Il server usa solo loopback e **salva automaticamente la sessione sul Mac**, inclusa la trascrizione completa (con timestamp, modello e lingua) e una copia privata del video importato, per permettere il recupero dopo la chiusura o un'interruzione. La sezione Progetto offre **Annulla / Ripeti**, scorciatoie ⌘Z / ⌘⇧Z e **Elimina dati locali**. Il percorso predefinito su macOS è `~/Library/Application Support/Pausio/Studio`; puoi personalizzarlo con `pausio studio --data-dir /percorso/privato`. Chiudere Pausio **non elimina** il video salvato: usa esplicitamente «Elimina dati locali» per rimuoverlo. **Importa progetto / Esporta progetto** salva o ricostruisce i tagli come comandi versionati in un file `.pausio.json` **v2**, senza includere il video. I file v1 sono importabili e vengono convertiti automaticamente in memoria. Undo/Redo conserva l'eventuale cronologia futura nel progetto portabile. Reimporta prima il video originale: il sistema verifica il suo SHA-256. Supporta MP4/MOV/MKV/WebM fino a 2 GiB. Importa, analizza le pause, rivedi gli intervalli da mantenere, **conferma il montaggio** ed esporta.

La modalità **Simulazione** salta tra gli intervalli dell'originale, e può essere imprecisa. Con **Genera preview** produci invece un MP4 a 540×960 tramite lo stesso pipeline FFmpeg dell'export finale per ascoltare e verificare gli stacchi, prima di confermare il montaggio. Le maniglie sulla timeline salvano modifiche strutturate nel progetto e invalidano la preview precedente. La riproduzione nel browser richiede codec compatibili (consigliato MP4 H.264). La trascrizione usa un motore MLX Whisper indipendente, con pacchetti opzionali e download dei modelli solo con consenso. Restano da costruire audio cleanup e tagli semantici.

Vedi [Guida Pausio Studio](docs/STUDIO_UI.md) per workflow, shortcut, privacy e limiti.

## Quickstart

Requires Python 3.11+, FFmpeg and FFprobe executables on PATH (on macOS: `brew install ffmpeg`).

```bash
git clone https://github.com/daniele21/pausio.git
cd pausio
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
pausio doctor
pausio inspect video.mp4
pausio plan video.mp4 -o plan.json
# Optional on Apple Silicon: python -m pip install -e '.[asr]'
pausio transcribe video.mp4 -o outputs/video.transcript.json
# Review and edit the JSON keep segments first.
pausio render plan.json -o final.mp4
```

The edit plan stores versioned integer-millisecond KEEP intervals. Editing decisions remain reversible; source video is never overwritten. Exports are padded 9:16, 30 fps H.264/AAC MP4. Use `pausio render plan.json -o final.mp4 --dry-run` to inspect the FFmpeg command.

## Transcription: standalone Pausio ASR (no ClosedRoom required)

Pausio runs **MLX Whisper directly on Apple Silicon** using an independent, optional local ASR module inspired by ClosedRoom's design. No running ClosedRoom app, localhost ASR server or cloud account is needed.

```bash
# Use Python 3.12 on Apple Silicon for the best-tested setup:
python -m pip install -e '.[asr]'

# Offline by default: requires a previously downloaded cached model.
pausio transcribe video.mp4 -o outputs/video.transcript.json

# Explicitly authorize downloading an uncached MLX model from Hugging Face:
pausio transcribe video.mp4 -o outputs/video.transcript.json --allow-model-download
```

In Studio choose the model and language under **Trascrizione locale**, click **Trascrivi il parlato**, and, if weights are absent, check **Scarica il modello se assente** and confirm the prompt. Only the model weights may be downloaded with consent; **no video or audio leaves your Mac**. The default model Large v3 Turbo is approximately 1.6 GB. Segment and word timestamps are stored in a private local autosave checkpoint associated with the imported media SHA-256. They reappear on restart without rerunning ASR, and can generate edited captions. The portable project intentionally excludes the raw ASR transcript. Python 3.15 compatibility and real A56 footage are not yet validated. See [local ASR guide](docs/LOCAL_ASR.md).

## Aggiungere sottotitoli al video

Dopo **Trascrivi il parlato**, apri **Trascrizione** → **+ Aggiungi sottotitoli**. Seleziona **Social**, **Minimal** o **Riquadro**. Espandi **Posizione e aspetto** per scegliere il **font** (Arial, Helvetica Neue, Avenir Next, Verdana, Georgia, Courier New, Impact o Times New Roman), oltre a posizione X/Y, dimensione, colore, contorno e sfondo. Puoi usare **Sposta sull'anteprima** per trascinare il testo o le frecce della tastiera (⇧ per 5%). Ogni impostazione modifica tutto il track dei sottotitoli, resta nel progetto ed è riproducibile nell'export. Correggi ciascuna frase con **Salva testo**, e controlla la sovrimpressione in Originale o Simulazione. Poi usa **Genera preview** per il vero video con sottotitoli impressi, **Conferma montaggio**, **Esporta MP4**. I sottotitoli seguono i tagli del montaggio (anche con due segmenti separati) e restano come istruzioni importabili/esportabili e annullabili nel progetto.

I font sono riferimenti a famiglie installate sul sistema, **non** vengono incorporati nei file o scaricati: se un font manca, libass può sostituirlo. Usa **Genera preview** per verificare l'aspetto reale prima dell'esportazione. Il progetto `.pausio.json` conserva la selezione del font e i vecchi progetti senza questa proprietà continuano ad usare Arial. Per l'export FFmpeg deve includere la libreria **libass**. Lo stile va validato su video reali e rispetto agli elementi UI delle piattaforme social; non è ancora disponibile l'export SRT separato.

## Project principles

- Preserve natural cadence rather than removing all silence.
- Local-first; no implicit uploads, telemetry or model downloads.
- Keep raw media immutable; inspect the plan before rendering.
- Separate domain/policy from external media and ML adapters.
- Tests and human media review are needed before claiming quality.

## Developer setup

```bash
python -m pip install -e .
python scripts/validate_skills.py
python -m unittest discover -s tests -v
python -m compileall -q src
```

CI tests Python 3.11–3.13 and synthetic FFmpeg E2E cases. Real Galaxy A56 footage, VFR sync, subtitle readability and editorial naturalness still require real-media evaluation.

### Agent skills for contributors

Pausio ships **thirteen task-specific Agent Skills** under [`.agents/skills/`](.agents/skills/README.md), covering Python architecture, FFmpeg, natural editing, local speech AI, subtitles, test engineering, security/releases and PR review. Read [`AGENTS.md`](AGENTS.md) for repo invariants and [`docs/AGENT_SKILLS.md`](docs/AGENT_SKILLS.md) for task triggers, agent compatibility, source references, validation and evaluation prompts.

These are guidance for coding agents. Pausio owns optional on-device ASR; weights download only after explicit opt-in.

## Current modules and documentation

- `src/pausio/domain.py`: validated immutable edit-plan model.
- `src/pausio/planner.py`: deterministic AI Natural cut policy.
- `src/pausio/media.py`: FFprobe / FFmpeg adapters.
- `src/pausio/local_asr.py`: independent local MLX Whisper engine, offline-first model resolver.
- `src/pausio/project_commands.py`: registro di istruzioni, Undo/Redo e formato portabile v2.
- `src/pausio/studio_persistence.py`: checkpoint atomici, autosalvataggio privato e recupero dopo crash.
- `src/pausio/cli.py`: `studio`, `doctor`, `inspect`, `plan`, `transcribe`, `render`.
- [Architecture](docs/ARCHITECTURE.md) · [Decisions](docs/DECISIONS.md) · [Roadmap](docs/ROADMAP.md) · [Dependencies/licensing](docs/DEPENDENCIES.md).

The source-license decision remains open: public repository visibility does not automatically grant reuse rights. See `docs/DEPENDENCIES.md`.

## Effetti audio personalizzati (riser, whoosh, impact)

Dopo aver importato il video in Studio, apri **Effetti audio** sotto la timeline e clicca **+ Importa audio**. Sono supportati MP3, WAV, M4A, AAC, FLAC e OGG fino a 60 MB e 3 minuti. L'effetto viene posizionato per terminare sul playhead quando possibile. Puoi modificare l'inizio e il volume in dB, ascoltare il file isolato e rimuoverlo. **Genera preview** applica il mixing FFmpeg, come l'export MP4; la sola simulazione dei tagli non contiene il mix finale. Ogni azione produce un comando importabile/esportabile e annullabile. I file audio sono copiati e conservati privatamente sul Mac, ma **non inclusi** nel `.pausio.json`: trasferendo il progetto devi reimportare gli audio originali, riconosciuti per SHA-256. Se mancano, il render viene bloccato; **Elimina dati locali** elimina anche questi file.


### Regola il volume di voce e riser

Nel **Mixer audio** sotto la timeline trovi due slider, **Voce originale** e **Effetti FX**, ciascuno con percentuale, dB, pulsante **Silenzia** e reset. Puoi inoltre modificare il volume di ogni riser con il relativo slider, silenziarlo individualmente o ripristinarlo a -12 dB. Le modifiche si ascoltano mentre il video viene riprodotto e vengono applicate al rendering FFmpeg. Tutti i parametri del mixer vengono registrati come istruzioni esportabili/importabili e annullabili. In modalità **Preview FFmpeg** il suono è già incorporato nel video: regolando un livello si ritorna all'ascolto live finché non rigeneri la preview.
