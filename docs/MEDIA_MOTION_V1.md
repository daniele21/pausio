# Media motion v1 — immagini e B-roll video

Branch `daniele/social-media-motion-v1`, dopo PR #86 (schede grafiche),
#85 (word-focus captions), #84 (B-roll video).

## Workflow Studio

- Importa un'immagine o un B-roll video nell'area dedicata.
- Apri **Posizione, taglio e layout** e poi **Animazioni di entrata e uscita**.
- Abilita l'opzione, seleziona separatamente entrata e uscita e la durata
  di ciascuna (80–800 ms).
- Salva: viene creato **un solo evento versionato** `image.overlay.update`
  o `video.broll.update`, con possibilità di Undo/Redo e autosalvataggio.
- Guarda la preview FFmpeg per controllare il movimento reale prima di
  approvare qualsiasi esportazione.

## Preset implementati

Entrata: none, fade, slide_up, slide_left.
Uscita: none, fade, slide_down, slide_right.

La struttura `motion` riusa esattamente la forma introdotta per le schede
grafiche: `enter`, `exit`, `enter_ms`, `exit_ms`. Le opzioni per media
sono intenzionalmente più ristrette: niente pop/shrink per ora, poiché il
resize dinamico di sorgenti video su alcuni backend FFmpeg è fragile.
Almeno 100 ms di permanenza a piena visibilità sono obbligatori.

## Renderer

- Nessun nuovo runtime. Un piccolo modulo `media_motion.py` valida e
  compila soltanto costanti numeriche e preset espliciti.
- Per immagini e video il clip alpha è animato nel **tempo locale** tramite
  fade nativo FFmpeg; poi la sorgente viene posizionata nel **tempo montato**.
- Gli slide usano le espressioni overlay FFmpeg composte dal modulo, senza
  consentire espressioni scritte dall'utente.
- L'audio del B-roll non viene mai mixato; si mantiene la voce originale.
  Le immagini vengono disegnate dopo il B-roll video e prima dei sottotitoli
  e delle schede grafiche, come già nel prodotto.
- Gli inserti senza `motion` conservano il comportamento storico.
- La stessa funzione `render()` alimenta preview parziale, preview intera
  ed export approvato.

## Contratto portabile v14

- Campo `motion` opzionale negli overlay immagine e B-roll video.
- Accettazione delle precedenti versioni, senza introdurre campi obbligatori
  nei vecchi eventi; esportazione in v14.
- Validazione forte di durata, tipi, enum, chiavi e limiti; nessuna URL
  remota o filtro FFmpeg libero; gli asset restano locali con SHA-256.

## Test

- `tests/test_media_layer_motion.py`: replay/undo/redo, sicurezza,
  composizione deterministica e campionamento di fotogrammi video/immagine
  sintetici prima, durante e dopo le transizioni, preservando audio/durata.
- `tests/browser/test_studio_playwright.py`: editor di entrambe le
  tipologie, salvataggio come istruzioni, preview reale e Undo.
- CI su Python 3.11/3.12/3.13 e audit Playwright devono essere verdi.
- Rimane necessaria una verifica di qualità sul Mac locale, con
  registrazione reale e FFmpeg full/libass.

## Ulteriori evoluzioni (non implementate)

Easing di traiettorie personalizzate, pop/shrink dinamici per media,
tracking di soggetti, keyframes liberi, auto-matching di B-roll, libreria
di asset e AI planner in transazioni batch. Queste funzioni non vanno
confuse con quanto effettivamente implementato qui.
