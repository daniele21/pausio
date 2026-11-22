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
  const matchesActive=()=>!current().active_variant||
    selection===current().active_variant;

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
      ? "Dai sottotitoli: «"+candidate.evidence.quoted_text+"»"
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
        if(!matchesActive())throw Error("Prima attiva la versione scelta in «Versioni del montaggio».");
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
  function drawVariants(){
    const rows=current().variant_workspaces||[];
    const create=el("style-variants-create");
    const list=el("style-variant-workspaces");
    if(!create||!list)return;
    create.hidden=rows.length>0;
    create.disabled=!ready()||rows.length>0;
    el("style-variants-import").disabled=!ready()||rows.length>0;
    el("style-variants-export").hidden=rows.length===0;
    const allReviewed=rows.length===3&&rows.every(item=>item.approved);
    const run=el("style-variants-render-all");
    run.disabled=!ready()||!allReviewed;
    run.textContent=allReviewed?"Esporta tutte e 3 · MP4":
      "Conferma tutti e 3 i montaggi per esportare";
    const download=el("style-variants-download-all");
    download.hidden=!current().batch_export_ready;
    const status=el("style-variants-render-status");
    const job=current().job||{};
    if(job.kind==="render_variants"&&job.status==="running"){
      status.textContent="Generazione MP4 "+(job.completed||0)+"/3 completata. "+
        "Ultima versione completata: "+(labels[job.variant]||"nessuna")+
        ". Lo ZIP sarà disponibile solo a render concluso.";
    }else if(job.kind==="render_variants"&&job.status==="failed"){
      status.textContent="Esportazione non riuscita: "+(job.error||"controlla gli asset locali")+
        ". Nessun ZIP parziale è disponibile.";
    }else if(current().batch_export_ready){
      status.textContent="Tre MP4 verificati e pronti nel pacchetto ZIP. "+
        "Le versioni e le approvazioni restano inalterate.";
    }else{
      status.textContent=allReviewed
        ?"Tutte e tre le versioni approvate: esportazione locale 1080 × 1920."
        :"Conferma ciascuna versione prima dell'export multiplo ("+
          rows.filter(x=>x.approved).length+"/3).";
    }
    list.replaceChildren();
    for(const item of rows){
      const node=document.createElement("button");
      node.type="button";
      node.className="style-variant-choice";
      node.setAttribute("aria-pressed",String(item.active));
      node.setAttribute("aria-label",(labels[item.id]||item.id)+
        (item.active?" · versione attiva":" · passa a questa versione"));
      node.disabled=!ready()||item.active;
      const title=document.createElement("strong");
      title.textContent=labels[item.id]||item.id;
      const details=document.createElement("small");
      details.textContent=(item.approved?"Approvata":"Da revisionare")+
        " · "+item.scene_count+" scene · rev "+item.revision;
      node.append(title,details);
      node.addEventListener("click",()=>run(()=>switchVariant(item.id)));
      list.append(node);
    }
    el("style-variant-status").textContent=rows.length
      ? "Attiva: "+(labels[current().active_variant]||current().active_variant)+
        ". Ogni versione conserva i propri tagli, effetti, sottotitoli e cronologia. "+
        (current().autosaved
          ?"Salvataggio locale recuperabile dopo il riavvio."
          :"Sessione temporanea: esporta la singola versione per conservarla.")
      : "Nessuna variante creata. Il montaggio attuale sarà copiato tre volte.";
  }
  async function exportAll(){
    const rows=current().variant_workspaces||[];
    if(rows.length!==3||rows.some(x=>!x.approved))
      throw Error("Devi confermare tutti e tre i montaggi prima di esportarli.");
    if(!ready())throw Error("Un'altra elaborazione è in corso.");
    const confirmed=window.confirm(
      "Esportare tre video verticali 1080 × 1920 in uno ZIP locale? "+
      "Ogni versione mantiene le proprie modifiche, senza caricare file online."
    );
    if(!confirmed)return;
    const state=await post("/api/variants/render-all",{
      revision:current().project_revision,media_id:current().media_id
    });
    update(state);
    message="Rendering locale di tre versioni avviato. "+
      "Lo ZIP apparirà solo dopo la verifica di tutti i file.";
    draw();
  }
  async function createVariants(){
    if(!ready())throw Error("Prepara il montaggio prima di creare le versioni.");
    const revision=current().project_revision;
    const state=await post("/api/variants/create",{revision});
    update(state);
    proposal=null;skipped.clear();selection="authority";
    message="Tre timeline indipendenti create. Seleziona una versione per personalizzarla.";
    draw();
  }
  async function importVariants(file){
    if(!file)throw Error("Seleziona il file JSON con le tre versioni.");
    if(file.size>4*1024*1024)throw Error("Il bundle supera il limite locale di 4 MB.");
    let bundle;
    try{bundle=JSON.parse(await file.text());}
    catch(_error){throw Error("Il file delle tre versioni non contiene JSON valido.");}
    if(!ready())throw Error("Importa prima il video originale.");
    const state=await post("/api/variants/import",{
      revision:current().project_revision,bundle
    });
    proposal=null;forMedia=null;skipped.clear();
    selection=state.active_variant||"authority";
    update(state);
    message="Tre versioni importate e collegate al video verificato.";
    draw();
  }
  async function switchVariant(styleId){
    if(!ready())throw Error("Completa prima l'elaborazione corrente.");
    if(mode==="rendered")changeMode("original");
    const revision=current().project_revision;
    const state=await post("/api/variants/switch",{
      revision,style_id:styleId
    });
    proposal=null;skipped.clear();forMedia=null;selection=styleId;
    update(state);
    message="Versione attiva: "+(labels[styleId]||styleId)+
      ". Preview e export si riferiscono a questa timeline.";
    draw();
  }
  function draw(){
    drawVariants();
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
      !currentVariant||!matchesActive()||
      current().caption_style===currentVariant.caption_preset_suggestion;
    caption.textContent=currentVariant
      ? "Applica sottotitoli: "+currentVariant.caption_preset_suggestion
      : "Applica stile sottotitoli";
    if(currentVariant){
      const available=currentVariant.candidates.filter(c=>!skipped.has(c.candidate_id));
      for(const item of available){
        const node=row(item);
        const apply=node.querySelector(".button-primary");
        if(apply)apply.disabled=!ready()||!matchesActive();
        list.append(node);
      }
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
    if(!matchesActive())throw Error("Attiva prima la versione scelta.");
    if(!(current().captions||[]).length)throw Error("Genera prima sottotitoli.");
    await edit("caption.style",{style:row.caption_preset_suggestion});
    proposal=null;skipped.clear();message="Preset sottotitoli applicato alla timeline corrente.";
    draw();
  }
  el("style-variants-create").addEventListener("click",()=>run(createVariants));
  el("style-variants-render-all").addEventListener("click",()=>run(exportAll));
  el("style-variants-import").addEventListener("click",()=>{
    el("style-variants-input").click();
  });
  el("style-variants-input").addEventListener("change",event=>{
    const input=event.currentTarget;
    const file=input.files?.[0];
    input.value="";
    if(file)run(()=>importVariants(file));
  });
  el("style-pack-generate").addEventListener("click",()=>run(generate));
  el("style-pack-caption").addEventListener("click",()=>run(applyCaption));
  window.pausioStylePacks={update:draw};
  if(project)draw();
})();
