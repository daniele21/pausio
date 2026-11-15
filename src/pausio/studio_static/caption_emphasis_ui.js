"use strict";
/* Reversible creator-controlled semantic word highlights. The renderer, not
   this browser module, is the authority for exported ASS subtitle timing. */
(() => {
  const el = id => document.getElementById(id);
  const list = el("caption-emphasis-cue");
  const wordsBox = el("caption-emphasis-words");
  const status = el("caption-emphasis-status");
  let chosenId = null;

  function wordsOf(cue) {
    return Array.isArray(cue.words) && cue.words.length
      ? cue.words.map(word => word.text)
      : cue.text.trim().split(/\s+/);
  }

  function draw(state = project) {
    const cues = state?.captions || [];
    if (!cues.length) {
      chosenId = null;
      list.replaceChildren();
      wordsBox.replaceChildren();
      status.textContent = "Genera i sottotitoli per selezionare le parole.";
      return;
    }
    if (!cues.some(c => c.id === chosenId)) chosenId = cues[0].id;
    list.replaceChildren(...cues.map(cue => {
      const option = document.createElement("option");
      option.value = cue.id;
      option.textContent = cue.text.slice(0, 80);
      return option;
    }));
    list.value = chosenId;
    const cue = cues.find(c => c.id === chosenId);
    const selected = new Set(cue.emphasis_indices || []);
    const color = state?.caption_config?.highlight_color || "#FFCD65";
    const disabled = working();
    list.disabled = disabled;
    wordsBox.replaceChildren();
    for (const [index, token] of wordsOf(cue).entries()) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "caption-emphasis-word";
      button.textContent = token;
      const highlighted = selected.has(index);
      button.setAttribute("aria-pressed", String(highlighted));
      button.setAttribute("aria-label",
        (highlighted ? "Disattiva" : "Attiva") + " evidenziazione: " + token);
      button.style.setProperty("--word-accent", color);
      button.disabled = disabled;
      button.addEventListener("click", () => run(async () => {
        const next = new Set(cue.emphasis_indices || []);
        if (next.has(index)) next.delete(index);
        else if (next.size < 6) next.add(index);
        else throw Error("Massimo sei parole evidenziate per frase.");
        chosenId = cue.id;
        await edit("caption.emphasize", {
          caption_id: cue.id, indices: [...next].sort((a, b) => a - b)
        });
      }));
      wordsBox.append(button);
    }
    status.textContent = selected.size + "/6 parole evidenziate. " +
      (cue.words?.length
        ? "L'allineamento parola-per-parola è disponibile."
        : "Senza timestamp parola, l'enfasi rimane visibile per tutta la frase.");
  }
  list.addEventListener("change", () => {
    chosenId = list.value;
    draw();
  });
  window.pausioCaptionEmphasis = {update: draw};
  if (project) draw();
})();
