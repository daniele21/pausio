"""Three bounded, output-timed social scene templates rendered with libass.

A scene is a deterministic typed project event, not generated HTML or a new
video engine. It is deliberately independent of FFmpeg, I/O and the UI.
Voice/music remain on the existing mixed audio graph under a full-screen card.
"""
from __future__ import annotations

import re
from typing import Any

from pausio.captions import _ass_color, _ass_text, _ass_time
from pausio.split_dashboard import compose_dashboard
from pausio.editorial_cards import compose_editorial_card
from pausio.motion_metric import is_valid_counter_value

MAX_SCENES = 16
SCENE_FIELDS = frozenset({"id", "template", "start_ms", "duration_ms", "accent", "content"})
_SCENE_ID = re.compile(r"^[0-9a-f]{32}$")
_COLORS = {"mint": "#66D4C5", "orange": "#FFA875"}
_BACKGROUND = "#091420"
_PANEL = "#152536"
_TEXT = "#F2F6F8"
_MUTED = "#A9BEC7"

# Field descriptions and defaults are shared with MCP and the Studio editor.
TEMPLATES = {
    "floating_insight": {
        "recommended_duration_ms": 1900,
        "label": "Overlay · Insight flottante",
        "layout": "overlay",
        "min_duration_ms": 900, "max_duration_ms": 5000,
        "fields": [
            {"key": "title", "label": "Messaggio principale",
             "type": "text", "max_length": 34,
             "default": "IL RISCHIO È NEI PERMESSI"},
            {"key": "detail", "label": "Spiegazione sintetica",
             "type": "text", "max_length": 52,
             "default": "Non solo cosa fa l'agente. Come lo autorizzi."},
        ],
    },
    "permission_mock": {
        "recommended_duration_ms": 3000,
        "label": "Mockup · Dialogo autorizzazione",
        "layout": "overlay",
        "min_duration_ms": 1600, "max_duration_ms": 7000,
        "fields": [
            {"key": "title", "label": "Titolo popup",
             "type": "text", "max_length": 36,
             "default": "Allow this command?"},
            {"key": "command", "label": "Comando illustrativo",
             "type": "text", "max_length": 37,
             "default": "Run a command requiring access"},
            {"key": "once", "label": "Autorizzazione singola",
             "type": "text", "max_length": 17,
             "default": "Allow once"},
            {"key": "persistent", "label": "Autorizzazione persistente",
             "type": "text", "max_length": 21,
             "default": "Don't ask again"},
        ],
    },
    "code_inspector": {
        "recommended_duration_ms": 3000,
        "label": "Mockup · Configurazione locale",
        "layout": "overlay",
        "min_duration_ms": 1800, "max_duration_ms": 7000,
        "fields": [
            {"key": "filename", "label": "File illustrativo",
             "type": "text", "max_length": 32,
             "default": "settings.local.json"},
            {"key": "line_one", "label": "Prima riga",
             "type": "text", "max_length": 34,
             "default": '"permissions": {'},
            {"key": "line_two", "label": "Seconda riga",
             "type": "text", "max_length": 34,
             "default": '"allow": ['},
            {"key": "highlight", "label": "Riga evidenziata",
             "type": "text", "max_length": 34,
             "default": '"example permission rule"'},
        ],
    },
    "metric_spotlight": {
        "recommended_duration_ms": 2800,
        "label": "Inserto · Dato principale",
        "layout": "fullscreen",
        "min_duration_ms": 1800, "max_duration_ms": 7000,
        "fields": [
            {"key": "heading", "label": "Titolo piccolo",
             "type": "text", "max_length": 35,
             "default": "COSA HA TROVATO LA RICERCA"},
            {"key": "number", "label": "Numero esatto",
             "type": "text", "max_length": 13,
             "default": "1.379"},
            {"key": "unit", "label": "Unità",
             "type": "text", "max_length": 22,
             "default": "SEGRETI"},
            {"key": "detail", "label": "Contesto",
             "type": "text", "max_length": 46,
             "default": "in file di configurazione pubblici"},
            {"key": "source_note", "label": "Nota sulla fonte",
             "type": "text", "max_length": 45,
             "default": "Dati da verificare prima di pubblicare"},
        ],
    },
    "stat_reveal": {
        "label": "03 · Statistica animata",
        "fields": [
            {"key": "eyebrow", "label": "Titolo piccolo", "type": "text",
             "max_length": 48, "default": "UNA RICERCA HA TROVATO"},
            {"key": "number", "label": "Numero", "type": "text",
             "max_length": 12, "default": "1.379"},
            {"key": "label", "label": "Etichetta", "type": "text",
             "max_length": 32, "default": "SEGRETI"},
            {"key": "detail", "label": "Dettaglio verificato", "type": "text",
             "max_length": 60, "default": "in 1.122 file pubblici"},
        ],
    },
    "permission_dialog": {
        "label": "04 · Popup autorizzazione",
        "fields": [
            {"key": "title", "label": "Domanda popup", "type": "text",
             "max_length": 50, "default": "Allow this command?"},
            {"key": "command", "label": "Azione illustrata", "type": "text",
             "max_length": 55, "default": "Run command with credentials"},
            {"key": "primary", "label": "Pulsante normale", "type": "text",
             "max_length": 22, "default": "Yes, once"},
            {"key": "persistent", "label": "Pulsante persistente", "type": "text",
             "max_length": 25, "default": "Don't ask again"},
            {"key": "detail", "label": "Nota di contesto", "type": "text",
             "max_length": 60, "default": "Una scelta apparentemente innocua"},
        ],
    },
    "dashboard_split": {
        "label": "01 · Dashboard + creator",
        "layout": "split_vertical",
        "fields": [
            {"key": "title", "label": "Titolo", "type": "text",
             "max_length": 35, "default": "COME FUNZIONA DAVVERO"},
            {"key": "task_one", "label": "Prima attività", "type": "text",
             "max_length": 30, "default": "Apri il progetto"},
            {"key": "task_two", "label": "Seconda attività", "type": "text",
             "max_length": 30, "default": "Analizza i risultati"},
            {"key": "task_three", "label": "Terza attività", "type": "text",
             "max_length": 30, "default": "Controlla il budget"},
            {"key": "progress_label", "label": "Etichetta avanzamento",
             "type": "text", "max_length": 27, "default": "Avanzamento"},
            {"key": "progress_pct", "label": "Avanzamento (%)",
             "type": "integer", "minimum": 0, "maximum": 100, "default": 70},
            {"key": "budget", "label": "Testo finale / budget",
             "type": "text", "max_length": 36, "default": "Budget: sotto controllo"},
            {"key": "presenter_height_pct", "label": "Altezza creator (%)",
             "type": "integer", "minimum": 35, "maximum": 55, "default": 45},
            {"key": "presenter_anchor_pct", "label": "Inquadratura verticale (%)",
             "type": "integer", "minimum": 20, "maximum": 80, "default": 42},
        ],
    },
    "code_highlight": {
        "label": "05 · Codice evidenziato",
        "fields": [
            {"key": "title", "label": "Titolo", "type": "text",
             "max_length": 52, "default": "IL COMANDO PUÒ ESSERE SALVATO"},
            {"key": "filename", "label": "Nome file", "type": "text",
             "max_length": 40, "default": "settings.local.json"},
            {"key": "code", "label": "Codice illustrativo (fino a 5 righe)",
             "type": "textarea", "max_length": 165,
             "default": "{\n  permissions:\n    allow: [TOKEN]\n}"},
            {"key": "highlight_line", "label": "Riga evidenziata (1–5)",
             "type": "integer", "minimum": 1, "maximum": 5, "default": 3},
            {"key": "detail", "label": "Spiegazione", "type": "text",
             "max_length": 60, "default": "Il segreto può finire nella regola"},
        ],
    },
}

# Additive scene type: legacy metric_spotlight remains byte-for-byte unchanged.
# The dedicated v15 schema gives this template a distinct, validated identity.
TEMPLATES["metric_countup"] = {
    **TEMPLATES["metric_spotlight"],
    "label": "Inserto · Metrica animata (count-up)",
    "fields": [dict(field) for field in TEMPLATES["metric_spotlight"]["fields"]],
}


def catalog() -> list[dict]:
    """Return display metadata without exporting internal render expressions."""
    return [{"id": name, "label": spec["label"],
             "layout": spec.get("layout", "fullscreen"),
             "min_duration_ms": spec.get("min_duration_ms", 2500),
             "max_duration_ms": spec.get("max_duration_ms", 12000),
             "recommended_duration_ms": spec.get("recommended_duration_ms", 3000),
             "fields": [dict(field) for field in spec["fields"]]}
            for name, spec in TEMPLATES.items()]


def validate_scene(raw: Any, total_ms: int) -> dict:
    if not isinstance(raw, dict) or set(raw) != SCENE_FIELDS:
        raise ValueError("Scena: campi mancanti o sconosciuti.")
    if type(raw["id"]) is not str or not _SCENE_ID.fullmatch(raw["id"]):
        raise ValueError("Scena: ID non valido.")
    template = raw["template"]
    if type(template) is not str or template not in TEMPLATES:
        raise ValueError("Scena: template sconosciuto.")
    start, duration = raw["start_ms"], raw["duration_ms"]
    spec = TEMPLATES[template]
    minimum = spec.get("min_duration_ms", 2500)
    maximum = spec.get("max_duration_ms", 12000)
    if (type(start) is not int or type(duration) is not int or
        start < 0 or not minimum <= duration <= maximum or
        start + duration > total_ms):
        raise ValueError(f"Scena: {minimum}–{maximum} ms dentro la timeline montata.")
    if type(raw["accent"]) is not str or raw["accent"] not in _COLORS:
        raise ValueError("Scena: colore non supportato.")
    content = raw["content"]
    specs = TEMPLATES[template]["fields"]
    if not isinstance(content, dict) or set(content) != {f["key"] for f in specs}:
        raise ValueError("Scena: contenuti mancanti o sconosciuti.")
    for field in specs:
        key, value = field["key"], content[field["key"]]
        if field["type"] == "integer":
            if type(value) is not int or not field["minimum"] <= value <= field["maximum"]:
                raise ValueError(f"Scena: parametro numerico {key} non valido.")
        elif (type(value) is not str or not 1 <= len(value.strip()) <= field["max_length"]
              or value != value.strip()
              or any(ord(ch) == 127 or (ord(ch) < 32 and
                       not (field["type"] == "textarea" and ch == "\n")) for ch in value)):
            raise ValueError(f"Scena: testo {key} non valido.")
    if template == "metric_countup" and not is_valid_counter_value(content["number"]):
        raise ValueError("Count-up: usa un numero intero non negativo, massimo 9.999.999.")
    if template == "code_highlight":
        lines = content["code"].split("\n")
        if (not 1 <= len(lines) <= 5 or
            any(not line.strip() or len(line) > 34 for line in lines) or
            content["highlight_line"] > len(lines)):
            raise ValueError("Scena: fino a 5 righe di codice, massimo 34 caratteri per riga.")
    return {"id": raw["id"], "template": template, "start_ms": start,
            "duration_ms": duration, "accent": raw["accent"], "content": dict(content)}


def validate_scenes(rows: Any, total_ms: int) -> None:
    if not isinstance(rows, (list, tuple)) or len(rows) > MAX_SCENES:
        raise ValueError(f"Scena: massimo {MAX_SCENES} scene per progetto.")
    seen: set[str] = set()
    previous_end = 0
    for scene in sorted(rows, key=lambda x: x["start_ms"] if isinstance(x, dict)
                        and type(x.get("start_ms")) is int else -1):
        item = validate_scene(scene, total_ms)
        if item["id"] in seen or item["start_ms"] < previous_end:
            raise ValueError("Scena: ID duplicato o intervalli visivi sovrapposti.")
        seen.add(item["id"])
        previous_end = item["start_ms"] + item["duration_ms"]


def _safe(value: str) -> str:
    """ASS override braces/slashes never come from untrusted scene content."""
    return _ass_text(value.replace("{", "｛").replace("}", "｝")
                     .replace("\\", "＼"))


def _event(layer: int, start: int, end: int, text: str, tags: str) -> str:
    return (f"Dialogue: {layer},{_ass_time(start)},{_ass_time(end)},"
            f"Scene,,0,0,0,,{{{tags}}}{text}\n")


def _rect(start: int, end: int, x: int, y: int, w: int, h: int,
          color: str, *, layer: int = 2) -> str:
    """ASS vector drawing uses fixed dimensions; not an FFmpeg expression."""
    path = f"m {x} {y} l {x+w} {y} {x+w} {y+h} {x} {y+h}"
    return _event(layer, start, end, path,
                  r"\an7\pos(0,0)\bord0\shad0\c" + _ass_color(color) +
                  r"\p1")


def _label(start: int, end: int, text: str, x: int, y: int,
           size: int, color: str, *, layer: int = 4, font: str = "Arial",
           pop: bool = False) -> str:
    if end <= start:
        return ""
    motion = (r"\fscx85\fscy85\t(0,240,\fscx100\fscy100)"
              if pop else "")
    tags = (rf"\an5\pos({x},{y})\fn{font}\fs{size}\b1\bord0\shad0"
            + r"\c" + _ass_color(color) + r"\fad(140,170)" + motion)
    return _event(layer, start, end, _safe(text), tags)


def compose_scene_events(rows: list[dict], total_ms: int) -> str:
    """Full-frame scene cards; narration is untouched in the audio graph.

    Caller inserts these events into the existing ASS document; captions have
    higher layer (10) when a scene is present. Scene timestamps are OUTPUT ms.
    """
    validate_scenes(rows, total_ms)
    out: list[str] = []
    for scene in rows:
        a = scene["start_ms"]
        end = a + scene["duration_ms"]
        data = scene["content"]
        accent = _COLORS[scene["accent"]]
        if scene["template"] == "dashboard_split":
            out.append(compose_dashboard(scene, _rect, _label))
            continue
        if scene["template"] in ("floating_insight", "permission_mock",
                                 "code_inspector", "metric_spotlight",
                                 "metric_countup"):
            out.append(compose_editorial_card(scene, _event, _safe))
            continue
        out.append(_rect(a, end, 0, 0, 1080, 1920, _BACKGROUND))
        out.append(_rect(a + 150, end, 92, 135, 896, 7, accent))
        if scene["template"] == "stat_reveal":
            out.append(_label(a+250, end, data["eyebrow"], 540, 400, 38, _MUTED))
            out.append(_label(a+900, end, data["number"], 540, 720, 190,
                              _TEXT, pop=True))
            out.append(_label(a+1400, end, data["label"], 540, 940, 95,
                              accent, pop=True))
            out.append(_label(a+2000, end, data["detail"], 540, 1185, 42, _MUTED))
        elif scene["template"] == "permission_dialog":
            out.append(_label(a+220, end, "SIMULAZIONE • NON È UNO SCREENSHOT", 
                              540, 340, 31, _MUTED))
            out.append(_rect(a+370, end, 110, 550, 860, 640, _PANEL))
            out.append(_label(a+540, end, data["title"], 540, 700, 56, _TEXT))
            out.append(_label(a+840, end, data["command"], 540, 870, 36, _MUTED))
            out.append(_rect(a+1100, end, 175, 995, 310, 105, "#364857"))
            out.append(_rect(a+1100, end, 510, 995, 385, 105, "#91523E"))
            out.append(_label(a+1200, end, data["primary"], 330, 1045, 32, _TEXT))
            out.append(_label(a+1350, end, data["persistent"], 700, 1045, 32,
                              _TEXT, pop=True))
            out.append(_label(a+1700, end, data["detail"], 540, 1310, 35, accent))
        elif scene["template"] == "code_highlight":
            out.append(_label(a+240, end, data["title"], 540, 360, 51, accent))
            out.append(_rect(a+350, end, 90, 515, 900, 795, _PANEL))
            out.append(_label(a+480, end, data["filename"], 540, 595, 37, _TEXT,
                              font="Courier New"))
            lines = data["code"].split("\n")
            for i, line in enumerate(lines):
                y = 730 + 100*i
                if i + 1 == data["highlight_line"]:
                    out.append(_rect(a+980, end, 140, y-55, 800, 95, "#613C43"))
                out.append(_label(a+620+140*i, end, line, 540, y, 34,
                                  accent if i+1 == data["highlight_line"] else
                                  _MUTED, font="Courier New"))
            out.append(_label(a+1500, end, data["detail"], 540, 1415, 34, _MUTED))
    return "".join(out)
