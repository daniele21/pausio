"use strict";
/* Pausio Studio: native browser UI, local APIs only, no telemetry or CDN. */
const el = id => document.getElementById(id);
const v = el("preview-video");
let project = null, mediaKey = null, mode = "original", uploading = false;
let lastJobNotice = "", toastTimeout = 0, dragLevel = 0;
let didNotifyRecovery = false;
const msFormat = (value, exact=false) => {
  const x = Math.max(0, Math.floor(Number(value) || 0));
  const base = String(Math.floor(x/60000)).padStart(2,"0") + ":" +
    String(Math.floor(x%60000/1000)).padStart(2,"0");
  return exact ? base+"."+String(Math.floor(x%1000/100)) : base;
};
const shortDuration = ms => ms>=60000 ? msFormat(ms,true) :
  (Math.round(ms/100)/10).toLocaleString("it-IT")+" s";
const segments = () => project?.editor_segments || [];
const editedDuration = () => segments().reduce((sum,s) => sum+s.end_ms-s.start_ms,0);
const outputTime = ms => {
  let elapsed=0;
  for(const s of segments()){if(ms<s.start_ms) break; elapsed+=Math.max(0,Math.min(ms,s.end_ms)-s.start_ms);}
  return elapsed;
};
const working = () => uploading || !!project?.importing || project?.job?.status==="running";
function toast(message,kind="success"){
  const n=el("toast");n.textContent=message;n.className="toast"+(kind==="error"?" error":"");n.hidden=false;
  clearTimeout(toastTimeout);toastTimeout=setTimeout(()=>n.hidden=true,6000);
}
async function post(path,data){
  const res=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json","X-Pausio-Client":"studio"},
    body:JSON.stringify(data),cache:"no-store"});
  let result;try{result=await res.json();}catch{throw Error("Risposta non valida dal server locale.");}
  if(!res.ok)throw Error(result.error||"Operazione non riuscita.");return result;
}
async function refresh(){
  const res=await fetch("/api/state",{cache:"no-store"});
  if(!res.ok)throw Error("Il server locale non risponde.");
  update(await res.json());
}
function busyLabel(kind){
  return ({analyze:"Analisi delle pause in corso…",render:"Creazione MP4 in corso…",
    transcribe:"ClosedRoom sta trascrivendo sul tuo Mac…"})[kind]||"Elaborazione…";
}
function update(next){
  project=next;
  const has=!!next.file, plan=!!next.plan, approved=!!next.approved, ready=!!next.export_ready, busy=working();
  if(next.media_id && mediaKey!==next.media_id){
    mediaKey=next.media_id;mode="original";v.pause();v.src="/api/media?v="+encodeURIComponent(mediaKey);v.load();tab("cuts");
  }
  el("empty-state").hidden=has;el("video-workspace").hidden=!has;
  el("stage-title").textContent=has?"Anteprima del tuo video":"Il tuo spazio creativo";
  el("stage-status").textContent=busy?"Elaborazione in corso":ready?"Pronto da scaricare":
    approved?"Montaggio confermato":plan?"In revisione":has?"Video importato":"Pronto a iniziare";
  el("stage-orb").style.background=busy?"var(--accent)":ready?"var(--keep)":"var(--faint)";
  el("project-status").textContent=ready?"ESPORTATO":approved?"CONFERMATO":plan?"DA RIVEDERE":has?"IMPORTATO":"IN ATTESA";
  el("project-title").textContent=next.file||"Nessun video caricato";
  el("project-meta").textContent=has?msFormat(next.media.duration_ms)+" · "+next.media.width+" × "+
    next.media.height+" · "+(next.media.has_audio?"Audio presente":"Senza audio"):"Scegli un file per iniziare.";
  el("project-revision").textContent = has
    ? "Progetto · "+String(next.history_cursor ?? next.command_count)+" / "+
      String(next.command_count || 0)+" istruzioni applicate"
    : "Progetto non ancora inizializzato";
  el("autosave-indicator").textContent = next.autosaved
    ? has ? "✓ Salvato sul Mac · recuperabile dopo il riavvio" :
      "Autosalvataggio locale attivo"
    : "Sessione temporanea: esporta il progetto per conservarlo";
  el("undo-action").disabled = !has || !next.can_undo || busy;
  el("redo-action").disabled = !has || !next.can_redo || busy;
  el("clear-session").disabled = !has || busy;
  el("project-export").hidden=!has;
  el("project-import").disabled=!has||busy;
  el("import-label").textContent=has?"Cambia video":"Importa video";
  for(const id of ["import-action","empty-import"])el(id).disabled=busy;
  el("analyze-action").disabled=!has||busy;
  el("transcribe-action").disabled=!has||!next.media.has_audio||busy;
  for(const id of ["back-five","forward-five","play-pause"])el(id).disabled=!has;
  el("segment-count").textContent=plan?String(next.plan.segments.length).padStart(2,"0"):"—";
  el("inspector-empty").hidden=plan;el("cuts-content").hidden=!plan;
  el("approve-action").disabled=!plan||approved||busy;
  el("approve-action").textContent=approved?"✓ Montaggio confermato":"✓ Conferma montaggio";
  el("restore-suggested").disabled=!next.suggested_plan||busy;
  el("restore-all").disabled=!plan||busy;el("add-segment").disabled=!plan||busy;
  el("export-action").disabled=!approved||busy||ready;
  el("export-action").hidden=ready;el("download-action").hidden=!ready;
  el("transcript-empty").hidden=!!next.transcript;
  el("transcript-content").hidden=!next.transcript;
  el("timeline-subtitle").textContent=!has?"Nessun video importato":!plan?"Originale • da analizzare":
    next.plan.segments.length+" intervalli mantenuti";
  el("timeline-caption").textContent=ready?"Video finale generato, pronto da scaricare.":
    approved?"Montaggio confermato. Puoi esportare il MP4.":
    plan?"Anteprima dei tagli: controlla e poi conferma il montaggio.":
    "Originale protetto. Nessuna modifica viene applicata automaticamente.";
  el("timeline-placeholder").hidden=has;el("timeline-track").hidden=!has;
  const duration=has?next.media.duration_ms:0;
  for(const [id,frac] of [["tick-quarter",.25],["tick-half",.5],["tick-threequarter",.75],["tick-end",1]]){
    el(id).textContent=has?msFormat(duration*frac):"—";
  }
  for(const step of document.querySelectorAll(".step")){
    const type=step.dataset.step;
    const done=type==="import"?has:type==="analyze"?!!next.suggested_plan:
      type==="review"?approved:ready;
    const active=!done&&(type==="import"?!has:type==="analyze"?has&&!next.suggested_plan:
      type==="review"?plan&&!approved:approved&&!ready);
    step.classList.toggle("complete",done);step.classList.toggle("active",active);
  }
  if(plan){
    el("saved-time").textContent=shortDuration(Math.max(0,duration-editedDuration()));
    el("keep-time").textContent=shortDuration(editedDuration());
  }
  drawSegments();drawTimeline();drawTranscript();transport();
  for(const button of document.querySelectorAll("[data-mode]")){
    button.disabled=!has||(button.dataset.mode==="edited"&&!plan);
    button.classList.toggle("active",button.dataset.mode===mode);
    button.setAttribute("aria-pressed",String(button.dataset.mode===mode));
  }
  el("canvas-badge").textContent=mode==="edited"?"MONTAGGIO • ANTEPRIMA":"ORIGINALE";
  el("job-banner").hidden=!busy;
  if(busy&&!uploading)el("job-message").textContent=busyLabel(next.job.kind);
  if(!didNotifyRecovery && next.recovery_warning){
    didNotifyRecovery = true;
    toast(next.recovery_warning,"error");
  } else if(!didNotifyRecovery && next.recovered){
    didNotifyRecovery = true;
    toast("Sessione recuperata automaticamente. Puoi continuare a modificare.");
  }
  if(["failed","completed"].includes(next.job?.status)){
    const signature=[next.media_id,next.job.kind,next.job.status,next.job.error].join("|");
    if(signature!==lastJobNotice){
      lastJobNotice=signature;
      if(next.job.status==="failed")toast(next.job.error||"Elaborazione fallita.","error");
      else{
        toast(({analyze:"Analisi completata. Rivedi i tagli.",render:"MP4 pronto da scaricare.",
          transcribe:"Trascrizione disponibile nel pannello Testo."})[next.job.kind]||"Operazione completata.");
        if(next.job.kind==="transcribe")tab("transcript");
      }
    }
  }
}
function drawSegments(){
  const list=el("segment-list");list.replaceChildren();
  for(const [index,s] of segments().entries()){
    const card=document.createElement("article");card.className="segment-card";card.dataset.index=index;
    card.innerHTML='<div class="segment-top"><span class="segment-title"><span class="segment-index">'+
      String(index+1).padStart(2,"0")+'</span>Mantieni</span><span class="segment-duration">'+
      shortDuration(s.end_ms-s.start_ms)+'</span></div>'+
      '<div class="segment-fields"><label>Da (secondi)<input class="start-input" type="number" min="0" step=".01"></label>'+
      '<label>A (secondi)<input class="end-input" type="number" min="0" step=".01"></label></div>'+
      '<div class="segment-card-actions"><button type="button" class="segment-action listen">▶ Ascolta da qui</button>'+
      '<button type="button" class="segment-action remove">Escludi</button></div>';
    const from=card.querySelector(".start-input"),to=card.querySelector(".end-input");
    from.value=(s.start_ms/1000).toFixed(2);to.value=(s.end_ms/1000).toFixed(2);
    from.disabled=working();to.disabled=working();card.querySelector(".remove").disabled=working()||segments().length<=1;
    async function save(){
      await edit("segment.update", {
        segment_id:s.id,
        start_ms:Math.round(Number(from.value)*1000),
        end_ms:Math.round(Number(to.value)*1000)
      });
    }
    from.addEventListener("change",()=>run(save));to.addEventListener("change",()=>run(save));
    card.querySelector(".remove").addEventListener("click",()=>run(()=>
      edit("segment.remove", {segment_id:s.id})));
    card.querySelector(".listen").addEventListener("click",()=>{
      v.currentTime=s.start_ms/1000;v.play().catch(()=>{});highlight(index);
    });
    list.append(card);
  }
}
function highlight(index){
  for(const c of document.querySelectorAll(".segment-card"))
    c.classList.toggle("selected",Number(c.dataset.index)===index);
}
function drawTranscript(){
  const list=el("transcript-list");list.replaceChildren();
  const tr=project?.transcript;if(!tr)return;
  el("transcript-model").textContent=tr.model||tr.backend||"";
  el("transcript-note").textContent=tr.word_timestamps_available?
    "Allineamento delle parole disponibile. Il testo non modifica automaticamente i tagli.":
    "Timestamp delle singole parole non disponibili. Mostro gli intervalli riconosciuti.";
  for(const s of tr.segments||[]){
    const item=document.createElement("article");item.className="transcript-item";
    const time=document.createElement("span");time.textContent=msFormat(s.start_ms,true)+" — "+msFormat(s.end_ms,true);
    const content=document.createElement("p");content.textContent=s.text||"(senza testo)";
    const seek=document.createElement("button");seek.type="button";seek.textContent="▶ Ascolta";
    seek.addEventListener("click",()=>{mode="original";update(project);v.currentTime=s.start_ms/1000;v.play().catch(()=>{});});
    item.append(time,content,seek);list.append(item);
  }
  if(!(tr.segments||[]).length){
    const text=document.createElement("p");text.className="transcript-note";
    text.textContent=tr.text||"Non è stato rilevato parlato.";list.append(text);
  }
}
function drawTimeline(){
  const parts=el("timeline-regions");parts.replaceChildren();if(!project?.media)return;
  const duration=project.media.duration_ms,keep=segments();
  parts.classList.toggle("unanalysed", !project.plan);
  if(!project.plan) return;
  for(const s of keep){
    const div=document.createElement("div");div.className="timeline-region";
    div.style.left=(s.start_ms/duration*100).toFixed(4)+"%";
    div.style.width=((s.end_ms-s.start_ms)/duration*100).toFixed(4)+"%";
    div.title="Mantieni "+msFormat(s.start_ms,true)+" – "+msFormat(s.end_ms,true);
    parts.append(div);
  }
}
function transport(){
  const duration=project?.media?.duration_ms||0;
  const at=Math.max(0,Math.min(duration,(v.currentTime||0)*1000));
  const edited=mode==="edited"&&!!project?.plan;
  el("current-time").textContent=msFormat(edited?outputTime(at):at,true);
  el("total-time").textContent=msFormat(edited?editedDuration():duration,true);
  el("playhead").style.left=(duration?at/duration*100:0)+"%";
  el("timeline-track").setAttribute("aria-valuenow",String(Math.round(duration?at/duration*100:0)));
  el("timeline-track").setAttribute("aria-valuetext",msFormat(at,true));
  el("play-pause").textContent=v.paused?"▶":"Ⅱ";
  el("play-pause").setAttribute("aria-label",v.paused?"Riproduci":"Pausa");
  el("video-workspace").classList.toggle("playing",!v.paused);
}
function tab(name){
  for(const key of ["cuts","transcript"]){
    el(key+"-panel").hidden=key!==name;
    el(key+"-tab").classList.toggle("active",key===name);
    el(key+"-tab").setAttribute("aria-selected",String(key===name));
  }
}
async function run(fn){
  try{await fn();}catch(error){toast(error.message||"Operazione non riuscita.","error");refresh().catch(()=>{});}
}
async function edit(type, payload={}){
  if(!project?.file)throw Error("Importa prima un video.");
  update(await post("/api/command", {
    revision:project.project_revision, type, payload
  }));
  toast(type==="timeline.approve"
    ? "Montaggio confermato. Puoi esportare."
    : "Modifica registrata nelle istruzioni del progetto.");
}
async function startJob(kind){
  update(await post("/api/jobs",{kind}));
  el("job-banner").hidden=false;el("job-message").textContent=busyLabel(kind);
}
async function approve(){
  await edit("timeline.approve");
}
async function moveHistory(kind){
  await edit(kind);
}
async function clearSession(){
  if(!project?.file)return;
  if(!window.confirm(
    "Eliminare il progetto attivo e la copia locale del video? "+
    "Gli autosalvataggi verranno cancellati. "+
    "Salva prima un file .pausio.json se vuoi conservarne le istruzioni."
  ))return;
  update(await post("/api/session/clear", {}));
  mediaKey=null;
  mode="original";
  v.pause();v.removeAttribute("src");v.load();
  toast("Sessione e video locali eliminati.");
}
function changeMode(chosen){
  if(chosen==="edited"&&!project?.plan)return;
  v.pause();mode=chosen;
  if(mode==="edited"){
    v.currentTime=segments()[0].start_ms/1000;
    toast("Questa anteprima simula i tagli. Controlla anche il MP4 finale.");
  }
  update(project);
}
function followEdits(){
  if(mode!=="edited"||!project?.plan||v.paused)return;
  const at=Math.floor(v.currentTime*1000),all=segments();
  const selected=all.findIndex(s=>at>=s.start_ms-30&&at<s.end_ms-50);
  if(selected>=0){highlight(selected);return;}
  const next=all.find(s=>s.start_ms>at);
  if(next)v.currentTime=next.start_ms/1000;
  else{v.pause();v.currentTime=all[all.length-1].end_ms/1000;}
}
function play(){
  if(!project?.media)return;
  if(!v.paused){v.pause();return;}
  if(mode==="edited"&&segments().length){
    const at=v.currentTime*1000;
    if(!segments().some(s=>at>=s.start_ms&&at<s.end_ms-50))
      v.currentTime=segments()[0].start_ms/1000;
  }else if(v.ended)v.currentTime=0;
  v.play().catch(()=>toast("Codec non riproducibile. Usa un MP4 H.264 per la preview.","error"));
}
function jump(seconds){
  if(!project?.media)return;
  v.currentTime=Math.max(0,Math.min(project.media.duration_ms/1000,(v.currentTime||0)+seconds));
}
function biggestGap(){
  let max=null,cursor=0;
  for(const s of [...segments(),{start_ms:project.media.duration_ms,end_ms:project.media.duration_ms}]){
    const gap={start_ms:cursor,end_ms:s.start_ms};
    if(gap.end_ms-gap.start_ms>=350&&(!max||gap.end_ms-gap.start_ms>max.end_ms-max.start_ms))max=gap;
    cursor=s.end_ms;
  }return max;
}
function importVideo(file){
  if(!file)return;
  if(working())return toast("Completa prima l'operazione in corso.","error");
  const ext=(file.name.split(".").pop()||"").toLowerCase();
  if(!["mp4","mov","m4v","mkv","webm"].includes(ext))return toast("Formato non supportato.","error");
  if(!file.size||file.size>2*1024*1024*1024)return toast("Video vuoto oppure oltre 2 GB.","error");
  uploading=true;el("job-banner").hidden=false;el("job-message").textContent="Importazione · 0%";
  const xhr=new XMLHttpRequest();xhr.open("POST","/api/import");
  xhr.setRequestHeader("Content-Type","application/octet-stream");
  xhr.setRequestHeader("X-Pausio-Client","studio");
  xhr.setRequestHeader("X-Filename",encodeURIComponent(file.name));
  xhr.upload.addEventListener("progress",event=>{
    if(event.lengthComputable)el("job-message").textContent="Importazione · "+Math.round(event.loaded/event.total*100)+"%";
  });
  xhr.addEventListener("load",()=>{
    uploading=false;el("file-input").value="";
    let result={};try{result=JSON.parse(xhr.responseText);}catch{}
    if(xhr.status===200){update(result);toast("Video importato. Analizza le pause per iniziare.");}
    else{el("job-banner").hidden=true;toast(result.error||"Importazione fallita.","error");}
  });
  xhr.addEventListener("error",()=>{uploading=false;el("job-banner").hidden=true;
    toast("Il server locale ha interrotto la connessione.","error");});
  xhr.send(file);
}
for(const id of ["import-action","empty-import"])el(id).addEventListener("click",()=>el("file-input").click());
el("project-import").addEventListener("click",()=>el("project-input").click());
el("project-input").addEventListener("change",()=>run(async()=>{
  const file=el("project-input").files?.[0];
  if(!file)return;
  if(file.size>256*1024)throw Error("File progetto troppo grande (massimo 256 KB).");
  let payload;
  try{payload=JSON.parse(await file.text());}
  catch{throw Error("Il file selezionato non è un progetto JSON valido.");}
  el("project-input").value="";
  update(await post("/api/project/import",payload));
  toast("Progetto importato. I tagli sono stati ricostruiti dalle istruzioni.");
}));
el("file-input").addEventListener("change",()=>importVideo(el("file-input").files?.[0]));
const drop=el("drop-target");
drop.addEventListener("dragenter",event=>{
  if(!event.dataTransfer?.types?.includes("Files"))return;event.preventDefault();
  dragLevel++;el("drag-overlay").hidden=false;
});
drop.addEventListener("dragover",event=>{if(event.dataTransfer?.types?.includes("Files"))event.preventDefault();});
drop.addEventListener("dragleave",()=>{dragLevel=Math.max(0,dragLevel-1);if(!dragLevel)el("drag-overlay").hidden=true;});
drop.addEventListener("drop",event=>{event.preventDefault();dragLevel=0;el("drag-overlay").hidden=true;importVideo(event.dataTransfer?.files?.[0]);});
el("analyze-action").addEventListener("click",()=>run(()=>startJob("analyze")));
el("transcribe-action").addEventListener("click",()=>run(()=>startJob("transcribe")));
el("export-action").addEventListener("click",()=>run(()=>startJob("render")));
el("approve-action").addEventListener("click",()=>run(approve));
el("undo-action").addEventListener("click",()=>run(()=>moveHistory("history.undo")));
el("redo-action").addEventListener("click",()=>run(()=>moveHistory("history.redo")));
el("clear-session").addEventListener("click",()=>run(clearSession));
el("cuts-tab").addEventListener("click",()=>tab("cuts"));
el("transcript-tab").addEventListener("click",()=>tab("transcript"));
el("restore-suggested").addEventListener("click",()=>run(()=>edit("timeline.restore_suggestion")));
el("restore-all").addEventListener("click",()=>run(()=>edit("timeline.keep_all")));
el("add-segment").addEventListener("click",()=>run(async()=>{
  const extra=biggestGap();if(!extra)throw Error("Non ci sono parti escluse recuperabili.");
  await edit("segment.insert", {start_ms:extra.start_ms, end_ms:extra.end_ms});
}));
for(const button of document.querySelectorAll("[data-mode]"))
  button.addEventListener("click",()=>changeMode(button.dataset.mode));
el("back-five").addEventListener("click",()=>jump(-5));
el("forward-five").addEventListener("click",()=>jump(5));
el("play-pause").addEventListener("click",play);
el("video-center-play").addEventListener("click",play);
v.addEventListener("click",play);
v.addEventListener("timeupdate",()=>{followEdits();transport();});
for(const name of ["play","pause","seeked","loadedmetadata"])v.addEventListener(name,transport);
v.addEventListener("error",()=>{if(project?.file)toast("Impossibile riprodurre il codec nel browser. Usa MP4 H.264.","error");});
el("timeline-track").addEventListener("click",event=>{
  if(!project?.media)return;const bounds=event.currentTarget.getBoundingClientRect();
  v.currentTime=Math.max(0,Math.min(1,(event.clientX-bounds.left)/bounds.width))*project.media.duration_ms/1000;
});
el("timeline-track").addEventListener("keydown",event=>{
  if(!project?.media)return;
  if(["ArrowLeft","ArrowRight","Home","End"].includes(event.key))event.preventDefault();
  if(event.key==="ArrowLeft")jump(-5);if(event.key==="ArrowRight")jump(5);
  if(event.key==="Home")v.currentTime=0;
  if(event.key==="End")v.currentTime=project.media.duration_ms/1000;
});
document.addEventListener("keydown",event=>{
  const target=event.target;
  if(["INPUT","TEXTAREA","SELECT"].includes(target?.tagName) || target?.isContentEditable)
    return; // Let native fields handle their own undo.
  if((event.metaKey||event.ctrlKey)&&!event.altKey){
    const isRedo=(event.code==="KeyZ"&&event.shiftKey)||
      (event.code==="KeyY"&&!event.shiftKey);
    if((event.code==="KeyZ"&&!event.shiftKey)||isRedo){
      event.preventDefault();
      if(!working())run(()=>moveHistory(isRedo?"history.redo":"history.undo"));
      return;
    }
  }
  if(event.metaKey||event.altKey||event.ctrlKey)return;
  if(["BUTTON","A"].includes(target.tagName)||
    target.getAttribute("role")==="slider")return;
  if(event.code==="Space"){event.preventDefault();play();}
  if(event.code==="ArrowLeft"){event.preventDefault();jump(-5);}
  if(event.code==="ArrowRight"){event.preventDefault();jump(5);}
});
setInterval(()=>{
  if(project?.job?.status==="running"||project?.importing)refresh().catch(()=>{});
},850);
refresh().catch(error=>toast(error.message,"error"));
