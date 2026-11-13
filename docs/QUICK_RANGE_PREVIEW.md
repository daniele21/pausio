# Pausio Studio — preview rapida della regione montata

## Primo incremento funzionante

Apri un video, genera una preview FFmpeg completa dal progetto **corrente**, posiziona il playhead e clicca **Clip 5 s**. Pausio ritaglia fino a cinque secondi attorno al cursore (timeline output, non sorgente) dalla preview già verificata; apre un player separato, con audio e tutti gli effetti realmente presenti nel video. La clip ha un endpoint locale `GET/HEAD /api/preview/range`, con richieste HTTP Range supportate.

Il clip usa FFmpeg con seeking sul MP4 *già renderizzato*, dunque non deve rifare tagli, motion, transizioni, sottotitoli o mix. La codifica breve è atomica, senza shell e limitata a 0,25–10 secondi. L'intervallo è validato contro la durata totale output. Un'identica richiesta sfrutta la cache locale; cambiare video o qualsiasi comando del progetto invalida cache e URL, e blocca nuove richieste finché non viene prodotta una preview completa della nuova revisione.

**Limite dichiarato:** questo incremento ottimizza la revisione *successiva alla prima preview completa*. Non è ancora un render parziale diretto da sorgente per un progetto che non dispone di una preview valida. Questa seconda fase, più complessa per i confini di KEEP, zoom, musiche e dissolvenze, rimane tracciata in [#65](https://github.com/daniele21/pausio/issues/65); non deve sacrificare la parità con il render completo.

## Sicurezza e UX

- `POST /api/jobs` con `kind=preview_range`, `range_start_ms`, `range_duration_ms` validati, sempre con `X-Pausio-Client` e protezione same-origin.
- Server solo localhost; l'utente non può scegliere path/URL o comandi FFmpeg.
- Il player clip è separato da preview/editor originale, che resta la sorgente di verità.
- Modifiche o reimport invalidano il file. Nessun nuovo artefatto nel JSON portabile; si tratta di un cache di revisione.
- Test: input invalidi, FFmpeg reale, output 540×960, byte-range, HEAD, cache-identical e invalidazione; Playwright dialog e keyboard undo.
