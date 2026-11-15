# Pausio · Editorial Motion System (v1)

## Mission

**Un sistema di montaggio modulare, non uno split-screen fisso.** L'unità creativa è un *beat* con scopo, timestamp output e layout esplicito. Il girato del creator resta la base; in assenza di un evento grafico la clip continua naturale. ChatGPT/Claude Chat progettano la regia; Pausio verifica e renderizza con lo stesso FFmpeg/libass che usa Studio. Il sistema non effettua chiamate AI API.

## Gli otto template supportati

| Template | Layer | Durata minima–massima | Scopo |
|---|---|---|---|
| `floating_insight` | Overlay su volto | 0.9–5s | Un messaggio breve, un consiglio o un rischio |
| `permission_mock` | Overlay su volto | 1.6–7s | Simulare una richiesta di autorizzazione (sempre dichiarata) |
| `code_inspector` | Overlay su volto | 1.8–7s | Ispezionare regole/configurazioni illustrate, senza segreti reali |
| `metric_spotlight` | Full-screen takeover | 1.8–7s | Un dato verificato, una volta sola quando serve |
| `stat_reveal` | Full-screen legacy | 2.5–12s | Vecchio template, invariato per replay |
| `permission_dialog` | Full-screen legacy | 2.5–12s | Vecchio template, invariato |
| `code_highlight` | Full-screen legacy | 2.5–12s | Vecchio template, invariato |
| `dashboard_split` | Split facoltativo | 2.5–12s | Vista composta, non default editoriale |

**Progetto:** schema v10, import compatibile v1–v9; fino a 16 scene per progetto; un solo evento per intervallo, nessuna sovrapposizione non esplicita. Le proposte editoriali e il montaggio corrente restano entità distinte; nessun algoritmo riempie automaticamente tutti i secondi.

## Linguaggio visivo

- Card con raggi arrotondati, ombre e pannelli sovrapposti usando vettori ASS, tipografia gerarchica, accenti arancione o verde acqua.
- Mock permission e code inspector con barre, badge, pulsanti, line numbers, tab editor e microanimazioni di apparizione.
- Due regioni chiaramente diverse: **overlay** preserva il volto e il video sottostante; **fullscreen** oscura la ripresa soltanto nell'intervallo richiesto; **split** resta un'opzione consapevole.
- Le informazioni aggiunte a video sono elementi editabili con campi tipizzati; non copie PNG predefinite e non testo HTML reso soltanto nel browser.
- I mock sono etichettati *simulazione*; non sono un falso screenshot delle app citate.
- Il registro Python `scene_templates.py` è fonte unica per i campi, durate e layout esposti nel catalogo MCP e nel form Studio.

## Contratto e pipeline

`ProjectTape(scene.template.add/update/remove)` → `scene_templates.validate_scene` → `compose_scene_events` → `editorial_cards.compose_editorial_card` → unico `compose_graphics_ass` → FFmpeg/libass per preview e MP4 finale.

Le voci e tracce audio non vengono toccate da questi template. Le scene originali/legacy continuano a essere interpretate come prima per compatibilità. Non accettare URL, shell command, JS, CSS, markup o espressioni FFmpeg personalizzate da una scena. Testare anche i casi con testo ASS malizioso.

Il pannello **Composizione editoriale modulare** mostra una sola mappa di lettura della sequenza, con aree volto/overlay/fullscreen/split e navigazione. Non diventa una seconda timeline modificabile.

## Esempio di proposta ChatGPT (non applicata senza revisione)

```json
{
  "revision": 74,
  "type": "scene.template.add",
  "payload": {
    "scene": {
      "id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "template": "floating_insight",
      "start_ms": 6200,
      "duration_ms": 1900,
      "accent": "orange",
      "content": {
        "title": "UN PERMESSO PUÒ RESTARE",
        "detail": "Il problema non è solo il codice generato"
      }
    }
  }
}
```

Per applicarlo, prima leggere la revisione corrente, verificare i conflitti, poi osservare il rendering. L'MCP è capace di operazioni atomiche **singole**; editing multi-scena in un solo Undo richiede il futuro componente `edit_transactions.py` (non affermare che già esista).

## Prossime evoluzioni

1. **Preflight visuale automatico** delle zone sottotitoli e pannelli, su frame reali con consenso.
2. **Atomic batch** validato con un solo undo per una sequenza di inserti, non N chiamate indipendenti.
3. **Motion curves / layouts per layer** e controllo avanzato del caption-safe area.
4. **B-roll video importato localmente**, assegnato come asset verificato, senza download nascosti.
5. Miglioramento del rendering delle UI (blur, antialiasing, glyph asset) dopo valutazione su video reale.

La compatibilità estetica è un obiettivo visivo da validare con preview e creator, non un esito misurabile dai test unitari.
