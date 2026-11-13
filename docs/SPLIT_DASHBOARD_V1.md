# Dashboard split-screen animata — prima versione

**Implementazione:** `dashboard_split` nel Scene Composer, progetto v9.

## Obiettivo

Riprodurre i primi 5–7 secondi dello stile del video di riferimento:
creator visibile nella fascia inferiore, dashboard animata nella metà superiore,
attività che compaiono/si completano, barra di avanzamento e riepilogo budget.
La voce e il mix audio del video originale continuano senza alterazioni.

**Non è ancora** un editor UI completamente libero: i quattro pannelli sono
data-driven; non si trascinano manualmente i singoli pulsanti, e non sono
implementati cursori o diagrammi ad archi. La base è volutamente ridotta.

## Come usarlo in Studio

1. Importa il video e prepara il montaggio.
2. Apri **Video FX → Scene animate e split-screen**.
3. Seleziona **01 · Dashboard + creator** e imposta una durata di circa 6.500 ms.
4. Modifica titolo, tre attività, etichetta/percentuale progress, budget.
5. Regola **Altezza creator (%)** 35–55 (45% predefinito) e
   **Inquadratura verticale (%)** 20–80 (42% predefinito): serve per
   scegliere quale fascia verticale del video sorgente riempirà il fondo.
6. Inserisci al cursore e premi **Guarda 5 s**; per osservare l'intera scena
   renderizza la preview completa. Il montaggio resta annullabile.

### Layout e animazione

- Video originale normalizzato 9:16 (FFmpeg), fascia inferiore riposizionata
  tramite un ritaglio centrato regolabile; il ritaglio è applicato solo tra
  `start_ms` e `start_ms + duration_ms` **dell'output montato**.
- Dashboard libass nella fascia superiore: entrata progressiva di tre card,
  indicatori di completamento, barra progressiva a 6 passi e budget finale.
- I sottotitoli già presenti restano nel livello superiore; se interferiscono
  con le grafiche, riposizionali tramite l'editor sottotitoli.
- Audio originale preservato; non sono caricati screenshot, immagini,
  stock footage o modelli AI.

## Da ChatGPT via MCP

Dopo aggiornamento Studio + riavvio tunnel e refresh strumenti:

1. `pausio_get_scene_templates`: elenca `dashboard_split` e lo schema
   esatto, con tutti i default.
2. `pausio_get_project`: ottieni `project_revision`, tempo totale e
   eventuali altre scene; evita sovrapposizioni.
3. `pausio_apply_command` con `scene.template.add` e valori validati.
4. `pausio_preview_range`, polling `pausio_get_job_status` e, previo
   consenso in Studio, `pausio_get_visual_context` per esaminare
   la parte superiore e il volto inferiore.
5. Non confermare il montaggio al posto del creator.

Esempio **indicativo** (revisione e ID da sostituire):

```json
{
  "revision": 12,
  "type": "scene.template.add",
  "payload": {
    "scene": {
      "id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "template": "dashboard_split",
      "start_ms": 0,
      "duration_ms": 6500,
      "accent": "orange",
      "content": {
        "title": "COSA STA SUCCEDENDO",
        "task_one": "Controlla le attività",
        "task_two": "Verifica i progressi",
        "task_three": "Rivedi il budget",
        "progress_label": "Avanzamento",
        "progress_pct": 70,
        "budget": "Budget: sotto controllo",
        "presenter_height_pct": 45,
        "presenter_anchor_pct": 42
      }
    }
  }
}
```

## Engineering contracts

- `split_dashboard.py` definisce animazioni ASS deterministiche e filtro
  FFmpeg per la zona speaker. Non accetta CSS, script, percorsi, URL, grafi
  FFmpeg arbitrari o dipendenze aggiuntive.
- `scene_templates.py` valida campi, durate, numero massimo e coerenza dei
  template. Il `ProjectTape` salva gli eventi v9 e importa v1–v8.
- `media.py` compone il ritaglio del creator **dopo** il concat KEEP e
  **prima** di immagini, scene libass e captions. Stessa composizione per
  intervalli renderizzati e MP4 finale. Layout disattivato fuori scena.
- `scene_template_ui.js` costruisce i controlli dal catalogo Python; i
  campi dell'utente non generano in modo diretto filtri o HTML.
- Prove: validazione, replay, Undo/Redo, codec reale FFmpeg, colore dell'area
  superiore/inferiore prima e dopo scena, presenza stream audio, preview a
  intervallo, UI Playwright e schemi v9.

### Successivi incrementi separati

`approval_cards`, `integration_flow`, cursore simulato, animazioni
keyframe più ricche, canvas a livelli, B-roll video e preflight caption-safe.
Non attribuire al solo template v1 risultati di engagement misurati.
