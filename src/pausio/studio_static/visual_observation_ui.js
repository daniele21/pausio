"use strict";
/* Local, per-session human opt-in for sending selected still frames to ChatGPT.
   The checkbox never persists to localStorage or portable project JSON. */
(() => {
  const input = document.getElementById("visual-sharing-enabled");
  const note = document.getElementById("visual-sharing-status");
  if (!input || !note) return;
  input.addEventListener("change", () => run(async () => {
    const value = input.checked;
    input.disabled = true;
    try {
      const next = await post("/api/observation/consent", {enabled: value});
      update(next);
    } catch (error) {
      input.checked = !!project?.visual_sharing_enabled;
      throw error;
    } finally {
      input.disabled = !project?.file;
    }
  }));
  function draw(state) {
    input.disabled = !state?.file;
    input.checked = state?.visual_sharing_enabled === true;
    note.textContent = !state?.file
      ? "Importa un video per abilitare la condivisione."
      : input.checked
      ? "Attivo solo per questa sessione e questo video. Revoca qui in qualsiasi momento."
      : "Disattivato: ChatGPT non può ottenere immagini del video tramite MCP.";
  }
  window.pausioVisualObservation = {update: draw};
  if (project) draw(project);
})();
