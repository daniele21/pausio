# Regia assistita v1 — proposte locali, motivabili e reversibili

## Prima versione

La nuova area **Video FX → Regia assistita** propone interventi coordinati per video parlati. Scelta fra tre profili:

- **Clean Tech** — grafica rara, movimenti minimi.
- **Educational** — dati e codice evidenziati, zoom moderati.
- **Dynamic Social** — una densità massima leggermente più alta, comunque limitata.

Nessun effetto viene applicato automaticamente. Ogni proposta mostra **evidenza concreta**: una frase dei sottotitoli revisionati contenente un numero, un nome file o un suggerimento, oppure un segnale temporale tecnico già usato dal motore Video FX. Premi **Accetta** per creare un vero comando `graphic.overlay.add` oppure `video.transform.add`, mantenendo Undo/Redo, import/export v7, revisione del progetto, preview ed export FFmpeg; premi **Ignora** per scartare la proposta. Una modifica invalida l'elenco precedente, così non si applicano suggerimenti riferiti a un montaggio vecchio.

## Principi di regia

- Se non ci sono sottotitoli revisionati, Pausio **non inventa dati o testi** e può proporre solo gli zoom supportati dai segnali tecnici disponibili.
- Le schede derivano da **testo letteralmente presente** nei sottotitoli: dati numerici, file tecnici e passaggi pratici. Non costituiscono una verifica esterna della veridicità della frase.
- Massimo otto schede e otto zoom candidati per tipo prima dell'ulteriore filtraggio del profilo; distanza minima configurata dal profilo fra interventi della stessa famiglia e separazione fra scheda e zoom. Gli effetti manuali esistenti hanno precedenza.
- Il motore è **deterministico e senza cloud**. Non usa chiavi API, LLM, telemetria, download di asset o esecuzione di istruzioni di testo.
- Non sostituisce il ragionamento di ChatGPT/Claude Chat. Il successivo livello agentico potrà usare lo stesso catalogo di comandi tipizzati con approvazioni, senza eseguire codice non attendibile.

## Limiti espliciti

Questa versione **non** comprende comprensione semantica affidabile, analisi dello storyboard da parte di un LLM, B-roll video scelto automaticamente, animazioni layer avanzate, oggetti mascherati, tracking continuo o un comando *Approva tutto*. La presenza di un numero nel parlato non prova che il dato sia corretto.

La UI è una superficie di revisione, non un secondo motore di montaggio. Preview di un effetto: genera la preview FFmpeg completa, quindi usa la clip rapida di 5 secondi per riascoltarlo.

## Contratto API

`POST /api/editorial/suggest` accetta esclusivamente `{"revision": <intero corrente>, "preset": "clean_tech"|"educational"|"dynamic_social"}`. Restituisce `engine`, `base_revision`, `media_sha256`, `total_output_ms`, `approval_required=true`, `missing_signals` e una lista di `candidates`, ciascuno con `candidate_id` stabile, `command_type` supportato, `payload`, `score_0_100`, timestamp output e `evidence`. Il server non muta la cronologia tramite questo endpoint.

Il client accetta ogni proposta attraverso l'endpoint canonico `POST /api/command`; i comandi vengono riprocessati con tutte le validazioni del progetto v7. La risposta di suggerimento non è mai una delega a eseguire script o espressioni FFmpeg libere.
