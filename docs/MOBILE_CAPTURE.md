# Pausio Mobile Capture — gobbo e download sul telefono

## Stato e responsabilità

La pagina `capture.html` è una **webapp statica**, originale, senza dipendenze JS, upload, account o connessioni obbligatorie. È distinta dal server Studio, che resta vincolato a `127.0.0.1` e **non va esposto su Internet o in LAN**.

Il video che scarichi sullo smartphone è il **take registrato originale** con audio, non il montaggio FFmpeg di Pausio. Il gobbo è un overlay HTML della sola anteprima e **non** viene inserito nel filmato. Il montaggio, i sottotitoli e il render finale si eseguono successivamente in Pausio Studio sul computer.

## Flusso per un creator

1. Apri `https://daniele21.github.io/pausio/` dal telefono **dopo** la pubblicazione GitHub Pages (la funzione non richiede Pausio installato sul telefono).
2. Incolla o modifica lo script, scegli velocità, dimensione, posizione.
3. Attiva fotocamera e microfono, controlla l'inquadratura e tocca **Registra**.
4. Dopo il countdown leggi il gobbo, premi **Termina registrazione**.
5. Guarda l'anteprima, premi **Scarica video**; su Safari usa anche **Condividi / Salva su File**, se disponibile.
6. **Verifica** che il video sia presente nell'app File/Download prima di chiudere la pagina; trasferiscilo sul PC con il metodo che preferisci (USB, AirDrop, Files/Drive, ecc.).
7. In Pausio Studio premi **Importa video** e seleziona il file MP4/WebM scaricato. La webapp non trasferisce automaticamente il take al Mac.

## Distribuzione HTTPS

Il workflow `.github/workflows/mobile-capture-pages.yml` pubblica solamente i tre asset statici `capture.html`, `capture.css`, `capture.js` da `main` tramite GitHub Pages. Per attivarlo: nella pagina GitHub del repository vai in **Settings → Pages → Build and deployment → GitHub Actions**, poi esegui il workflow o pubblica una modifica su `main`. Non esporre il server Python di Studio: la versione statica permette a iPhone/Android di usare `getUserMedia` su HTTPS senza accesso al Mac.

Per test locale desktop, avvia `pausio studio` e apri `http://127.0.0.1:8765/capture` (o la porta comunicata da Pausio). `localhost` è un contesto sicuro, ma lo stesso URL **non funziona** su un telefono diverso. Verifica sempre la disponibilità del Pages URL prima di condividerlo.

## Layout mobile e video verticale (sorgenti Android orizzontali)

Un browser Android può consegnare una sorgente fotocamera `1920×1080` (16:9 orizzontale) **anche con il telefono in verticale** e con `aspectRatio: {ideal: 9/16}`. I vincoli `ideal` sono preferenze, non garantiscono il formato: prima questa discrepanza produceva una fascia orizzontale nell'anteprima, mentre MediaRecorder scaricava il video orizzontale.

Pausio ora disegna i frame della fotocamera (mai il gobbo DOM) su un canvas **720×1280 (9:16)**: l'anteprima mostra questo canvas e il file video usa `canvas.captureStream(24)` + la traccia microfono originale in `MediaRecorder`. La camera resta la fonte di verità; il browser decide il container MP4/WebM. Il video risultante è verticale anche se l'ingresso è 16:9 orizzontale, **quando il browser supporta la cattura del canvas**. Se manca questo supporto, l'interfaccia mostra un errore anziché salvare silenziosamente un file orizzontale.

- **Verticale 9:16 · campo completo (default):** mostra l'intero fotogramma della fotocamera con uno sfondo sfocato ricavato dallo stesso video, senza tagliare i lati. Se la sorgente è orizzontale, il contenuto principale mantiene le sue proporzioni e si vedrà una fascia panoramica sopra lo sfondo sfocato. Non è uno zoom ottico.
- **Verticale 9:16 · schermo pieno (ritaglio):** riempie tutta l'altezza e larghezza del file verticale con un crop centrale. Non lascia bande ma necessariamente ritaglia una parte notevole dei lati di una sorgente 16:9, quindi l'immagine può apparire più ravvicinata.
- L'opzione cambia la composizione di anteprima e file **insieme**; non ruota il volto sideways e non imprime il gobbo sul video. Il canvas rimane non specchiato nel file, mentre la preview selfie è specchiata solo tramite CSS.
- Le impostazioni del gobbo restano esportate come preferenze locali; il pannello è collassabile su mobile e il gobbo mostra da 3 a 7 righe.

**Qualità/performance:** questa composizione iniziale esporta HD 720×1280 a 24 fps, non Full HD nativo; il canvas e l'effetto sfocatura possono consumare CPU e batteria. Provare la qualità su Galaxy A56, Safari iOS e microfono esterno prima di considerare la funzione production-ready. Per ottenere contemporaneamente **campo visivo più ampio e pieno schermo 9:16** senza sfondo, occorre una sorgente camera realmente verticale o un'ottica più ampia: il browser non può ricostruire pixel fuori dall'inquadratura.

## Compatibilità e limiti

- Browser: Safari iOS recente e Chrome Android recente, previa autorizzazione fotocamera+microfono. L'app non garantisce supporto su browser vecchi o embedded. MediaRecorder sceglie MP4 dove disponibile, altrimenti WebM; Pausio Studio importa entrambi, ma alcuni player di sistema non riproducono WebM.
- La richiesta `width/height/frameRate` è una **preferenza**: la sorgente può essere orizzontale. Se il canvas è supportato, Pausio registra una composizione HD 720×1280 verticale; verificare con FFprobe i metadati e l'audio dopo il download.
- Il microfono esterno è selezionato dal sistema operativo/browser. Controllare audio e sincronia su hardware reale. Le videocamere anteriori possono mostrare l'anteprima specchiata; l'effetto è solo CSS, non un filtro del video registrato.
- Non bloccare il display o passare ad altre app durante la registrazione: i sistemi mobili possono interrompere capture/MediaRecorder. Preferire take brevi (1–3 minuti); i blob sono mantenuti in memoria fino al download e una navigazione/refresh può far perdere il video.
- Il testo e le impostazioni del gobbo si conservano localmente in `localStorage` quando disponibile. **Le registrazioni non si salvano automaticamente**, non vengono inviate ad alcun server e non restano disponibili dopo aver chiuso/ricaricato la pagina. Il download è un'azione esplicita.
- Alcuni Safari ignorano `<a download>` sui blob o mostrano un player. In tal caso usa il pulsante Share Sheet per **Salva su File** (quando offerto); verifica che il file sia salvato. Mai dichiarare salvato un file senza una verifica visiva.
- La PWA installabile e i take persistenti (OPFS/IndexedDB a chunk) sono fasi successive: servono test su limiti storage, eviction, interruzione e ripresa.
- Questa prima fase non implementa ASR voice-follow, pairing, sincronizzazione col desktop, editing mobile, rendering FFmpeg o final MP4 garantito.

## QA richiesta prima della release

Playwright Chromium: 320 e 390px senza overflow, device simulato, permessi, camera, countdown, registrazione, preview e download non vuoto; Safari iOS reale e Samsung Galaxy A56 reale: file apribile, rotazione verticale, format/container coerente, audio udibile, nessun gobbo nel video, salvataggio in File/Download, perdita permesso, interruzione da blocco schermo, compatibilità microfono esterno. Il test browser fake-media verifica API e download, non la qualità ottica o i codec su hardware reale.
