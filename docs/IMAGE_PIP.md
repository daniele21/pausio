# B-roll con immagini e Picture-in-Picture — progetto v7

## Utilizzo

1. Apri Pausio Studio, importa un video e prepara il montaggio con **Tagli AI**.
2. Apri **B-roll** nella navigazione principale, posiziona il cursore e premi **Aggiungi immagine al cursore**. Seleziona un PNG, JPG o WebP.
3. La scheda mostra **inizio e fine nel video montato**. La traccia B-roll sulla timeline originale visualizza ogni intervallo sorgente effettivamente mantenuto: se l'immagine attraversa un taglio, compare in più pezzi visivi ma rimane una sola istruzione. Clicca un pezzo oppure **Vai al punto** per raggiungere l'elemento. Apri **Regola tempi, dimensione e posizione** per effettuare modifiche reversibili (0,4–12 secondi, dimensione e X/Y).
4. Premi **Guarda 5 s** sulla singola immagine per verificare immediatamente il clip montato con FFmpeg, anche senza preview completa precedente. La preview completa si trova nella timeline con **Genera preview**; non c'è una seconda pipeline. Le immagini sono impresse dopo gli zoom, ma sotto sottotitoli e card testuali. Conferma il montaggio per esportare l'MP4.
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

## Limiti UX attuali

La traccia B-roll mostra posizioni e durata, **non una composizione CSS live**: in Originale/Simulazione l'immagine non è impressa nel player. Usa **Guarda 5 s** per la resa reale. La barra del tempo è in coordinate sorgente, le proprietà sono in coordinate del montaggio: le conversioni attraversano solo i segmenti KEEP. Il supporto a clip B-roll video rimane separato, non va confuso con immagini PIP.
