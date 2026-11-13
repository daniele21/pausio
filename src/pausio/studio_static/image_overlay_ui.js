"use strict";
/* Image B-roll is output-timed; display source-ruler markers projected over KEEP. */
(() => {
  const el=id=>document.getElementById(id);
  const images=()=>project?.image_overlays||[];
  const time=ms=>msFormat(ms,true);
  let selectedId=null, importing=false;

  function sourcePieces(image, keeps) {
    const parts=[];
    let offset=0;
    for(const segment of keeps) {
      const length=segment.end_ms-segment.start_ms;
      const a=Math.max(offset,image.start_ms);
      const b=Math.min(offset+length,image.start_ms+image.duration_ms);
      if(b>a) parts.push({
        start:segment.start_ms+a-offset,
        end:segment.start_ms+b-offset
      });
      offset+=length;
    }
    return parts;
  }

  function goTo(image, showSettings=false) {
    selectedId=image.id;
    setWorkspace("broll");
    // Only FFmpeg mode uses edited/output time. Other modes use source time.
    const at=mode==="rendered"?image.start_ms:sourceFromOutput(image.start_ms);
    v.pause();v.currentTime=Math.max(0,at)/1000;
    timelineLocate(sourceFromOutput(image.start_ms));
    draw();
    const card=el("pip-image-list").querySelector('[data-pip-id="'+image.id+'"]');
    if(showSettings)card?.querySelector("details")?.setAttribute("open","");
    card?.scrollIntoView({block:"nearest"});
  }

  async function watch(image) {
    if(!image.available)throw Error("Immagine mancante: reimporta il file originale.");
    if(!project?.plan)throw Error("Prepara prima il montaggio.");
    const total=editedDuration(),length=Math.min(total,5000);
    if(length<250)throw Error("Il montaggio è troppo corto.");
    const start=Math.max(0,Math.min(total-length,image.start_ms-400));
    update(await post("/api/jobs",{
      kind:"preview_range",range_start_ms:start,range_duration_ms:length
    }));
    // The existing job polling opens the true FFmpeg clip after completion.
  }

  function editFields(image) {
    const box=document.createElement("details");box.className="pip-advanced";
    box.open=selectedId===image.id;
    const summary=document.createElement("summary");
    summary.textContent="Regola tempi, dimensione e posizione";box.append(summary);
    const grid=document.createElement("div");grid.className="visual-fx-edit-grid";
    const fields={};
    const definitions=[
      ["Inizio nel montaggio (s)","start_ms",0,172800,1000],
      ["Durata (s)","duration_ms",0.4,12,1000],
      ["Larghezza (%)","width_pct",20,70,1],
      ["Orizzontale (%)","x_pct",0,100,1],
      ["Verticale (%)","y_pct",0,100,1]
    ];
    for(const [label,key,min,max,unit] of definitions) {
      const wrapper=document.createElement("label");
      wrapper.textContent=label;
      const input=document.createElement("input");
      input.type="number";input.min=String(min);input.max=String(max);
      input.step=unit===1000?"0.1":"1";
      input.value=String(image[key]/unit);
      input.setAttribute("aria-label",label+" immagine PIP");
      wrapper.append(input);grid.append(wrapper);
      fields[key]={input,unit};
    }
    const save=document.createElement("button");
    save.type="button";save.className="button button-primary button-full";
    save.textContent="Salva modifiche";
    save.disabled=working()||importing;
    save.addEventListener("click",()=>run(async()=>{
      const {available,...updated}=image;
      for(const [key,{input,unit}] of Object.entries(fields)) {
        if(!input.checkValidity()||!Number.isFinite(Number(input.value)))
          throw Error("Valore non valido: "+key);
        updated[key]=Math.round(Number(input.value)*unit);
      }
      selectedId=image.id;
      await edit("image.overlay.update",{image:updated});
    }));
    box.append(grid,save);
    box.addEventListener("toggle",()=>{if(box.open)selectedId=image.id;});
    return box;
  }

  function button(label,action,cls="button button-outline") {
    const b=document.createElement("button");b.type="button";
    b.className=cls;b.textContent=label;b.disabled=working()||importing;
    b.addEventListener("click",()=>run(action));
    return b;
  }

  function cardFor(image) {
    const card=document.createElement("section");
    card.className="visual-fx-entry pip-card"+(selectedId===image.id?" is-selected":"");
    card.dataset.pipId=image.id;
    const name=document.createElement("strong");name.className="pip-name";
    name.textContent=image.filename;
    const interval=document.createElement("p");interval.className="pip-interval";
    interval.textContent="Nel video finale: "+time(image.start_ms)+" – "+
      time(image.start_ms+image.duration_ms);
    const note=document.createElement("p");
    note.textContent=image.available?
      "L'immagine appare sopra il parlato. Controlla il risultato con FFmpeg.":
      "File locale mancante: reimporta l'originale per renderizzarlo.";
    const actions=document.createElement("div");
    actions.className="visual-fx-entry-actions";
    actions.append(
      button("Vai al punto",()=>goTo(image)),
      button("▶ Guarda 5 s",()=>watch(image),"button button-primary")
    );
    const remove=button("Rimuovi immagine",()=>edit(
      "image.overlay.remove",{image_id:image.id}),"button button-ghost");
    card.append(name,interval,note,actions,editFields(image),remove);
    return card;
  }

  function drawLane() {
    const surface=el("timeline-surface"),track=el("timeline-broll-track");
    const lane=el("broll-lane");lane.replaceChildren();
    const visible=!!project?.plan&&!!project?.media&&
      (images().length>0||el("app").dataset.workspace==="broll");
    track.hidden=!visible;surface.classList.toggle("has-broll",visible);
    el("broll-lane-empty").hidden=images().length>0;
    if(!visible)return;
    const duration=project.media.duration_ms;
    for(const image of images()) {
      for(const piece of sourcePieces(image,segments())) {
        const mark=button("▧ "+image.filename,()=>goTo(image,true),"broll-mark");
        mark.dataset.pipId=image.id;
        mark.style.left=(piece.start/duration*100).toFixed(4)+"%";
        mark.style.width=((piece.end-piece.start)/duration*100).toFixed(4)+"%";
        mark.setAttribute("aria-label","B-roll "+image.filename+
          " nel video finale da "+time(image.start_ms)+" a "+
          time(image.start_ms+image.duration_ms)+". Vai al punto.");
        mark.title=mark.getAttribute("aria-label");
        mark.classList.toggle("is-selected",selectedId===image.id);
        mark.addEventListener("click",event=>event.stopPropagation());
        lane.append(mark);
      }
    }
  }

  function cursorHint() {
    const note=el("pip-image-playhead-note");
    if(!project?.plan){note.textContent="";return;}
    const t=Math.max(0,Math.round((v.currentTime||0)*1000));
    const output=mode==="rendered"?t:outputTime(t);
    const current=images().find(x=>x.start_ms<=output&&
      output<x.start_ms+x.duration_ms);
    const next=images().filter(x=>x.start_ms>output)
      .sort((a,b)=>a.start_ms-b.start_ms)[0];
    note.textContent="Cursore nel video finale: "+time(output)+". "+
      (current?"Qui è prevista «"+current.filename+"». "+
        (mode==="rendered"?"La vedi nel video.":"Premi «Guarda 5 s» per vederla."):
      next?"Prossima immagine a "+time(next.start_ms)+
        ". Usa «Vai al punto» o «Guarda 5 s».":"Nessuna immagine qui.");
  }

  function draw() {
    const ready=!!project?.plan&&!working()&&!importing;
    el("pip-image-import").disabled=!ready||images().length>=4;
    el("pip-image-status").textContent=!project?.plan?
      "Importa il video e prepara i tagli.":
      images().length+"/4 immagini · Selezionale dalla traccia B-roll.";
    const list=el("pip-image-list");list.replaceChildren();
    if(!images().length) {
      const empty=document.createElement("p");empty.className="pip-empty";
      empty.textContent="Nessuna immagine. Sposta il cursore nel video e premi «Aggiungi immagine al cursore».";
      list.append(empty);
    }
    for(const image of images())list.append(cardFor(image));
    drawLane();cursorHint();
  }

  async function importImage(file) {
    if(!file)return;
    if(!project?.plan)throw Error("Prepara prima il montaggio.");
    if(!file.size||file.size>12*1024*1024)
      throw Error("Scegli PNG/JPG/WebP fino a 12 MB.");
    const extension=(file.name.split(".").pop()||"").toLowerCase();
    if(!["png","jpg","jpeg","webp"].includes(extension))
      throw Error("Scegli un'immagine PNG/JPG/WebP.");
    const previous=new Set(images().map(x=>x.id));
    const at=Math.round((v.currentTime||0)*1000);
    const output=mode==="rendered"?at:outputTime(at);
    const start=Math.max(0,Math.min(editedDuration()-1,output));
    importing=true;draw();
    try {
      const response=await fetch("/api/image/import",{
        method:"POST",cache:"no-store",body:file,
        headers:{
          "Content-Type":"application/octet-stream",
          "X-Pausio-Client":"studio",
          "X-Filename":encodeURIComponent(file.name),
          "X-Pausio-Revision":String(project.project_revision),
          "X-Pausio-Start-Ms":String(start)
        }
      });
      let data;
      try{data=await response.json();}catch{throw Error("Risposta non valida.");}
      if(!response.ok)throw Error(data.error||"Import immagine fallito.");
      selectedId=data.image_overlays?.find(x=>!previous.has(x.id))?.id||selectedId;
      update(data);
      toast("Immagine aggiunta: la trovi nella traccia B-roll. Premi «Guarda 5 s».");
    }finally{
      importing=false;draw();el("pip-image-input").value="";
    }
  }

  el("pip-image-import").addEventListener("click",()=>el("pip-image-input").click());
  el("pip-image-input").addEventListener("change",()=>run(
    ()=>importImage(el("pip-image-input").files?.[0])
  ));
  v.addEventListener("timeupdate",cursorHint);
  v.addEventListener("seeked",cursorHint);
  window.pausioImages={update:draw};
  if(project)draw();
})();
