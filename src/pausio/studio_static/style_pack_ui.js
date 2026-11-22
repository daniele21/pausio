"use strict";
/* Three Style Packs: review-only comparison of grounded edit candidates.
   The actual video remains unchanged until each typed edit is accepted.
   No generated markup from transcripts, remote services, or preview fakery. */
(() => {
  const el=id=>document.getElementById(id);
  const current=()=>project||{};
  let proposal=null,forMedia=null,selection="visual_explainer";
  let skipped=new Set(),message="";
  const labels={
    authority:"Authority",visual_explainer:"Visual Explainer",
    social_impact:"Social Impact"
  };
  const kindLabels={
    "graphic.overlay.add":"Scheda grafica",
    "video.transform.add":"Movimento camera"
  };
  const time=ms=>(ms/1000).toFixed(1).replace(".",",")+" s";
  const ready=()=>!!current().media&&!!current().plan&&!working();
  // Compare the project revision and opaque media ID; no source paths are exposed.
  const isFresh=()=>proposal&&proposal.base_revision===current().project_revision&&
    forMedia===current().media_id;

  function button(label,action,cls="button button-outline"){
    const node=document.createElement("button");
    node.type="button";node.className=cls;node.textContent=label;
    node.disabled=working();
    node.addEventListener("click",()=>run(action));
    return node;
  }
  function row(candidate){
    const card=document.createElement("article");
    card.className="style-plan-candidate";
    const title=document.createElement("strong");
    title.textContent=(kindLabels[candidate.command_type]||"Intervento")+
      " · "+time(candidate.output_time_ms);
    const evidence=document.createElement("p");
    evidence.textContent=candidate.evidence?.quoted_text
      ? "Dal video: «"+candidate.evidence.quoted_text+"»"
      : "Segnale tecnico · "+(candidate.evidence?.kind||"timestamp");
    const payload=candidate.command_type==="graphic.overlay.add"
      ? candidate.payload.graphic : candidate.payload.effect;
    const description=document.createElement("p");
    description.className="style-plan-metadata";
    description.textContent=candidate.command_type==="graphic.overlay.add"
      ? "Grafica: "+(payload?.kind||"")+
        " · testo tratto dai sottotitoli"
      : "Camera: "+(payload?.kind||"")+
        " · proposta basata su segnali locali";
    const actions=document.createElement("div");actions.className="style-plan-actions";
    actions.append(
      button("Vai al punto",async()=>{
        if(!isFresh())throw Error("Storyboard scaduto. Generane uno nuovo.");
        const outputMs=candidate.output_time_ms;
        const sourceMs=sourceFromOutput(outputMs);
        v.pause();
        v.currentTime=(mode==="rendered"?outputMs:sourceMs)/1000;
        timelineLocate(sourceMs);
      }),
      button("Applica intervento",async()=>{
        if(!isFresh())throw Error("Il progetto è cambiato. Rigenera le proposte.");
        // One canonical command, one undo; never a hidden batch.
        await edit(candidate.command_type,candidate.payload);
        proposal=null;skipped.clear();
        message="Modifica applicata sulla timeline corrente. Rigenera per confrontare gli altri stili.";
        draw();
      },"button button-primary"),
      button("Ignora",async()=>{
        skipped.add(candidate.candidate_id);
        draw();
      },"button button-ghost")
    );
    card.append(title,evidence,description,actions);
    return card;
  }
  function draw(){
    const container=el("style-pack-choices");
    const list=el("style-pack-candidates");
    if(!container||!list)return;
    if(proposal&&!isFresh()){
      proposal=null;skipped.clear();
      message="La timeline è stata modificata. Rigenera i tre storyboard.";
    }
    el("style-pack-generate").disabled=!ready();
    const catalog=current().style_pack_catalog||[];
    container.replaceChildren();
    for(const style of catalog){
      const name=style.id, data=proposal?.variants?.[name];
      const tab=document.createElement("button");
      tab.type="button";tab.className="style-pack-choice";
      tab.setAttribute("aria-pressed",String(name===selection));
      tab.setAttribute("aria-label",labels[name]||style.label);
      tab.disabled=!ready();
      const title=document.createElement("strong");
      title.textContent=labels[name]||style.label;
      const sub=document.createElement("small");
      sub.textContent=data
        ? data.candidates.length+" interventi suggeriti"
        : (name==="authority"?"Sobrio":name==="visual_explainer"
           ?"Esplicativo":"Dinamico");
      tab.append(title,sub);
      tab.addEventListener("click",()=>{selection=name;draw();});
      container.append(tab);
    }
    list.replaceChildren();
    const currentVariant=proposal?.variants?.[selection];
    el("style-pack-selected").textContent=currentVariant
      ? (labels[selection]||selection)+" · "+
        currentVariant.candidates.length+" interventi candidati"
      : "Seleziona uno stile e genera le tre proposte";
    const caption=el("style-pack-caption");
    caption.disabled=!ready()||!(current().captions||[]).length||
      !currentVariant||current().caption_style===currentVariant.caption_preset_suggestion;
    caption.textContent=currentVariant
      ? "Applica sottotitoli: "+currentVariant.caption_preset_suggestion
      : "Applica stile sottotitoli";
    if(currentVariant){
      const available=currentVariant.candidates.filter(c=>!skipped.has(c.candidate_id));
      for(const item of available)list.append(row(item));
      if(!available.length){
        const note=document.createElement("p");note.className="visual-fx-status";
        note.textContent="Nessun altro intervento tecnico suggerito. Non aggiungere effetti solo per riempire.";
        list.append(note);
      }
    }
    el("style-pack-status").textContent=message||(
      !current().plan?"Prepara prima un montaggio.":
      !(current().captions||[]).length
        ?"Aggiungi sottotitoli per proporre schede informative. Gli zoom restano suggerimenti tecnici."
        :"Tre storyboard tecnici, non ancora tre video. Esamina ogni proposta prima di applicarla."
    );
  }
  async function generate(){
    if(!ready())throw Error("Prepara il montaggio prima di generare le proposte.");
    const revision=current().project_revision,mediaId=current().media_id;
    const data=await post("/api/editorial/variants/auto",{revision});
    if(current().project_revision!==revision||current().media_id!==mediaId||
       data.base_revision!==revision)throw Error("Proposte scadute: la timeline è cambiata.");
    proposal=data;forMedia=mediaId;skipped.clear();
    message="Tre regie calcolate da segnali reali. Nulla è stato applicato.";
    draw();
  }
  async function applyCaption(){
    const row=proposal?.variants?.[selection];
    if(!isFresh()||!row)throw Error("Proposte scadute.");
    if(!(current().captions||[]).length)throw Error("Genera prima sottotitoli.");
    await edit("caption.style",{style:row.caption_preset_suggestion});
    proposal=null;skipped.clear();message="Preset sottotitoli applicato alla timeline corrente.";
    draw();
  }
  el("style-pack-generate").addEventListener("click",()=>run(generate));
  el("style-pack-caption").addEventListener("click",()=>run(applyCaption));
  window.pausioStylePacks={update:draw};
  if(project)draw();
})();
