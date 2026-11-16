# Pausio — catalogo tool e guida alla scelta

**Ambito:** tool MCP disponibili nel server locale, comandi di editing autorizzati tramite MCP, comandi CLI e confini con Studio UI.  
**Verificato sul codice di main:** 16 novembre 2026. Questa pagina è una guida d'uso, non una promessa che ogni client ChatGPT/Claude esponga ogni tool.

## 1. Regola fondamentale

Pausio **non è un agente AI autonomo**: il client ChatGPT/Claude valuta contenuto e regia; Pausio è l'editor locale deterministico che controlla revisioni, validazione, preview e rendering. Il girato non viene sovrascritto. Ogni modifica deve essere un comando strutturato e annullabile.

**Fonti di verità:**
- [mcp_tool_catalog.py](../src/pausio/mcp_tool_catalog.py): nomi e input schema dei tool MCP, allowlist di edit e rapporto delle capability.
- [local_mcp.py](../src/pausio/local_mcp.py): esecuzione reale, integrazione con Studio e MCP stdio.
- [project_commands.py](../src/pausio/project_commands.py) e [PROJECT_FORMAT.md](PROJECT_FORMAT.md): semantica e validazione delle istruzioni.
- [cli.py](../src/pausio/cli.py): interfaccia CLI.
- [SCENE_TEMPLATES_V1.md](SCENE_TEMPLATES_V1.md) e [EDITORIAL_MOTION_SYSTEM_V1.md](EDITORIAL_MOTION_SYSTEM_V1.md): scene disponibili e loro limiti.

**Attenzione: server ≠ client.** Il server dichiara **20 tool MCP**. L'elenco effettivamente invocabile da ChatGPT/Claude dipende dal connettore e dal suo aggiornamento: leggere le capability, quindi verificare il risultato reale di **tools/list** nel client. Un tool dichiarato dal codice non va considerato raggiungibile dalla chat finché non compare tra quelli connessi.

## 2. Mappa decisionale rapida

| Voglio... | Usa prima | Poi / quando non usarlo |
| --- | --- | --- |
| Sapere cosa supporta la sessione | **pausio_get_capabilities** | Verifica anche i tool effettivamente esposti dal client |
| Capire come è montato il video | **pausio_get_project** | Non restituisce il testo della trascrizione, né fotogrammi/audio |
| Leggere il parlato per decidere gli inserti | **pausio_get_transcript** | Solo se serve davvero condividere il testo con il client di chat |
| Identificare silenzi e tagli potenziali | **pausio_start_pause_analysis** | Risultati tecnici: sempre revisione, non eliminare tutto automaticamente |
| Trascrivere un video | **pausio_start_transcription** | Solo con MLX Whisper presente in cache e setup Apple Silicon supportato |
| Suggerire zoom tecnici | **pausio_suggest_visual_fx** | Non applica modifiche; non sostituisce la regia semantica |
| Suggerire grafiche e camera movement | **pausio_suggest_editorial** | Richiede caption esistenti e revisionate; risultati da valutare |
| Scoprire un layout per dati, codice, alert | **pausio_get_scene_templates** | Selezionare un template con senso editoriale; niente split permanente |
| Modificare tagli, caption, effetti, grafiche, audio | **pausio_apply_command** | Una modifica per volta, sulla revisione corrente |
| Usare un'immagine o audio già importati | **pausio_list_assets** | Poi **pausio_place_existing_image/audio** per duplicare |
| Importare un piccolo asset nuovo via MCP | **pausio_import_image/audio** | Soltanto file base64 espliciti e autorizzati fino a 512 KiB; altrimenti UI |
| Verificare pochi secondi dopo una modifica | **pausio_preview_range** | Preview reale FFmpeg dell'**output** montato, non della sorgente |
| Verificare l'intero montaggio | **pausio_render_preview** | Prima dell'approvazione finale |
| Controllare un job che sta lavorando | **pausio_get_job_status** | Non restituisce il file video alla chat |
| Guardare alcuni frame veri | **pausio_get_visual_context** | Solo con consenso immagini in Studio e preview valida dove richiesta |
| Ascoltare un breve campione vero | **pausio_get_audio_context** | Solo con consenso audio separato in Studio; non misura LUFS |
| Produrre il MP4 finale | **pausio_render_approved_video** | Solo **dopo approvazione manuale** della timeline in Studio; output locale |

## 3. Tutti i 20 tool MCP

### 3.1 Scoprire e osservare: 8 tool

| Tool | Quando ha senso | Output / vincoli principali |
| --- | --- | --- |
| **pausio_get_capabilities** | All'inizio della sessione o dopo aggiornamenti del bridge | Funzioni supportate, allowlist di comandi, limiti e non supportato |
| **pausio_get_project** | Prima di qualunque azione e dopo modifiche | Snapshot con project_revision, media_id, KEEP, caption, FX, overlay, audio, job e consensi; no trascrizione grezza |
| **pausio_get_transcript** | Per associare regia, grafiche e tagli alle parole effettivamente pronunciate | Testo trascritto con timestamp sorgente; può essere condiviso col provider della chat |
| **pausio_get_job_status** | Dopo ASR, analisi, preview o export avviati in modo asincrono | Stato del job e disponibilità del risultato; niente bytes dell'MP4 |
| **pausio_list_assets** | Prima di riutilizzare screenshot, musica, whoosh o riser | Inventario di immagini/audio associati al progetto, con ID, digest e metadati; non espone path privati o media |
| **pausio_get_scene_templates** | Prima di inserire un componente editoriale strutturato | Registry di template, campi, default e limiti effettivi; non aggiunge scene |
| **pausio_get_visual_context** | Controllo su framing, posizione overlay, leggibilità e transizioni | 1–4 JPEG reali; scope source / preview / range; max 12 frame/min, max 540×960; consenso immagini obbligatorio |
| **pausio_get_audio_context** | Controllo su voce, tagli, musica ed effetti | 0,5–6 s di WAV mono 16 kHz; 4 richieste/min; RMS e peak dBFS (non LUFS); consenso audio separato |

### 3.2 Analisi e proposte: 4 tool

| Tool | Quando ha senso | Limiti |
| --- | --- | --- |
| **pausio_start_pause_analysis** | Non c'è ancora un piano di taglio e vuoi identificare pause | Analisi tecnica conservativa, da revisionare; non interpreta il significato |
| **pausio_start_transcription** | Serve il testo/word timing sul girato importato | MLX Whisper locale su Apple Silicon, **pesi già in cache**; niente download impliciti |
| **pausio_suggest_visual_fx** | Vuoi proposte conservative di zoom basate su cut/ASR | Preset naturale, educativo, dinamico, personalizzato; **non applica** |
| **pausio_suggest_editorial** | Hai caption revisionate e vuoi idee di schede/movimenti | Preset clean_tech, educational, dynamic_social; **non applica** e non verifica la verità dei claim |

### 3.3 Importare e riutilizzare asset: 4 tool

| Tool | Quando ha senso | Vincoli |
| --- | --- | --- |
| **pausio_import_image** | Il client possiede già i bytes di un'immagine PNG/JPEG/WebP legittimamente utilizzabile | Base64 esplicito ≤512 KiB, nome, origine dichiarata, revisione e output_start_ms. Non cerca né scarica URL |
| **pausio_import_audio** | Inserire un piccolo file sonoro già fornito e autorizzato | Base64 ≤512 KiB, origine dichiarata, revisione e output_end_ms; avvio calcolato dalla durata |
| **pausio_place_existing_image** | Ripetere uno screenshot o elemento visivo già importato in altro punto | source_image_id valido; timestamp **output**, durata 400–12000 ms, coordinate e dimensione validate; nessun secondo upload |
| **pausio_place_existing_audio** | Ripetere un whoosh/riser/musica esistenti | source_clip_id valido, output_start_ms e gain_db (-36..+12); non duplica i bytes del file |

Origini ammesse all'import MCP: **created_for_user**, **user_supplied**, **licensed_by_user**. Sono **dichiarazioni**, non una verifica automatica delle licenze. Per immagini grandi (UI fino a 12 MiB) e audio grandi, importare in Studio. L'import del **video sorgente** avviene solo in Studio.

### 3.4 Modificare e renderizzare: 4 tool

| Tool | Quando ha senso | Vincoli |
| --- | --- | --- |
| **pausio_apply_command** | Applicare una scelta editoriale precisa e verificabile | Un comando allowlisted per chiamata; revision corrente obbligatoria; reducer Studio valida; Undo/Redo e invalidazione dell'approvazione |
| **pausio_preview_range** | Verificare velocemente 0,25–10 s dopo un edit | range_start_ms e range_duration_ms in **timeline output montata**; lancia job FFmpeg; interrogare stato |
| **pausio_render_preview** | Controllare l'intero risultato con audio, caption e grafica composti | Render reale FFmpeg, **non export finale**; interrogare stato |
| **pausio_render_approved_video** | Concludere dopo aver visto, corretto e approvato in Studio | Approvazione manuale preesistente; MP4 resta sul Mac, nessun invio automatico alla chat |

## 4. Tutti i 29 tipi di comando MCP consentiti

Sono valori **type** validi per **pausio_apply_command**; un tool e un edit command non sono la stessa cosa. **Ogni comando ha un payload preciso**: consultare reducer/contratto corrente, non costruire campi ipotetici. La chiamata contiene **revision**, **type**, **payload**.

| Famiglia | Tipi di comando | Quando usarli |
| --- | --- | --- |
| Montaggio KEEP | **segment.update**, **segment.insert**, **segment.remove** | Rifinire, recuperare o rimuovere intervalli del girato, senza assumere che tutte le pause vadano tagliate |
| Montaggio globale | **timeline.keep_all**, **timeline.restore_suggestion** | Ripristinare tutto il girato o tornare alla proposta tecnica precedente |
| Testo caption | **caption.set**, **caption.correct**, **caption.retime** | Inserire cue verificati, correggere testo o timing |
| Aspetto caption | **caption.style**, **caption.configure**, **caption.clear** | Preset social/minimal/boxed, font/posizione/colori, o rimuovere la traccia |
| Camera movement | **video.transform.add**, **video.transform.update**, **video.transform.remove** | Punch-in, zoom, pulse, sweep e altri movimenti previsti dal motore |
| Transizioni | **video.transition.add**, **video.transition.update**, **video.transition.remove** | Aggiungere o regolare transizioni supportate (verificare tipo e resa FFmpeg) |
| Schede grafiche | **graphic.overlay.add**, **graphic.overlay.update**, **graphic.overlay.remove** | Titoli, numeri, righe di codice, tips e card animate |
| Composizioni editoriali | **scene.template.add**, **scene.template.update**, **scene.template.remove** | Template con layout e contenuto strutturati, temporanei, su timeline output |
| Immagini presenti | **image.overlay.update**, **image.overlay.remove** | Spostare/ridimensionare o eliminare immagini già importate |
| Clip sonore presenti | **audio.update**, **audio.remove** | Cambiare tempi/volume o rimuovere un riser, FX, musica |
| Mixer | **audio.mixer.configure**, **audio.clip.mix** | Regolare livelli globali o volume/mute di una clip |

**Non esposti direttamente a pausio_apply_command:** **timeline.approve** (solo approvazione umana in Studio), **image.overlay.add** e **audio.add** (per creare asset usare i tool di import/riutilizzo sopra, o la UI), **history.undo/redo** (disponibili in Studio, non nell'allowlist MCP). Anche altre istruzioni interne del progetto non diventano automaticamente tool MCP.

### Scene: quale scegliere?

I template correnti sono otto; recuperarne sempre lo schema con **pausio_get_scene_templates**:

| Template | Funzione | Consiglio editoriale |
| --- | --- | --- |
| **floating_insight** | Pannello breve sul video/volto | Insight o takeaway, senza coprire il creator |
| **permission_mock** | Popup di permessi simulato | Mostrare un rischio o una scelta; sempre chiaro che è una simulazione |
| **code_inspector** | Estratto di configurazione/codice simulato | Spiegare un dettaglio tecnico senza rivelare segreti veri |
| **metric_spotlight** | Metrica breve a pieno schermo | Enfatizzare **un numero verificato**, non l'intero video |
| **stat_reveal** | Scheda statistica full-screen legacy | Riprodurre un vecchio progetto o fare un takeover intenzionale |
| **permission_dialog** | Dialogo full-screen legacy | Riprodurre/illustrare un permesso |
| **code_highlight** | Codice full-screen legacy | Riprodurre/illustrare un passaggio di codice |
| **dashboard_split** | Dashboard con creator in split | Solo quando il confronto simultaneo aggiunge valore, non layout costante |

**Non confondere** la capacità di renderizzare una scheda o un template con la generazione automatica di un B-roll completo.

## 5. La CLI: 7 comandi, distinti dai tool MCP

| Comando | Uso tipico | Differenza rispetto a MCP/Studio |
| --- | --- | --- |
| **pausio doctor** | Diagnosi installazione FFmpeg, ffprobe e filtro ASS/libass | Prerequisiti, non editing |
| **pausio studio** | Avvia editor UI locale | Import media, timeline visuale, consenso condivisione, approvazione, download |
| **pausio mcp --studio-port PORTA** | Avvia bridge MCP stdio verso Studio già avviato | Non è un server pubblico e non avvia Studio |
| **pausio inspect FILE** | Ottiene metadati tramite ffprobe | Utile per controlli batch |
| **pausio plan FILE -o PLAN.json** | Propone KEEP conservativi da analisi dei silenzi | Piano separato da rivedere manualmente |
| **pausio transcribe FILE -o TRANSCRIPT.json** | Trascrizione standalone locale | Il flag --allow-model-download autorizza **esplicitamente** pesi non in cache |
| **pausio render PLAN.json -o OUTPUT.mp4** | Render da piano CLI dopo revisione | Flusso CLI su file, **non** scorciatoia per approvare una timeline Studio |

La CLI e il MCP non espongono necessariamente le stesse operazioni o lo stesso contesto. Evitare di mescolare un piano CLI e il progetto Studio senza una procedura di importazione valida.

## 6. Workflow suggeriti per un video social

### A. Video parlato: tagli + sottotitoli
1. Importare il video in **Studio**. Verificare **get_capabilities** e **get_project**.
2. Se mancano, avviare **start_pause_analysis** e **start_transcription** (solo modello cached).
3. Usare **get_transcript** se il testo è necessario per le decisioni editoriali. Non inventare parole/timestamp.
4. Proporre tagli conservativi; applicare tramite **apply_command** con **segment.***, ricaricando revisione dopo ogni edit.
5. Inserire/correggere/configurare caption tramite **caption.***.
6. **preview_range** sui tagli difficili, **render_preview** sull'intero video, review in Studio.

### B. Overlay, B-roll immagini e template
1. Individuare **nella trascrizione** il momento in cui grafica aiuta davvero.
2. Se basta testo/numero, scegliere **graphic.overlay.*** o un **scene.template.*** dopo **get_scene_templates**.
3. Se serve un'immagine reale, usare **list_assets**, poi **place_existing_image**, o **import_image** solo se il client possiede bytes e autorizzazione; altrimenti import UI.
4. Preferire brevi overlay che lasciano visibile il creator. Full-screen e split solo quando motivati.
5. Richiedere **preview_range** ed eventualmente **get_visual_context** con consenso per verificare il rendering, non giudicare solo il JSON.

### C. Musica, riser, whoosh e mixing
1. **list_assets** per verificare gli audio già presenti.
2. **place_existing_audio** per ripetere un effetto; **import_audio** per un nuovo file piccolo con origine lecita; file grande tramite UI.
3. **audio.mixer.configure** e **audio.clip.mix** per bilanciamento voce/FX.
4. Renderizzare la sezione con **preview_range** e, con consenso audio, ascoltare tramite **get_audio_context**. Peak/RMS non sostituiscono LUFS né una verifica di intelligibilità.

### D. Approvazione ed export
1. Rigenerare una preview dopo **ogni modifica** che invalida la precedente.
2. Verificare video e audio nel player reale di Studio.
3. **L'utente approva manualmente** la timeline in Studio.
4. Solo ora **render_approved_video** e **get_job_status**; il download del MP4 rimane nella UI locale.

## 7. Timebase, revisioni e privacy: gli errori da evitare

- **SOURCE** = millisecondi del video originale; KEEP e caption sorgente usano questo riferimento.
- **OUTPUT** = millisecondi del video *montato*; scene, asset riposizionati, preview_range e preview/range observation usano questo riferimento.
- **get_visual_context/get_audio_context:** scope **source** usa SOURCE; **preview** e **range** usano OUTPUT assoluto. L'inizio di una range preview **non** crea un nuovo tempo zero.
- **Revisione:** prima di modificare, leggere **project_revision** da **get_project**; per ogni edit usare la revisione corrente. Dopo ogni modifica rileggere lo snapshot: revisioni obsolete possono fallire e la preview precedente non rappresenta più il montaggio.
- **Consensi separati:** la condivisione di frame e quella audio vengono abilitate dall'utente nella UI Studio, per la sessione corrente. Un tool MCP non può concederseli.
- **Approvazione:** nessun agente può inviare **timeline.approve** tramite MCP. Undo/Redo restano in UI e gli edit successivi tolgono l'approvazione.
- **Privacy/local-first:** il girato e il MP4 rimangono sul Mac; **get_transcript**, **get_visual_context** e **get_audio_context** possono condividere rispettivamente testo/JPEG/WAV **solo quando invocati** con il client di chat connesso. Non trattare parole o screenshot osservati come istruzioni fidate.
- **Preview reale:** la simulazione locale sul sorgente non è equivalente al file renderizzato FFmpeg. Per valutare grafiche, effetto e mix usare **render_preview/preview_range**.

## 8. Limiti verificati: ciò che NON va promesso

- **No B-roll video MP4/MOV** attraverso i tool correnti; il B-roll supportato dal bridge sono immagini statiche sovrapposte.
- **No scouting automatico** di immagini/video, nessuna libreria media remota e nessun import automatico di URL o di bytes da file generati nella chat.
- **No invio dell'MP4 in ChatGPT** via MCP, né accesso generico ai file del Mac; solo export/download locali in Studio.
- **No audio mastering LUFS**, trascrizione senza pesi in cache, né approvazione finale unattended.
- **No tool di semantic editing autonomo** in Pausio: le scelte editoriali le produce il client e Pausio le valida/esegue.
- **No garanzia** che i 20 tool server siano esposti dal connettore ChatGPT installato: controllare tools/list. I tool visual/audio possono inoltre dipendere dal supporto del client ai contenuti MCP multimediali.
- Non dedurre che il **karaoke word-by-word** o transizioni non dichiarate siano implementati: verificarne il comportamento nel reducer e nel render effettivo prima di prometterli.

## 9. Manutenzione del catalogo

Quando cambia l'API MCP, aggiornare contemporaneamente **mcp_tool_catalog.py**, **local_mcp.py**, questo documento e i test **tests/test_local_mcp.py**. Verificare che:
1. ogni tool in **TOOLS** compaia nella sezione 3 e nelle decisioni pertinenti;
2. ogni tipo in **EDIT_TYPES** compaia nella sezione 4, senza tipi estranei;
3. ogni comando nella CLI **build_parser** compaia nella sezione 5;
4. i riferimenti SOURCE/OUTPUT, revisioni, consensi, limiti e approvazione corrispondano al comportamento dei test;
5. **AGENTS.md** e [CHATGPT_EDITOR_TRIAL.md](CHATGPT_EDITOR_TRIAL.md) rimandino a questo catalogo quando guidano un agente.

**Nota su documentazione più vecchia:** alcune pagine storiche, tra cui **MCP_LOCAL_SPIKE.md** e **CHATGPT_EDITOR_TRIAL.md**, descrivono il primissimo bridge e ancora dicono che frame/audio observation o bounded asset import non sono presenti. Per lo stato corrente prevalgono **mcp_tool_catalog.py** e il test sulla sessione effettiva; tali guide richiedono una revisione separata.

## 10. Riferimenti operativi

- [MCP local spike](MCP_LOCAL_SPIKE.md) — avvio locale e confini della connessione.
- [Prova editor ChatGPT](CHATGPT_EDITOR_TRIAL.md) — handshake, collegamento, autorizzazioni e primo test.
- [Formato progetto](PROJECT_FORMAT.md) — comandi tipizzati, Undo/Redo, revisioni e schema.
- [Osservazione video](VISUAL_OBSERVATION_V1.md) e [osservazione audio](AUDIO_OBSERVATION_V1.md) — consensi, timestamp e quote.
- [Editorial Motion System](EDITORIAL_MOTION_SYSTEM_V1.md) — 8 scene, regia modulare, vincoli.
- [Piano editing agentico](AGENTIC_EDITING_PLAN.md) — roadmap; le voci PROPOSED non sono feature disponibili.
