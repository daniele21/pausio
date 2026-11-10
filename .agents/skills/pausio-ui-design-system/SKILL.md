---
name: pausio-ui-design-system
description: Use when implementing or reviewing Pausio Studio visual hierarchy, CSS tokens, typography, spacing, contrast, responsive behavior, component states, microcopy, focus, motion or accessibility. Do not alter editor data semantics.
---

# Pausio interface design system

## Visual direction
A focused **cinematic workbench** for a human voice—not a sales dashboard or generic SaaS template. Dark ink surfaces reduce glare around footage; warm amber signals creator action; quiet mint means media **kept**. Color never carries meaning by itself.

## Implementation rules
1. Inspect the semantic CSS tokens in `src/pausio/studio_static/styles.css` before adding styles. Reuse ink, surfaces, borders, accent, keep, removed, focus and typography variables; do not create an ad-hoc parallel palette.
2. Establish hierarchy through spacing and type scale before adding effects. Media preview and the next workflow decision get prominence; inspector supports the task, not the reverse.
3. Use legible system fonts offline; no network-loaded design assets or bloated icon library. Prefer a few consistent SVG strokes.
4. All buttons/inputs must have visible hover, focus-visible, disabled, busy and error states. Accessible names and semantic labels are mandatory; no clickable div when a button works.
5. Support 320 px mobile through wide desktop, 200% zoom, long Italian filenames, narrow panels, and prefers-reduced-motion.
6. Keep touch targets generous, timeline readable, numbers tabular and essential text non-truncated. Avoid overly animated or decorative controls that reduce video attention.
7. Validate keyboard focus order, text/interactive contrast, active tab semantics, aria-live status and screen-reader descriptions in addition to visual review.

## Review gate
Capture before/after screenshots at 1440x900, 1024x768, 390x844 and 200% zoom when a browser runner is available. Ensure no action is hidden under video/timeline.

See [tokens and accessibility](references/tokens.md).
