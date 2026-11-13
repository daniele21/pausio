# Pausio Studio — anteprima rapida dell'intervallo montato

Pausa il video sul punto da controllare e premi **Clip 5 s** dopo aver preparato il montaggio. Non serve più renderizzare prima tutta la preview.

- Se una preview FFmpeg completa è aggiornata, il clip viene estratto dal file già renderizzato: percorso più veloce.
- Altrimenti Pausio renderizza direttamente **solo l'intervallo output richiesto** dalla stessa composizione FFmpeg di export e preview, inclusi KEEP, movimenti camera, transizioni, grafiche, sottotitoli, immagini PIP e audio. La composizione è tagliata in uscita, così non viene creato un MP4 completo. Per clip vicini alla fine del video, FFmpeg può comunque dover elaborare i frame precedenti; questa versione non fa ancora seeking anticipato sui singoli segmenti sorgente.
- I parametri sono in millisecondi di **timeline montata**, non di sorgente. Il range è 250 ms–10 s; niente sovrascrittura dell'originale e nessun upload.
- Un unico job locale alla volta, 300 s di timeout per il rendering diretto, publish atomico e cache per intervallo del progetto corrente. Le modifiche al progetto invalidano il file range e la preview completa.
- Endpoint `POST /api/jobs` con `kind=preview_range`, `range_start_ms` e `range_duration_ms`; la stessa protezione Host/Origin del resto di Studio.

Il player del dialog è separato dal player principale. Le azioni non alterano il tape di comandi o l'approvazione del montaggio.

**Verifica**: test Python dry-run e FFmpeg con audio, HTTP prima/dopo render completo, cache e invalidazione; Playwright di apertura e chiusura su Studio. I test sintetici non sostituiscono la revisione di un vero video registrato su smartphone.
