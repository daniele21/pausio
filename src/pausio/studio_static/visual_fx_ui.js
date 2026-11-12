"use strict";
/* Pausio Video FX: ephemeral proposals + canonical typed source-time edits.
   The renderer owns the actual camera motion. Browser preview requires FFmpeg.
   No cloud requests, third-party libraries or auto-applied edits. */
(() => {
  let proposal = null;
  let proposalStatus = "";
  let ignored = new Set();
  let ignoredContext = "";
  let selectedFxId = null;
  let proposalForMediaId = null;
  const e = id => document.getElementById(id);
  const current = () => project || {};
  const fxList = () => current().video_fx || [];
  const formatMs = ms => {
    const seconds=Math.floor(ms/1000),centis=Math.round(ms%1000/10);
    return String(Math.floor(seconds/60)).padStart(2,"0")+":"+
      String(seconds%60).padStart(2,"0")+"."+String(centis).padStart(2,"0");
  };
  const button = (label,handler,cls="button button-outline") => {
    const b=document.createElement("button");
    b.type="button";b.className=cls;b.textContent=label;
    b.addEventListener("click",handler);
    return b;
  };
  function title(kind){
    return ({punch:"Punch-in",slow_push:"Zoom progressivo",ease_push:"Zoom morbido",ratchet:"Ratchet · 3 scatti"})[kind]||"Video FX";
  }
  function ignoredKey(preset){
    return "pausio.fx.ignored.v1."+String(current().media_id||"")+"."+preset;
  }
  function loadIgnored(){
    const preset=e("visual-fx-preset").value;
    const key=ignoredKey(preset);
    if(ignoredContext===key)return;
    ignoredContext=key;ignored=new Set();
    try{
      const saved=JSON.parse(localStorage.getItem(key)||"[]");
      if(Array.isArray(saved))saved.slice(0,100).forEach(v=>{
        if(typeof v==="string" && /^[0-9a-f]{32}$/.test(v))ignored.add(v);
      });
    }catch(_error){}
  }
  function persistIgnored(){
    try{localStorage.setItem(ignoredContext,JSON.stringify([...ignored].slice(-100)));}
    catch(_error){ /* Private browsing may disable localStorage. */ }
  }
  function status(message){
    proposalStatus=message;e("visual-fx-suggest-status").textContent=message;
  }
  function field(label,value,attrs={}){
    const box=document.createElement("label");box.textContent=label;
    const input=document.createElement("input");
    input.type="number";input.value=String(value);
    input.min=String(attrs.min??0);input.max=String(attrs.max??100);
    input.step=String(attrs.step??1);
    input.dataset.fxField=attrs.name||"";
    input.setAttribute("aria-label",label);
    box.append(input);
    return {box,input};
  }
  function editorEffect(effect){
    const item=document.createElement("div");
    item.className="visual-fx-entry"+(selectedFxId===effect.id?" is-selected":"");
    item.dataset.visualFxId=effect.id;
    const head=document.createElement("strong");
    head.textContent=title(effect.kind)+" · "+
      (effect.end_scale_pct/100).toFixed(2)+"×";
    const desc=document.createElement("p");
    desc.textContent="Sorgente "+formatMs(effect.start_ms)+" – "+
      formatMs(effect.end_ms)+" · modificabile ed esportabile";
    const controls=document.createElement("div");
    controls.className="visual-fx-edit-grid";
    const start=field("Inizio (s)",(effect.start_ms/1000).toFixed(2),
                      {min:0,max:172800,step:0.05});
    const end=field("Fine (s)",(effect.end_ms/1000).toFixed(2),
                    {min:0,max:172800,step:0.05});
    const scale=field("Zoom finale (%)",effect.end_scale_pct,{min:100,max:130});
    const x=field("Centro X (%)",effect.anchor_x_pct,{min:0,max:100});
    const y=field("Centro Y (%)",effect.anchor_y_pct,{min:0,max:100});
    const kind=document.createElement("label");kind.textContent="Movimento";
    const select=document.createElement("select");
    for(const value of ["punch","slow_push","ease_push","ratchet"]){
      const option=document.createElement("option");
      option.value=value;option.textContent=title(value);
      select.append(option);
    }
    select.value=effect.kind;kind.append(select);
    for(const o of [start,end,scale,x,y])controls.append(o.box);
    controls.append(kind);
    const actions=document.createElement("div");actions.className="visual-fx-entry-actions";
    actions.append(button("Salva modifiche",()=>run(async()=>{
      for(const input of item.querySelectorAll("input[type=number]")){
        if(!input.checkValidity())throw Error("Controlla i limiti di Video FX.");
      }
      const kindValue=select.value;
      const zoom=Math.round(Number(scale.input.value));
      const updated={
        ...effect,
        start_ms:Math.round(Number(start.input.value)*1000),
        end_ms:Math.round(Number(end.input.value)*1000),
        kind:kindValue, start_scale_pct:kindValue==="punch"?zoom:100,
        end_scale_pct:zoom,
        anchor_x_pct:Math.round(Number(x.input.value)),
        anchor_y_pct:Math.round(Number(y.input.value))
      };
      await edit("video.transform.update",{effect:updated});
    })));
    actions.append(button("Rimuovi",()=>run(()=>edit(
      "video.transform.remove",{effect_id:effect.id}
    )),"button button-ghost"));
    item.append(head,desc,controls,actions);
    return item;
  }
  function candidateView(candidate){
    const item=document.createElement("div");
    item.className="visual-fx-entry is-suggested";
    const effect=candidate.effect;
    const head=document.createElement("strong");
    head.textContent=title(effect.kind)+" · "+
      (effect.end_scale_pct/100).toFixed(2)+"×";
    const desc=document.createElement("p");
    const reason=candidate.evidence?.kind==="cut_boundary"?
      "Dopo un taglio reale":"Inizio frase con timestamp ASR";
    desc.textContent=formatMs(effect.start_ms)+" – "+
      formatMs(effect.end_ms)+" · "+reason+
      " · punteggio tecnico "+candidate.score_0_100+"/100";
    const actions=document.createElement("div");actions.className="visual-fx-entry-actions";
    actions.append(button("Accetta",()=>run(async()=>{
      if(!proposal || proposal.base_revision!==current().project_revision)
        throw Error("Proposta scaduta. Ricalcola i suggerimenti.");
      await edit("video.transform.add",{effect});
      // The project revision changed. Recalculate candidates against the new
      // timeline and exclude the accepted effect, never replay stale writes.
      await suggest();
    }),"button button-primary"));
    actions.append(button("Ignora",()=>{
      ignored.add(candidate.candidate_id);persistIgnored();draw();
    },"button button-ghost"));
    item.append(head,desc,actions);
    return item;
  }
  function draw(){
    if(!e("visual-fx-panel"))return;
    loadIgnored();
    const has=!!current().media && !!current().plan;
    const busy=working();
    for(const id of ["visual-fx-add","visual-fx-suggest","visual-fx-preview"])
      e(id).disabled=!has||busy;
    for(const id of ["visual-fx-preset","visual-fx-kind","visual-fx-scale"])
      e(id).disabled=!has||busy;
    const controls=e("visual-fx-list");controls.replaceChildren();
    const effects=fxList();
    if(!effects.length){
      const empty=document.createElement("p");
      empty.className="visual-fx-status";empty.textContent="Nessun movimento applicato. Il video originale resta invariato.";
      controls.append(empty);
    }else for(const fx of effects)controls.append(editorEffect(fx));
    if(proposal && (proposal.base_revision!==current().project_revision ||
                    proposalForMediaId!==current().media_id)){
      proposal=null;proposalStatus="Il progetto è cambiato. Ricalcola i suggerimenti.";
    }
    e("visual-fx-suggest-status").textContent=proposalStatus;
    const suggestions=e("visual-fx-proposals");
    suggestions.replaceChildren();
    if(proposal){
      const available=proposal.candidates.filter(x=>
        !ignored.has(x.candidate_id) && !effects.some(e=>e.id===x.candidate_id));
      if(!available.length){
        const empty=document.createElement("p");
        empty.className="visual-fx-status";
        empty.textContent="Nessun nuovo effetto adatto a questo preset. Va bene anche così.";
        suggestions.append(empty);
      }else{
        for(const candidate of available)suggestions.append(candidateView(candidate));
      }
    }
    drawLane();
  }
  function drawLane(){
    const track=e("timeline-visual-fx-track"),lane=e("visual-fx-lane");
    const surface=e("timeline-surface");
    if(!track||!lane||!surface)return;
    const available=!!current().media && !!current().plan;
    track.hidden=!available;
    surface.classList.toggle("has-visual-fx",available);
    lane.replaceChildren();
    e("visual-fx-lane-empty").hidden=fxList().length>0;
    if(!available)return;
    const duration=current().media.duration_ms;
    for(const fx of fxList()){
      const marker=button(title(fx.kind),()=>{
        selectedFxId=fx.id;
        const at=mode==="rendered"?outputTime(fx.start_ms):fx.start_ms;
        v.currentTime=Math.max(0,at)/1000;
        draw();
        const target=e("visual-fx-list").querySelector(
          '[data-visual-fx-id="'+fx.id+'"]');
        target?.scrollIntoView({block:"nearest",behavior:"smooth"});
      },"visual-fx-mark"+(selectedFxId===fx.id?" is-selected":""));
      marker.style.left=(fx.start_ms/duration*100).toFixed(4)+"%";
      marker.style.width=Math.max(0.6,(fx.end_ms-fx.start_ms)/duration*100)+"%";
      marker.title=title(fx.kind)+" · "+formatMs(fx.start_ms)+
        "–"+formatMs(fx.end_ms)+" · "+(fx.end_scale_pct/100).toFixed(2)+"×";
      marker.setAttribute("aria-label",marker.title);
      lane.append(marker);
    }
  }
  async function suggest(){
    if(!current().plan)throw Error("Crea prima il montaggio.");
    const preset=e("visual-fx-preset").value;
    const requestedMediaId=current().media_id;
    const response=await post("/api/visual-fx/suggest",{
      revision:current().project_revision,preset
    });
    if(requestedMediaId!==current().media_id){
      // Studio returns media_id as SHA-256; changing media while a promise
      // is pending must never show suggestions from the previous file.
      throw Error("Il video è cambiato durante l'analisi.");
    }
    if(response.base_revision!==current().project_revision)
      throw Error("Il montaggio è cambiato. Ricalcola gli effetti.");
    proposal=response;
    proposalForMediaId=requestedMediaId;
    const missing=response.missing_signals?.includes("asr_phrases")?
      " Senza frasi ASR sono disponibili solo i cambi su tagli reali.":"";
    status(response.candidates.length+" effetti proposti · nessuno è stato applicato."+missing);
    draw();
  }
  function createId(){
    if(crypto.randomUUID)return crypto.randomUUID().replaceAll("-","");
    const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);
    return [...bytes].map(b=>b.toString(16).padStart(2,"0")).join("");
  }
  async function addAtPlayhead(){
    if(!current().plan)throw Error("Prepara prima il montaggio.");
    const at=mode==="rendered"?
      sourceFromOutput(Math.round(v.currentTime*1000)):
      Math.round(v.currentTime*1000);
    const seg=segments().find(s=>s.start_ms<=at&&at<s.end_ms)||
      segments().find(s=>s.start_ms>at)||segments().at(-1);
    if(!seg||seg.end_ms-seg.start_ms<250)
      throw Error("Serve un segmento mantenuto di almeno 250 ms.");
    const start=Math.min(Math.max(at,seg.start_ms),seg.end_ms-250);
    const end=Math.min(seg.end_ms,start+1150);
    const kind=e("visual-fx-kind").value;
    const zoom=Math.round(Number(e("visual-fx-scale").value));
    const effect={
      id:createId(),segment_id:seg.id,start_ms:start,end_ms:end,kind,
      start_scale_pct:kind==="punch"?zoom:100,end_scale_pct:zoom,
      anchor_x_pct:50,anchor_y_pct:48
    };
    await edit("video.transform.add",{effect});
    selectedFxId=effect.id;draw();
  }
  e("visual-fx-suggest").addEventListener("click",()=>run(suggest));
  e("visual-fx-preset").addEventListener("change",()=>{
    proposal=null;proposalStatus="Scegli «Suggerisci effetti» per ricalcolare.";
    ignoredContext="";draw();
  });
  e("visual-fx-add").addEventListener("click",()=>run(addAtPlayhead));
  e("visual-fx-preview").addEventListener("click",()=>run(()=>startJob("preview")));
  e("visual-fx-scale").addEventListener("input",()=>{
    e("visual-fx-scale-output").textContent=
      (Number(e("visual-fx-scale").value)/100).toFixed(2).replace(".",",")+"×";
  });
  window.pausioVideoFx = {update:draw};
  if(project)draw();
})();
