"use strict";
/* Editorial treatment proposals: read-only until a human accepts typed edits. */
(() => {
  const e=id=>document.getElementById(id);
  const current=()=>project||{};
  let proposal=null,forMedia=null,ignored=new Set(),message="";
  const reasons={
    caption_stat:"Dato numerico letteralmente pronunciato e sottotitolato",
    caption_code:"Nome file presente nei sottotitoli revisionati",
    caption_tip:"Suggerimento pratico presente nei sottotitoli",
    cut_boundary:"Taglio confermato nella timeline",
    asr_phrase_boundary:"Inizio frase rilevato nella trascrizione",
    measured_waveform_rise:"Variazione della waveform misurata"
  };
  const second=ms=>(ms/1000).toFixed(1).replace(".",",")+" s";
  function label(candidate){
    if(candidate.command_type==="graphic.overlay.add"){
      const kind=candidate.payload.graphic.kind;
      return ({stat:"Dato",code:"Codice",tip:"Suggerimento"})[kind]||"Grafica";
    }
    return "Movimento camera";
  }
  function card(candidate){
    const div=document.createElement("article");
    div.className="visual-fx-entry is-suggested";
    div.dataset.editorialId=candidate.candidate_id;
    const title=document.createElement("strong");
    title.textContent=label(candidate)+" · "+second(candidate.output_time_ms);
    const evidence=document.createElement("p");
    const reason=reasons[candidate.evidence?.kind]||"Segnale tecnico verificato";
    const exact=candidate.evidence?.quoted_text;
    evidence.textContent=reason+(typeof exact==="string"?" · «"+exact+"»":"")+
      " · punteggio tecnico "+candidate.score_0_100+"/100";
    const actions=document.createElement("div");actions.className="visual-fx-entry-actions";
    const button=(caption,action,cls)=>{
      const node=document.createElement("button");node.type="button";
      node.className=cls;node.textContent=caption;
      node.disabled=working();
      node.addEventListener("click",action);return node;
    };
    actions.append(
      button("Accetta",()=>run(async()=>{
        if(!proposal||proposal.base_revision!==current().project_revision||
           proposal.media_sha256!==current().media?.sha256)
          throw Error("Proposta scaduta: ricalcola la regia.");
        await edit(candidate.command_type,candidate.payload);
        proposal=null;ignored.clear();
        message="Modifica applicata. Ricalcola le proposte per la nuova revisione.";
        draw();
      }),"button button-primary"),
      button("Ignora",()=>{ignored.add(candidate.candidate_id);draw();},
             "button button-ghost")
    );
    div.append(title,evidence,actions);
    return div;
  }
  function draw(){
    const ready=!!current().media&&!!current().plan&&!working();
    e("editorial-preset").disabled=!ready;
    e("editorial-suggest").disabled=!ready;
    if(proposal&&(proposal.base_revision!==current().project_revision||
                  forMedia!==current().media_id)){
      proposal=null;ignored.clear();
      message="Il progetto è cambiato. Ricalcola le proposte editoriali.";
    }
    const items=e("editorial-proposals");
    items.replaceChildren();
    if(proposal){
      const available=proposal.candidates.filter(x=>!ignored.has(x.candidate_id));
      if(!available.length){
        const note=document.createElement("p");
        note.className="visual-fx-status";
        note.textContent="Nessun nuovo intervento motivato da proporre. Il video può restare così.";
        items.append(note);
      }else for(const item of available)items.append(card(item));
    }
    e("editorial-status").textContent=message||(
      !current().plan?"Analizza prima il video.":
      !(current().captions||[]).length
      ?"Puoi generare proposte di camera; per le schede informative crea prima sottotitoli revisionati."
      :"Scegli il profilo e genera proposte motivabili. Ogni intervento richiede approvazione."
    );
  }
  async function suggest(){
    if(!current().plan)throw Error("Analizza prima il video.");
    const revision=current().project_revision,mediaId=current().media_id;
    const data=await post("/api/editorial/suggest",{
      revision,preset:e("editorial-preset").value
    });
    if(current().project_revision!==revision||current().media_id!==mediaId||
       data.base_revision!==revision)
      throw Error("Progetto modificato. Ricalcola la regia.");
    proposal=data;forMedia=mediaId;ignored.clear();
    message=data.candidates.length+" proposte · nessuna modifica applicata. "+
      ((data.missing_signals||[]).includes("reviewed_caption_data")?
        "Sottotitoli mancanti: le schede informative non possono essere suggerite.":"");
    draw();
  }
  e("editorial-suggest").addEventListener("click",()=>run(suggest));
  e("editorial-preset").addEventListener("change",()=>{
    proposal=null;ignored.clear();
    message="Profilo modificato. Genera nuovamente le proposte.";
    draw();
  });
  window.pausioEditorial={update:draw};
  if(project)draw();
})();