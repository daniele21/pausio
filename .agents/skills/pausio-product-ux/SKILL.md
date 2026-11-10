---
name: pausio-product-ux
description: Use when designing or changing Pausio Studio journeys, empty/loading/error states, creator workflows, confirmations, clarity of AI decisions or user-facing copy. Ensure real tasks are discoverable and every edit is reversible.
---

# Pausio product UX — make editing understandable

## Product principle
Creators want to finish a trustworthy talking-head video, not learn FFmpeg or new AI terminology. Prioritize explicit decisions, instant comprehension and the feeling of control.

## Workflow
1. Start from an actual user job: **import → analyze → review KEEP intervals → explicitly confirm → render → download**. ClosedRoom transcription is optional and must not block editing.
2. Define the user's mental model in plain Italian before designing a screen. Use consistent labels: "Originale", "Montaggio", "Mantieni", "Escluso", "Conferma montaggio", "Esporta MP4". Never label unimplemented semantics "AI automatic".
3. Design **empty, loading, ready, error and completed** states for each action. Every error must explain the next safe action.
4. Provide understandable **Importa progetto / Esporta progetto** actions with clear source pairing; every edit must be replayable. Show exactly what was proposed and what will be removed. Require explicit approval; modifying a cut invalidates approval and any previous export.
5. Preview editing decisions *before* rendering. Clearly mark the browser's seek-simulation as an approximation, not final AV quality.
6. Keep the original immutable and make recovery easy: restore suggestion, retain all, add missed region, edit seconds, **Undo/Redo**. State clearly that Studio autosaves the original video locally until the creator explicitly deletes stored data. Test recovery after closing and reopening.
7. Test with a first-time creator without CLI knowledge. Measure task completion and editing clarity, not merely visual appeal.

## Before shipping
- The primary next action is always visible.
- No fake disabled controls that imply functionality; explain missing ClosedRoom or incompatible codecs.
- Empty states invite an action; failures are actionable; successful exports provide a direct download.
- No dark patterns or hidden automated deletion.

See [creator journey and copy](references/creator-journey.md).
