# Pausio

**Edit the noise. Keep the voice.**

A local-first toolkit for natural-sounding, talking-head social videos. Pausio is designed to make post-production **reviewable**, not fully automatic at the expense of speech or pacing.

> **Status: early foundation (v0.1.0).** The current CLI inspects videos, suggests cuts using FFmpeg's signal-level silence detection, writes a human-editable JSON timeline, and exports a vertical 1080x1920 MP4. It can now request a transcript from the **existing, separately running ClosedRoom local ASR service**, but does not yet make semantic cuts, generate subtitles, denoise or export CapCut projects.

## Pausio Studio — interfaccia per test reali

Un editor web locale senza npm, cloud o account. L'area di lavoro offre anteprima 9:16, timeline dei tagli, intervalli modificabili, trascrizione ClosedRoom opzionale e download MP4.

```bash
brew install ffmpeg
git clone https://github.com/daniele21/pausio.git
cd pausio
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
pausio studio
```

Il browser si apre su **http://127.0.0.1:8765**. Altre opzioni: `pausio studio --port 8877 --no-open`. Il server usa solo loopback e **salva automaticamente la sessione sul Mac**, inclusa una copia privata del video importato, per permettere il recupero dopo la chiusura o un'interruzione. La sezione Progetto offre **Annulla / Ripeti**, scorciatoie ⌘Z / ⌘⇧Z e **Elimina dati locali**. Il percorso predefinito su macOS è `~/Library/Application Support/Pausio/Studio`; puoi personalizzarlo con `pausio studio --data-dir /percorso/privato`. Chiudere Pausio **non elimina** il video salvato: usa esplicitamente «Elimina dati locali» per rimuoverlo. **Importa progetto / Esporta progetto** salva o ricostruisce i tagli come comandi versionati in un file `.pausio.json` **v2**, senza includere il video. I file v1 sono importabili e vengono convertiti automaticamente in memoria. Undo/Redo conserva l'eventuale cronologia futura nel progetto portabile. Reimporta prima il video originale: il sistema verifica il suo SHA-256. Supporta MP4/MOV/MKV/WebM fino a 2 GiB. Importa, analizza le pause, rivedi gli intervalli da mantenere, **conferma il montaggio** ed esporta.

La preview "Montaggio" simula i tagli tramite seek tra gli intervalli dell'originale: non è frame-accurate né sostituisce il controllo del MP4 finale. La riproduzione nel browser richiede codec compatibili (consigliato MP4 H.264). La trascrizione richiede ClosedRoom già in esecuzione. Restano da costruire sottotitoli, audio cleanup, waveform e tagli semantici.

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
# Optional: ClosedRoom local server must already be running on 127.0.0.1:1236
pausio transcribe video.mp4 -o outputs/video.transcript.json
# Review and edit the JSON keep segments first.
pausio render plan.json -o final.mp4
```

The edit plan stores versioned integer-millisecond KEEP intervals. Editing decisions remain reversible; source video is never overwritten. Exports are padded 9:16, 30 fps H.264/AAC MP4. Use `pausio render plan.json -o final.mp4 --dry-run` to inspect the FFmpeg command.

## Transcription: reuse ClosedRoom, do not rebuild ASR

[ClosedRoom](https://github.com/daniele21/closedroom) already implements on-device MLX Whisper/Nemotron, VAD, model management, cache and transcription. Pausio only calls the **same-machine local API** on `127.0.0.1:1236` and adapts its response for editing. The integration follows the ClosedRoom `dev` endpoint `POST /v1/audio/transcriptions/path`.

```bash
# Start the existing ClosedRoom server using its own repository instructions.
pausio transcribe video.mp4 -o outputs/video.transcript.json
# Optional: --model mlx-community/whisper-large-v3-turbo
# Optional: --closedroom-url http://127.0.0.1:1236
```

Pausio uses FFmpeg to extract a temporary mono WAV, requests ClosedRoom's `verbose_json` response with `asr_provider=local`, normalizes segments and available word timestamps to **source-time milliseconds**, and deletes the temporary audio. It rejects non-loopback destinations and HTTP redirects. No model is installed or started automatically by Pausio. Pre-provision your desired ClosedRoom model to avoid unexpected upstream download behavior.

The output is a separate reviewable transcript JSON, **not yet wired into cut decisions or subtitle rendering**. If ClosedRoom returns no word-level alignment, the sidecar reports `word_timestamps_available: false`; it never invents word timings. A live ClosedRoom integration test with real recordings is still outstanding. See [ClosedRoom integration](docs/CLOSEDROOM_INTEGRATION.md).

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

These are guidance for coding agents, not runtime features. ClosedRoom is the sole ASR implementation; the optional local adapter does not install any transcription models.

## Current modules and documentation

- `src/pausio/domain.py`: validated immutable edit-plan model.
- `src/pausio/planner.py`: deterministic AI Natural cut policy.
- `src/pausio/media.py`: FFprobe / FFmpeg adapters.
- `src/pausio/closedroom_asr.py`: existing ClosedRoom ASR API integration; no duplicate model stack.
- `src/pausio/project_commands.py`: registro di istruzioni, Undo/Redo e formato portabile v2.
- `src/pausio/studio_persistence.py`: checkpoint atomici, autosalvataggio privato e recupero dopo crash.
- `src/pausio/cli.py`: `studio`, `doctor`, `inspect`, `plan`, `transcribe`, `render`.
- [Architecture](docs/ARCHITECTURE.md) · [Decisions](docs/DECISIONS.md) · [Roadmap](docs/ROADMAP.md) · [Dependencies/licensing](docs/DEPENDENCIES.md).

The source-license decision remains open: public repository visibility does not automatically grant reuse rights. See `docs/DEPENDENCIES.md`.
