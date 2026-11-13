# Schede grafiche animate — Pausio v5

Status: implemented on the v5 development branch; not present in the older v0.1.0 wheel. Studio → Tagli / Video FX → Schede grafiche animate.

1. Place the playhead in a retained source interval. Add one concise text card with a style (Headline, Stat, Code, Tip), entrance (Fade, Pop, Slide), duration (0.4–12s), horizontal/vertical placement, font size and a solid color. A record is saved as a typed event and can be undone/redone.
2. Change text, position or size with **Salva modifiche**, or remove the card. The source-time interval must remain within its selected retained segment.
3. Press **Genera preview grafica**, switch to **Preview FFmpeg**, listen, and export as usual. The plain **Simulazione** does not display the graphic effect.
4. Export .pausio.json v5 to retain the exact instructions and history. Import with the same original video; no raw media or fonts are embedded.

The backend uses only FFmpeg/libass already required for burned-in subtitles; no new model, software runtime, web service or paid dependency. This is informational text, not an embedded image, screenshot, rich code syntax highlighter, B-roll, or object segmentation. The text uses safe allowlisted fonts and fixed native ASS transitions, which are rendered after camera zoom to keep it stationary. Test on actual phones for platform UI safe areas and typography.

## Visual templates and editing (v5)

Each graphic `kind` renders with a distinct local libass template: **Headline** is clean outlined text, **Stat** is a bold, dark number card, **Code** uses monospaced text on a dark code card, and **Tip** uses a soft contrasting information card. Existing typed graphics can now update **kind, animation, duration (400–12,000ms), color, text, X/Y and font size** through the canonical `graphic.overlay.update` command; no browser-only style overrides. Pausio rejects duration changes that would extend beyond the bound KEEP segment. Generate an FFmpeg preview to inspect the actual composite; fonts are system-dependent and may be substituted.
