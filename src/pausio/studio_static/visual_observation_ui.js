"use strict";
/* Volatile local creator opt-ins; visual and audio are independent.
   Neither permission persists in the exported project or browser storage. */
(() => {
  const bindings = [
    ["visual-sharing-enabled","visual-sharing-status",
     "visual_sharing_enabled","/api/observation/consent","fotogrammi","immagini"],
    ["audio-sharing-enabled","audio-sharing-status",
     "audio_sharing_enabled","/api/observation/audio-consent","audio","audio"],
  ];
  function draw(state) {
    for (const [id,status,key,,label,noun] of bindings) {
      const checkbox=document.getElementById(id);
      const message=document.getElementById(status);
      if (!checkbox || !message) continue;
      checkbox.disabled=!state?.file;
      checkbox.checked=state?.[key]===true;
      message.textContent=!state?.file
        ? "Importa un video per abilitare la condivisione."
        : checkbox.checked
        ? "Attivo soltanto in questa sessione. Puoi revocare il consenso qui."
        : "Disattivato: ChatGPT non può ottenere "+noun+" tramite MCP.";
    }
  }
  for (const [id,,key,url] of bindings) {
    const checkbox=document.getElementById(id);
    if (!checkbox) continue;
    checkbox.addEventListener("change",()=>run(async()=>{
      const enabled=checkbox.checked;
      checkbox.disabled=true;
      try {
        update(await post(url,{enabled}));
      } catch (error) {
        checkbox.checked=project?.[key]===true;
        throw error;
      } finally {
        checkbox.disabled=!project?.file;
      }
    }));
  }
  window.pausioVisualObservation={update:draw};
  if(project)draw(project);
})();
