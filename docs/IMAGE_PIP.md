# B-roll con immagini e Picture-in-Picture — progetto v7

## Utilizzo

1. Apri Pausio Studio, importa un video e prepara il montaggio con **Tagli AI**.
2. In **Video FX → B-roll · immagini PIP**, premi **Importa immagine al cursore** e seleziona un PNG, JPG oppure WebP dal Mac.
3. Dopo l'importazione viene creata una scheda PIP ancorata alla timeline **montata** (non al file sorgente). Imposta inizio, durata (0,4–12 secondi), larghezza e posizione X/Y, poi premi **Salva posizione**. Tutte le modifiche sono istruzioni versionate, esportabili e annullabili.
4. Premi **Genera preview FFmpeg con PIP**, poi **Preview FFmpeg**. Le immagini vengono impresse dopo gli zoom, ma sotto sottotitoli e card testuali. Conferma il montaggio per esportare l'MP4.
5. Esporta il progetto `.pausio.json` v7. Il file contiene hash e metadati dei riferimenti, **non contiene i file immagine**. Se riapri il progetto su un dispositivo diverso o hai cancellato la copia privata, importa nuovamente gli stessi byte di immagine per ricollegarla, senza duplicare i comandi.

## Sicurezza e confini

- Solo immagini locali PNG, JPEG, WebP. FFprobe ne controlla il codec, una sola traccia video, 32–4.096 pixel per lato, massimo 12 megapixel e 12 MiB. Il server rifiuta altri formati o file con nome che include percorsi.
- L'upload avviene esclusivamente verso l'istanza Studio di localhost con protezioni same-origin e identificativo client; lettura a blocchi con limite di grandezza e hash SHA-256. I file vengono salvati nella cartella privata della sessione (0600).
- Il progetto non accetta URL, HTML, JavaScript, shader o espressioni FFmpeg arbitrarie. Le trasformazioni vengono costruite esclusivamente con parametri numerici validati.
- Ogni rendering verifica nuovamente l'hash degli asset prima di usarli. Asset mancanti o modificati comportano un errore esplicito, non un risultato parziale silenzioso.
- Fino a quattro immagini per progetto, ciascuna tra 400ms e 12s, larghezza 20–70%, coordinate X/Y 0–100%.
- Non sono ancora supportati video B-roll, keyframe animati dell'immagine, ritagli grafici avanzati, asset bundling, B-roll selezionato automaticamente o un asset manager con anteprime.

## Verifica

Test: replay v7, Undo/Redo, compatibilità vecchi progetti, valori invalidi, hash errati, MP4 FFmpeg con overlay visibile, import locale e retry/relink, preview e UI Playwright. Eseguire inoltre una prova privata con registrazioni reali e schermate sensibili, senza caricarle su GitHub.
