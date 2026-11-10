# Studio visual system and constraints

Actual source: `src/pausio/studio_static/styles.css`, `:root`.

- Background: `--bg` = #0b1017; panels: `--surface`, `--surface-raised`; borders: `--border`.
- Primary copy: `--ink` and `--ink-secondary`; subdued copy: `--muted` and `--faint`.
- Human action: `--accent` = #f4ad7b; retained media: `--keep` = #86d4c5; removed regions: `--removed` = #76545d.
- Focus: `--focus`. Status messages require text labels as well as color.
- Type: offline-first system sans for controls, restrained serif italic for branded editorial emphasis.
- Key surfaces: header; workflow rail; central 9:16 preview stage; right decision inspector; full-width timeline.

Accessibility QA:
- WCAG 2.2 AA contrast targets: 4.5:1 normal text, 3:1 large text/essential controls.
- Keyboard: tab through controls, Space play when not typing, arrow keys ±5 s, timeline slider arrows/Home/End.
- Responsive: no horizontal scrolling at 390 px, no clipped filename, no overlapping export buttons.
- Do not rely on color alone for KEEP/EXCLUDED distinction; pair label, icon and differing fill.
- Respect reduced motion, retain visual focus, restore meaningful interaction state after updates.

Reference inspirations (no copied source):
- https://github.com/vercel-labs/agent-skills/blob/main/skills/web-design-guidelines/SKILL.md
- https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
