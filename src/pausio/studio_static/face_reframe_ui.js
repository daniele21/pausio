"use strict";
/* Face-aware STABLE crop only, fully local opt-in. This is not a tracker.
   No request automatically modifies a project or recognizes an identity. */
(() => {
  const e=id=>document.getElementById(id);
  const panel=document.createElement("section");
  panel.className="visual-fx-panel face-reframe-panel";
  panel.setAttribute("aria-labelledby","face-reframe-title");
  panel.innerHTML='<header class="visual-fx-heading"><h3 id="face-reframe-title">Centra il volto · opzionale</h3><p>Analisi locale di 5 fotogrammi. Se il volto è instabile, multiplo o fuori crop, nessun movimento viene proposto. Non è tracking continuo.</p></header>';
  const controls=document.createElement("div");
  controls.className="visual-fx-controls";
  const label=document.createElement("label");
  label.setAttribute("for","face-effect-id");label.textContent="Effetto da ricentrare";
  const selector=document.createElement("select");selector.id="face-effect-id";
  label.append(selector);
  const action=document.createElement("button");
  action.id="face-analyze";action.type="button";action.className="button button-outline button-full";
  action.textContent="Analizza volto sul Mac";
  const status=document.createElement("p");status.id="face-analysis-status";
  status.className="visual-fx-status";status.setAttribute("role","status");
  const confirm=document.createElement("button");
  confirm.id="face-accept";confirm.type="button";confirm.className="button button-primary button-full";
  confirm.textContent="Applica il centro suggerito";confirm.hidden=true;
  controls.append(label,action,status,confirm);panel.append(controls);
  e("visual-fx-panel")?.after(panel);
  let proposal=null,proposalMediaId=null,selectedId=null;
  function update(){
    const fx=project?.video_fx||[];
    const prev=selectedId||selector.value;
    selector.replaceChildren();
    for(const item of fx){
      const option=document.createElement("option");option.value=item.id;
      option.textContent=(item.kind==="punch"?"Punch-in":"Zoom")+
        " · "+(item.start_ms/1000).toFixed(2)+"s";
      selector.append(option);
    }
    if(fx.some(i=>i.id===prev))selector.value=prev;
    selectedId=selector.value||null;
    const enabled=!!selectedId&&!working();
    action.disabled=!enabled;selector.disabled=!enabled;
    panel.hidden=!project?.plan;
    if(proposal && (proposal.base_revision!==project.project_revision ||
                    proposalMediaId!==project.media_id ||
                    proposal.effect_id!==selectedId)){
      proposal=null;confirm.hidden=true;
      status.textContent="Il progetto o l'effetto è cambiato. Ricalcola il centro.";
    }
  }
  selector.addEventListener("change",()=>{
    selectedId=selector.value;proposal=null;confirm.hidden=true;
    status.textContent="Scegli Analizza per un nuovo effetto.";
  });
  action.addEventListener("click",()=>run(async()=>{
    if(!selectedId)throw Error("Seleziona prima uno zoom.");
    const revision=project.project_revision;
    const mediaId=project.media_id;
    action.disabled=true;status.textContent="Analisi dei fotogrammi in locale…";
    try{
      const result=await post("/api/visual-fx/face-anchor",{
        revision,effect_id:selectedId
      });
      if(project.project_revision!==revision || project.media_id!==mediaId ||
          selectedId!==result.effect_id){
        throw Error("Proposta non valida dopo una modifica al progetto.");
      }
      proposal=result;proposalMediaId=mediaId;
      if(result.status!=="ready"){
        confirm.hidden=true;
        status.textContent="Non applicato: "+
          (result.reason||"volto non rilevato con affidabilità")+".";
      }else{
        confirm.hidden=false;
        status.textContent="Centro suggerito: X "+result.anchor_x_pct+
          "% · Y "+result.anchor_y_pct+"% da "+result.samples+
          " fotogrammi. Controlla sempre la preview.";
      }
    }finally{action.disabled=false;}
  }));
  confirm.addEventListener("click",()=>run(async()=>{
    if(!proposal||proposal.status!=="ready"||
        proposal.base_revision!==project.project_revision||
        proposalMediaId!==project.media_id){
      throw Error("La proposta del volto è scaduta.");
    }
    const fx=(project.video_fx||[]).find(e=>e.id===proposal.effect_id);
    if(!fx)throw Error("L'effetto non esiste più.");
    await edit("video.transform.update",{
      effect:{...fx,anchor_x_pct:proposal.anchor_x_pct,
              anchor_y_pct:proposal.anchor_y_pct}
    });
    confirm.hidden=true;proposal=null;status.textContent=
      "Nuovo centro salvato come istruzione. Rigenera la preview FFmpeg.";
  }));
  window.pausioFaceReframe={update};
  if(typeof project!=="undefined"&&project)update();
})();
