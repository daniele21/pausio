# Graphic motion v1 — entrata, permanenza e uscita configurabili

**Branch:** `daniele/social-motion-overlay-v1`, in sequenza dopo PR #85 e PR #84.

## Obiettivo

Animare le schede grafiche di Pausio (titolo, metrica, codice, consiglio) con
una grammatica editoriale modulare. **Non** introduce un altro motore di
montaggio, cloud rendering o JavaScript eseguibile nei progetti.

## Comportamento

- Il formato portabile v13 supporta un campo opzionale `motion` su
  `graphic.overlay.add/update`. Se assente restano i preset precedenti,
  senza alterare l'aspetto dei progetti legacy.
- Entrata: none, fade, pop, slide_up, slide_left.
  Uscita: none, fade, shrink, slide_down, slide_right.
- Durate indipendenti: 80–800 ms per animazione attiva, 0 ms quando assente;
  almeno 100 ms di permanenza visibile. Vincoli applicati prima di salvare.
- L'editor Studio permette di attivare il motion avanzato tanto sulle nuove
  schede quanto su quelle già esistenti. La modifica rimane un singolo
  comando versionato, reversibile con Undo/Redo.
- In rendering il compilatore `graphic_motion.py` produce fino a tre
  eventi ASS non sovrapposti (entrata, permanenza, uscita) con tempi
  deterministici sulla timeline **montata**.
- Entrate/uscite slide usano movimenti lineari nativi libass; pop/shrink
  usano interpolazione di scala con accelerazione controllata. La preview
  FFmpeg è il riferimento per posizione, tipografia e transizioni reali.

## Riuso open

- [FableCut](https://github.com/ronak-create/FableCut): riferimento per
  motion parametrico, senza aggiungere il suo renderer alla pipeline.
- [AutoBroll](https://github.com/andriidrok1/autobroll): riferimento per
  timeline e collocazione intenzionale di elementi in/out.

Nessun codice di questi repository è copiato nel progetto.

## Contratto e sicurezza

- `motion` ha solo quattro campi allowlist:
  `enter`, `exit`, `enter_ms`, `exit_ms`.
- Nessun valore arbitrario raggiunge i comandi `\move`, `\fad`, `\t`
  o qualsiasi filtro FFmpeg.
- V13 accetta progetti precedenti v1–v12. I dati restano locali; non ci sono
  API remote o telemetria aggiuntive.
- La preview usa esattamente lo stesso compilatore delle esportazioni;
  l'approvazione finale resta distinta e manuale.

## Test

- `tests/test_graphic_motion.py`: validazione input, versioni legacy,
  intervalli ASS, combinazioni motion e render FFmpeg sintetico con audio.
- `tests/browser/test_studio_playwright.py`: compilazione della UI
  con entrata/uscita, salvataggio, preview reale e Undo.
- CI Python 3.11–3.13, audit Playwright e collaudo macOS su registrazione
  originale devono passare prima del rilascio.

## Non incluso

Motion per immagini/B-roll video, tracking, easing personalizzato dello
spostamento, librerie di asset stock e piano automatico di effetti AI.
Questi elementi vengono dopo la verifica del motion grafico canonico.
