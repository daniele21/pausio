"use strict";
/* Video B-roll: source assets are local, positions are on the edited output. */
(() => {
  const el = id => document.getElementById(id);
  const videos = () => project?.video_broll || [];
  const fmt = ms => msFormat(ms, true);
  let selected = null, importing = false;

  function sourcePieces(item) {
    const parts = [];
    let offset = 0;
    for (const seg of segments()) {
      const length = seg.end_ms - seg.start_ms;
      const a = Math.max(offset, item.start_ms);
      const b = Math.min(offset + length, item.start_ms + item.duration_ms);
      if (b > a) parts.push({start: seg.start_ms + a - offset,
                              end: seg.start_ms + b - offset});
      offset += length;
    }
    return parts;
  }

  function goTo(item) {
    selected = item.id;
    setWorkspace("broll");
    const at = mode === "rendered" ? item.start_ms : sourceFromOutput(item.start_ms);
    v.pause();
    v.currentTime = Math.max(0, at) / 1000;
    timelineLocate(sourceFromOutput(item.start_ms));
    draw();
    el("video-broll-list").querySelector('[data-roll-id="' + item.id + '"]')
      ?.scrollIntoView({block: "nearest"});
  }

  async function watch(item) {
    if (!item.available) throw Error("Video mancante: reimporta l'asset.");
    const total = editedDuration();
    const duration = Math.min(total, 5000);
    if (duration < 250) throw Error("Montaggio troppo corto.");
    const start = Math.max(0, Math.min(total - duration, item.start_ms - 400));
    update(await post("/api/jobs", {
      kind: "preview_range", range_start_ms: start,
      range_duration_ms: duration
    }));
  }

  function action(label, callback, cls="button button-outline") {
    const b=document.createElement("button");
    b.type="button";b.textContent=label;b.className=cls;
    b.disabled=working()||importing;
    b.addEventListener("click",()=>run(callback));
    return b;
  }

  function fields(item) {
    const details=document.createElement("details");
    details.className="pip-advanced";
    details.open=selected===item.id;
    const summary=document.createElement("summary");
    summary.textContent="Posizione, taglio e layout";
    details.append(summary);
    const grid=document.createElement("div");grid.className="visual-fx-edit-grid";
    const modeLabel=document.createElement("label");
    modeLabel.textContent="Modalità";
    const selector=document.createElement("select");
    for(const [val,name] of [["fullscreen","Schermo intero"],["pip","Picture-in-picture"]]) {
      const opt=document.createElement("option");opt.value=val;opt.textContent=name;
      selector.append(opt);
    }
    selector.value=item.mode;modeLabel.append(selector);grid.append(modeLabel);
    const nums={};
    for(const [label,key,min,max,unit] of [
      ["Inizio montaggio (s)","start_ms",0,172800,1000],
      ["Durata (s)","duration_ms",0.4,20,1000],
      ["Inizio nella clip (s)","media_in_ms",0,172800,1000],
      ["Larghezza PIP (%)","width_pct",20,80,1],
      ["Posizione X (%)","x_pct",0,100,1],
      ["Posizione Y (%)","y_pct",0,100,1]
    ]) {
      const wrapper=document.createElement("label");wrapper.textContent=label;
      const input=document.createElement("input");input.type="number";
      input.min=String(min);input.max=String(max);input.step=unit===1000?"0.1":"1";
      input.value=String(item[key]/unit);input.setAttribute("aria-label",label);
      wrapper.append(input);grid.append(wrapper);nums[key]={input,unit};
    }
    details.append(grid,action("Salva modifiche",async()=>{
      const {available,...record}=item;record.mode=selector.value;
      for(const [key,{input,unit}] of Object.entries(nums)){
        if(!input.checkValidity()||!Number.isFinite(Number(input.value)))
          throw Error("Valore non valido: "+key);
        record[key]=Math.round(Number(input.value)*unit);
      }
      selected=item.id;
      await edit("video.broll.update",{video:record});
    },"button button-primary button-full"));
    return details;
  }

  function card(item) {
    const box=document.createElement("section");
    box.className="visual-fx-entry pip-card";
    box.dataset.rollId=item.id;
    const title=document.createElement("strong");title.className="pip-name";
    title.textContent=item.filename;
    const where=document.createElement("p");where.className="pip-interval";
    where.textContent=fmt(item.start_ms)+" – "+fmt(item.start_ms+item.duration_ms)+
      " · "+(item.mode==="pip"?"PIP":"Schermo intero");
    const info=document.createElement("p");
    info.textContent=item.available?
      "La voce originale continua; l'audio del B-roll è disattivato.":
      "Asset mancante: reimporta il file originale.";
    const buttons=document.createElement("div");
    buttons.className="visual-fx-entry-actions";
    buttons.append(
      action("Vai al punto",()=>goTo(item)),
      action("▶ Guarda 5 s",()=>watch(item),"button button-primary")
    );
    box.append(title,where,info,buttons,fields(item),
      action("Rimuovi clip",()=>edit("video.broll.remove",{video_id:item.id}),
        "button button-ghost"));
    return box;
  }

  function drawLane() {
    const lane=el("broll-lane");
    lane.querySelectorAll(".broll-video-mark").forEach(n=>n.remove());
    if(!project?.media||!project?.plan)return;
    const duration=project.media.duration_ms;
    for(const item of videos()){
      for(const segment of sourcePieces(item)){
        const mark=action("▶ "+item.filename,()=>goTo(item),"broll-mark broll-video-mark");
        mark.style.left=(segment.start/duration*100).toFixed(4)+"%";
        mark.style.width=((segment.end-segment.start)/duration*100).toFixed(4)+"%";
        mark.title="Video B-roll: "+item.filename;
        mark.setAttribute("aria-label",mark.title);
        mark.addEventListener("click",event=>event.stopPropagation());
        lane.append(mark);
      }
    }
  }

  function draw() {
    const ready=!!project?.plan&&!working()&&!importing;
    el("video-broll-import").disabled=!ready||videos().length>=6;
    el("video-broll-status").textContent=!project?.plan?
      "Prepara i tagli per aggiungere clip.":
      videos().length+"/6 clip · MP4, MOV, MKV, WebM fino a 256 MB.";
    const list=el("video-broll-list");list.replaceChildren();
    if(!videos().length){
      const p=document.createElement("p");p.className="pip-empty";
      p.textContent="Nessuna clip video. Importa un B-roll nel punto desiderato.";
      list.append(p);
    }
    for(const item of videos())list.append(card(item));
    drawLane();
  }

  async function importVideo(file){
    if(!file)return;
    if(!project?.plan)throw Error("Prepara prima il montaggio.");
    if(!file.size||file.size>256*1024*1024)throw Error("Massimo 256 MB.");
    const suffix=(file.name.split(".").pop()||"").toLowerCase();
    if(!["mp4","mov","mkv","webm"].includes(suffix))
      throw Error("Scegli un video MP4/MOV/MKV/WebM.");
    const previous=new Set(videos().map(x=>x.id));
    const time=Math.round((v.currentTime||0)*1000);
    const at=mode==="rendered"?time:outputTime(time);
    const start=Math.max(0,Math.min(editedDuration()-1,at));
    importing=true;draw();
    try{
      const response=await fetch("/api/video-broll/import",{
        method:"POST",cache:"no-store",body:file,
        headers:{"Content-Type":"application/octet-stream","X-Pausio-Client":"studio",
          "X-Filename":encodeURIComponent(file.name),
          "X-Pausio-Revision":String(project.project_revision),
          "X-Pausio-Start-Ms":String(start)}
      });
      let data;try{data=await response.json();}catch{throw Error("Risposta non valida.");}
      if(!response.ok)throw Error(data.error||"Import B-roll fallito.");
      selected=data.video_broll?.find(x=>!previous.has(x.id))?.id||selected;
      update(data);toast("Video B-roll importato. Controlla il montaggio con l'anteprima.");
    }finally{importing=false;draw();el("video-broll-input").value="";}
  }

  el("video-broll-import").addEventListener("click",()=>el("video-broll-input").click());
  el("video-broll-input").addEventListener("change",()=>run(
    ()=>importVideo(el("video-broll-input").files?.[0])
  ));
  window.pausioVideos={update:draw};
  if(project)draw();
})();
