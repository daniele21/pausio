# Pilotare Pausio con ChatGPT: primo test reale (MCP locale)

## Stato, senza promesse automatiche

Pausio ha un MCP **stdio locale** che può controllare il progetto aperto in
Studio. La chat decide le scelte editoriali: Pausio registra istruzioni
deterministiche e le renderizza con FFmpeg, senza un secondo LLM. La disponibilità
della connessione dipende dal **client ChatGPT** e dalle autorizzazioni dell'account.

Al momento **ChatGPT browser non legge il localhost del Mac** e non basta
aprire una chat per avere accesso a questi strumenti. Un client MCP locale che
supporti stdio può usarli direttamente; per ChatGPT cloud è necessario un
collegamento autorizzato, per esempio Secure MCP Tunnel quando disponibile.

## Che cosa è davvero esposto al modello

Chiama prima `pausio_get_capabilities`, quindi `pausio_get_project`.
Il progetto include revisione, media SHA, montaggio, sottotitoli, grafiche,
immagini importate, camera FX, transizioni e audio. La trascrizione non è
restituita con il progetto: si richiede separatamente usando
`pausio_get_transcript` (il testo sarà condiviso con il client di chat).

Il connettore espone questi flussi:
- Analisi pause e trascrizione locale (modello già nella cache; senza download).
- Suggerimenti tecnici zoom e regia editoriale non mutanti.
- Modifica di tagli, sottotitoli, card grafiche, effetti camera, transizioni,
  mixer e parametri delle immagini **già importate**, usando esattamente
  `pausio_apply_command` con revisione corrente.
- Preview completa e `pausio_preview_range` (250–10000 ms di video **montato**).
- `pausio_render_approved_video`: avvia il render finale **solo** dopo che
  l'utente ha confermato il montaggio nella UI. Il risultato rimane sul Mac.

**Non ancora esposti:** caricamento del video o di nuovi asset dal client di
chat, preview visive di frame per il modello, download dei byte MP4 in chat,
ricerca B-roll, video B-roll MP4/MOV, approvazione senza utente, server MCP
remoto pubblico. Il bridge non crea immagini o musica.

## Test rapido, senza cloud e senza chiave LLM

1. Aggiorna Pausio dal repo e avvia Studio nel terminale:

   ~~~bash
   git pull --ff-only origin main
   source .venv/bin/activate
   python -m pip install -e .
   pausio studio --port 8765
   ~~~

   Se Studio sceglie un'altra porta, usa quella reale nei passaggi successivi.
   Importa un video e genera il montaggio nella UI; per provare gli effetti
   verbali crea anche una trascrizione.

2. In un secondo terminale, verifica l'handshake MCP, senza ChatGPT:

   ~~~bash
   source .venv/bin/activate
   python -m unittest tests.test_local_mcp -v
   printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | pausio mcp --studio-port 8765
   ~~~

   La seconda risposta deve avere `tools` con, fra gli altri,
   `pausio_get_capabilities`, `pausio_apply_command`,
   `pausio_preview_range` e `pausio_render_approved_video`.
   Questa prova verifica il **bridge**, non un collegamento ChatGPT completato.

3. Per un client desktop che supporta MCP stdio (es. Claude Desktop), registra
   come `command` il binario assoluto `.../pausio/.venv/bin/pausio`
   e come `args` `["mcp","--studio-port","8765"]`. Usa la stessa porta
   dell'istanza Studio attiva. Autorizza solo le modifiche desiderate.

4. **ChatGPT via MCP cloud:** in ChatGPT Plugins aggiungi un server MCP
   personalizzato **solo se la funzione è disponibile** nel tuo account.
   Se possibile usa *Connection: Tunnel* e il
   [Secure MCP Tunnel ufficiale](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
   associato al workspace corretto. Il tunnel si connette al nostro processo
   locale stdio e non pubblica la porta Studio; richiede autorizzazioni e
   una **chiave tecnica di runtime Platform** (non una chiave per chiamare
   GPT come modello), quindi non è un setup completamente senza chiavi.
   NON aprire una porta pubblica, usare un tunnel anonimo o esporre direttamente
   le API Studio. Non promettere che il piano ChatGPT o il client in uso
   supportino la scrittura fino a un vero tool-call di prova.

## Prompt per il primo esperimento con un client MCP collegato

> Usa Pausio per montare un video divulgativo naturale e professionale. Prima
> controlla `pausio_get_capabilities`, `pausio_get_project` e, se presente,
> `pausio_get_transcript`. Non inventare scene, parole o timestamp. Proponi
> selettivamente sottotitoli, massimo due zoom utili e una scheda di riepilogo
> se il contenuto lo giustifica. Spiega ogni modifica prima di usare
> `pausio_apply_command`; applica una modifica per volta con la revisione
> aggiornata, poi genera una preview breve del punto interessato. Non chiedere
> di scaricare modelli o importare nuovi asset; non approvare il montaggio.
> Quando ho verificato personalmente la preview e confermato il montaggio in
> Studio, puoi avviare il rendering finale e dirmi dove scaricarlo nella UI.

## Sicurezza e limiti del primo pilota

- `pausio_apply_command` inoltra **solo** eventi tipizzati allowlisted e il
  reducer Studio valida payload e revisione. Nessun path arbitrario o
  esecuzione di shell. Audio/video grezzi non passano dal MCP.
- Tool di lettura esplicita della trascrizione: prima di invocarlo, considera
  che le parole possono raggiungere il provider della chat.
- Un tool MCP non equivale ad aver visto fotogrammi: per una regia affidabile
  bisognerà aggiungere osservazioni visuali bounded (storyboard e frame).
- Qualsiasi modifica toglie l'approvazione, invalidando il precedente render;
  l'utente mantiene Undo/Redo e il download dalla UI.
- Non affermare che un test ChatGPT+Mac è passato senza una vera sessione
  connected-to-server e una chiamata documentata a `tools/call`.
