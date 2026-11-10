# Dependencies, upstream inspiration and licensing checklist

The code in this repository is original and does **not** vendor third-party project code. External FFmpeg executables must be installed by the user; FFmpeg license obligations depend on the build flags and linked libraries. Do not assume every FFmpeg binary is distributable under the same terms.

| Technology | Intended role | Integration status | License review before bundling |
| --- | --- | --- | --- |
| [FFmpeg](https://ffmpeg.org/) | Probe, silence detection, render | External executables (required for media commands) | Build-specific LGPL/GPL and codecs |
| [auto-editor](https://github.com/WyattBlue/auto-editor) | Algorithm/design reference for cut workflows | Inspiration only | Inspect current upstream LICENSE before any source reuse |
| [WhisperX](https://github.com/m-bain/whisperX) | Word-aligned transcripts | Future optional adapter | Dependencies/models/cross-platform support |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Local ASR | Future optional adapter | Runtime, model weights and packaging |
| [Silero VAD](https://github.com/snakers4/silero-vad) | Speech activity confidence | Future optional adapter | Check model distribution and transitive licenses |
| [DeepFilterNet](https://github.com/Rikorose/DeepFilterNet) | Audio denoising | Future optional adapter | License and model weights |
| CapCut project manipulation tools | Editable project exporter | Idea only; no dependency | Non-public interchange format, breakage risk, licenses |

## Pausio source license

**Decision pending:** GitHub repository is public but no license was added by default. Public visibility is not equivalent to an open-source license. Before accepting contributions or distributing a compiled app, choose a license deliberately (e.g. permissive vs copyleft vs proprietary) and review dependencies in that context.

## Media and sound effects

Respect rights and privacy for recorded people, screenshot assets, background music and effects (e.g. Pixabay). Keep a provenance record: title, creator, source URL, download date, license snapshot, any attribution obligations. Do not commit media or model weights to Git.
