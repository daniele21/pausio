# Piano editoriale · Password, coding agent e GitHub

**Base reale:** trascrizione MLX Whisper associata al video `pausio-take-2026-11-12T11-34-23-592Z.mp4` e ai 20 intervalli KEEP del progetto (durata montata 88.051 ms, revision 74 al momento dell'analisi). **Stato:** proposta da applicare e verificare; non è ancora un render approvato. I timestamp sotto sono **output**, dopo i tagli, non secondi del file sorgente.

## Regia: presenza del creator prima dell'effetto

| Output (mm:ss) | Modalità | Beat narrativo | Intervento |
|---|---|---|---|
| 00:00–00:06.2 | **VOLTO** | «Potresti pubblicare una password su GitHub» | Inquadratura originale, hook e sottotitoli. Nessuno split |
| 00:06.2–00:08.1 | **OVERLAY** | L'agente AI mentre programmi | `floating_insight`: «UN PERMESSO PUÒ RESTARE» / «Il problema non è solo il codice generato» |
| 00:08.1–00:16.1 | **VOLTO** | Anticipazione del controllo e introduzione della ricerca | Nessuna grafica; un eventuale zoom già esistente resta indipendente |
| 00:16.1–00:19.2 | **INSERTO DATI** | «oltre 1300 secret» | `metric_spotlight`: numero 1.379 / segreti / in 1.122 file pubblici. **Verificare fonte e cifra prima della pubblicazione** |
| 00:19.2–00:28.1 | **VOLTO** | «Ma com'è possibile? Immaginatevi...» | Ritorno al volto; la pausa visiva crea contrasto |
| 00:28.1–00:31.2 | **OVERLAY UI** | L'agente chiede un permesso e compare «non chiedermelo più» | `permission_mock`, interfaccia *illustrativa dichiarata*, bottone permanente evidenziato |
| 00:31.2–00:36.7 | **VOLTO** | Il permesso salvato diventa un rischio persistente | Volto, senza pannello fisso |
| 00:36.7–00:39.7 | **OVERLAY UI** | Una regola nella configurazione | `code_inspector`, file illustrativo `settings.local.json`; nessuna password reale |
| 00:39.7–00:53.9 | **VOLTO** | Spiegazione della pubblicazione e introduzione dei consigli | Solo parlato e sottotitoli |
| 00:53.9–00:56.2 | **OVERLAY** | Primo consiglio: controllare i comandi | `floating_insight`: «1. CONTROLLA IL COMANDO» |
| 00:56.2–01:01.6 | **VOLTO** | Secondo consiglio: configurazione e GitHub | Ritorno al volto |
| 01:01.6–01:04.0 | **OVERLAY** | Controllare file tracciati | `floating_insight`: «2. RIVEDI I FILE TRACCIATI» |
| 01:04.0–01:12.6 | **VOLTO** | Annuncio del controllo con git | Mostrare il creator, non sovraccaricare |
| 01:12.6–01:15.7 | **OVERLAY CODICE** | `settings.local.json` tracciato da git | `code_inspector`, esempio `git ls-files` in due righe |
| 01:15.7–01:28.05 | **VOLTO** | «Non solo cosa fanno. Come li utilizziamo.» | Chiusura in camera, niente grafica invasiva |

I range sono proposti sulla base della trascrizione e della proiezione dei KEEP. I tagli possono cambiare e invalidare i tempi: il piano deve essere ricalcolato da GPT prima di applicare le istruzioni.

## Specifica visual

- **Volto (stato di base):** ripresa originale intera, senza split continuo.
- **Overlay:** contenuto concentrato nella parte alta, volto ancora visibile sotto. Non nascondere i sottotitoli.
- **Inserto dati:** unica occupazione piena dello schermo, 2–3 secondi, ritorno al volto.
- **Mock UI:** componenti di prodotto *verosimili* ma dichiaratamente illustrativi. Mai copie spacciate per screenshot autentici.
- **Motion:** reveal in 140–240 ms, variazioni contenute, pausa sufficiente per leggere; niente zoom o transizione ad ogni frase.
- **Safe areas:** controllare titoli, sottotitoli e grafica con una vera preview FFmpeg, non il solo form HTML.

## Applicazione e rollback

I template implementati sono eventi `scene.template.add/update/remove` (ProjectTape, progetto v10). L'MCP li applica soltanto con revisione esatta; non esiste editing browser-only. Conservare gli eventi già presenti finché non si prepara un montaggio coerente e si verifica l'assenza di conflitti con le grafiche legacy.

**Non applicare automaticamente questo elenco come se fosse approvato:** GPT deve leggere stato e revisione correnti, verificare che l'intervallo sia libero e proporre il batch per revisione, poi preview; l'approvazione per la release finale resta nell'app.
