"use strict";
/* Pausio Studio: native browser UI, local APIs only, no telemetry or CDN. */
const el = id => document.getElementById(id);
const v = el("preview-video");
let project = null, mediaKey = null, mode = "original", uploading = false;
let lastJobNotice = "", toastTimeout = 0, dragLevel = 0;
let didNotifyRecovery = false;
let waveformData = null, waveformRequestedFor = null, timelineZoom = 1, previewSourceMode = "original";
let dragHandleActive = false;
let simulationFrame = null;
let captionDraft = null, captionSource = null, captionMediaKey = null;
let captionPositionMode = false;
let captionPointer = null;
const captionNumberFields = ["x_pct","y_pct","font_size","outline_size"];
const captionColorFields = ["text_color","outline_color","background_color"];
function captionConfig(){ return captionDraft||project?.caption_config||project?.caption_presets?.social; }
function renderCaptionSettings(){
  if(!captionDraft)return;
  el("caption-style").value=captionDraft.preset;
  for(const field of [...captionNumberFields,...captionColorFields]){
    const input=document.querySelector('[data-caption-setting="'+field+'"]');
    if(input)input.value=captionDraft[field];
  }
  document.querySelector('[data-caption-setting="background"]').checked=captionDraft.background;
  for(const [id,name,suffix] of [
    ["caption-x-output","x_pct","%"],["caption-y-output","y_pct","%"],
    ["caption-font-output","font_size",""],["caption-outline-output","outline_size",""]
  ])el(id).textContent=captionDraft[name]+suffix;
}
function syncCaptionSettings(next,busy){
  const config=next.caption_config||next.caption_presets?.social;
  if(!config)return;
  const key=JSON.stringify([next.media_id,config]);
  if(next.media_id!==captionMediaKey){
    captionMediaKey=next.media_id;
    captionPositionMode=false;
  }
  if(key!==captionSource){
    captionSource=key; captionDraft={...config}; renderCaptionSettings();
  }
  const canEdit=(next.captions||[]).length>0;
  if(!canEdit)captionPositionMode=false;
  for(const input of document.querySelectorAll("[data-caption-setting]"))input.disabled=busy||!canEdit;
  el("caption-drag-toggle").disabled=busy||!canEdit;
  el("caption-drag-toggle").setAttribute("aria-pressed",String(captionPositionMode));
  el("caption-drag-toggle").textContent=captionPositionMode?
    "✓ Posizione attiva · trascina sul video":"Sposta sull'anteprima";
}
function previewCaptionSetting(key,value){
  if(!captionDraft)return;
  captionDraft={...captionDraft,preset:"custom",[key]:value};
  renderCaptionSettings();
  updateCaptionOverlay();
}
async function commitCaptionSettings(){
  if(!(project?.captions||[]).length || !captionDraft)return;
  if(JSON.stringify(captionDraft)===JSON.stringify(project.caption_config))return;
  await edit("caption.configure",{config:{...captionDraft}});
}

let cutDraft = null, cutSource = null;
const cutDescriptions = {
  natural: "Preserva il ritmo del parlato. Riduce solo pause sufficientemente lunghe.",
  balanced: "Accorcia più pause per un ritmo social equilibrato.",
  dynamic: "Proposte più frequenti per Reels; riascolta sempre gli stacchi.",
  custom: "Usa le soglie impostate sotto. Modifiche applicate alla prossima analisi."
};
const cutNames = ["noise_db", "min_silence_ms", "min_removed_ms",
  "speech_padding_before_ms", "speech_padding_after_ms", "min_keep_ms"];
function renderCutControls(){
  if(!cutDraft)return;
  el("cut-preset").value=cutDraft.preset;
  for(const name of cutNames)
    document.querySelector('[data-cut-setting="'+name+'"]').value=cutDraft[name];
  el("cut-preset-help").textContent=cutDescriptions[cutDraft.preset]||cutDescriptions.custom;
}
function syncCutControls(next, busy){
  const defaultPreset=next.cut_presets?.natural;
  const effective=next.analysis_settings||(defaultPreset?{preset:"natural",...defaultPreset}:null);
  if(!effective)return;
  const source=JSON.stringify([next.media_id, effective]);
  if(source!==cutSource){
    cutSource=source;
    cutDraft={...effective};
    renderCutControls();
  }
  el("cut-preset").disabled=busy;
  for(const input of document.querySelectorAll("[data-cut-setting]"))input.disabled=busy;
  const detected=next.detected_silences;
  const duration=next.media?.duration_ms||0;
  const retained=(next.plan?.segments||[]).reduce((sum,s)=>sum+s.end_ms-s.start_ms,0);
  const saved=Math.max(0,duration-retained);
  const dirty=!!next.plan&&JSON.stringify(cutDraft)!==JSON.stringify(effective);
  const message=dirty?"Parametri modificati: clicca «Rianalizza le pause» per applicarli.":
    !next.plan?"Scegli un preset, poi avvia l'analisi.":
    detected===0?"Nessuna pausa rilevata: prova Bilanciato o Dinamico.":
    saved===0?"Pause rilevate"+(detected===null?"":": "+detected)+
      ", ma nessuna idonea al taglio. Prova un preset più dinamico.":
    (detected===null?"Analisi precedente":detected+" pause rilevate")+
      " · "+(saved/1000).toFixed(1)+" s esclusi. Rivedi ogni taglio.";
  el("cut-result").textContent=message;
  el("analyze-action").querySelector(".tool-copy strong").textContent=
    next.plan?"Rianalizza le pause":"Analizza le pause";
}
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
// If the playhead is in an excluded interval, continue with the NEXT kept
// interval instead of jumping all the way back to the first segment.
function nextSimulatedSourceTime(at){
  const all=segments();
  for(const s of all){
    if(at<s.start_ms)return s.start_ms;
    if(at<s.end_ms)return at;
  }
  return all.length?all[0].start_ms:0;
}
const sourceFromOutput = ms => {
  let remaining=Math.max(0,ms);
  for(const segment of segments()){
    const length=segment.end_ms-segment.start_ms;
    if(remaining<=length)return segment.start_ms+remaining;
    remaining-=length;
  }
  return segments().length ? segments()[segments().length-1].end_ms : 0;
};
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
  return ({analyze:"Analisi delle pause in corso…",preview:"Rendering anteprima FFmpeg…",render:"Creazione MP4 in corso…",
    transcribe:"Pausio sta trascrivendo localmente con MLX Whisper…"})[kind]||"Elaborazione…";
}
function update(next){
  project=next;
  const has=!!next.file, plan=!!next.plan, approved=!!next.approved, ready=!!next.export_ready, busy=working();
  if(mode==="edited"&&(!plan||(next.media&&editedDuration()>=next.media.duration_ms))){
    mode="original";
    v.pause();
    syncSimulationLoop();
  }
  document.body.classList.toggle("has-media",has);
  syncCutControls(next, busy);
  syncCaptionSettings(next, busy);
  if(next.media_id && mediaKey!==next.media_id){
    mediaKey=next.media_id;mode="original";previewSourceMode="original";
    waveformData=null;waveformRequestedFor=null;
    paintWaveform();
    v.pause();v.src="/api/media?v="+encodeURIComponent(mediaKey);v.load();tab("cuts");
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
  for(const name of ["asr-model","asr-language","asr-download"])el(name).disabled=busy;
  for(const id of ["back-five","forward-five","play-pause"])el(id).disabled=!has;
  el("segment-count").textContent=plan?String(next.plan.segments.length).padStart(2,"0"):"—";
  el("inspector-empty").hidden=plan;el("cuts-content").hidden=!plan;
  el("approve-action").disabled=!plan||approved||busy;
  el("approve-action").textContent=approved?"✓ Montaggio confermato":"✓ Conferma montaggio";
  el("restore-suggested").disabled=!next.suggested_plan||busy;
  el("restore-all").disabled=!plan||busy;el("add-segment").disabled=!plan||busy;
  el("preview-action").disabled=!plan||busy;
  el("preview-action").textContent=next.preview_ready?"Rigenera preview":"Genera preview";
  if(mode==="rendered"&&!next.preview_ready){
    // Editing invalidated the cached FFmpeg preview: return to original safely.
    mode="original";previewSourceMode="original";
    v.pause();v.src="/api/media?v="+encodeURIComponent(mediaKey);v.load();
  }
  el("export-action").disabled=!approved||busy||ready;
  el("export-action").hidden=ready;el("download-action").hidden=!ready;
  const hasCaptions=(next.captions||[]).length>0;
  el("transcript-empty").hidden=!!next.transcript||hasCaptions;
  el("transcript-content").hidden=!next.transcript&&!hasCaptions;
  el("caption-generate").disabled=!next.transcript||busy;
  el("caption-generate").textContent=hasCaptions?"Rigenera da trascrizione":"+ Aggiungi sottotitoli";
  el("caption-style").disabled=busy;
  el("caption-clear").disabled=!hasCaptions||busy;
  el("caption-active").hidden=!hasCaptions;
  el("caption-count").textContent=hasCaptions?
    next.captions.length+" sottotitoli · inclusi nell'MP4":"";
  el("timeline-subtitle").textContent=!has?"Nessun video importato":!plan?"Originale • da analizzare":
    next.plan.segments.length+" intervalli mantenuti";
  el("waveform-state").textContent=!has?"":next.waveform_status==="running"?
    "Waveform in elaborazione…":next.waveform_status==="failed"?
    (next.waveform_error||"Waveform non disponibile"):next.waveform_status==="ready"?
    (next.media.has_audio?"Waveform audio reale":"Video senza audio"):"";
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
  drawSegments();drawTimeline();drawTranscript();drawCaptionEditor();transport();
  if(has&&next.waveform_status==="ready"&&waveformRequestedFor!==next.media_id){
    waveformRequestedFor=next.media_id;
    fetch("/api/waveform",{cache:"no-store"}).then(async response=>{
      if(!response.ok)throw Error("Waveform non disponibile.");
      return response.json();
    }).then(data=>{
      if(data.media_id!==mediaKey)return;
      waveformData=data.values;
      paintWaveform();
    }).catch(()=>{waveformData=null;});
  }
  for(const button of document.querySelectorAll("[data-mode]")){
    button.disabled=!has||(button.dataset.mode==="edited"&&(!plan||
      editedDuration()>=next.media.duration_ms))||
      (button.dataset.mode==="rendered"&&!next.preview_ready);
    if(button.dataset.mode==="edited"){
      button.title=plan&&editedDuration()>=next.media.duration_ms?
        "Nessuna parte esclusa: prova a rianalizzare con un preset più dinamico.":
        "Salta le parti escluse usando il player originale.";
    }
    button.classList.toggle("active",button.dataset.mode===mode);
    button.setAttribute("aria-pressed",String(button.dataset.mode===mode));
  }
  el("canvas-badge").textContent=mode==="edited"?"SIMULAZIONE TAGLI":
    mode==="rendered"?"ANTEPRIMA FFmpeg":"ORIGINALE";
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
        toast(({analyze:"Analisi completata. Rivedi i tagli.",preview:"Anteprima FFmpeg pronta. Ascolta gli stacchi prima di confermare.",render:"MP4 pronto da scaricare.",
          transcribe:"Trascrizione disponibile nel pannello Testo."})[next.job.kind]||"Operazione completata.");
        if(next.job.kind==="transcribe")tab("transcript");
        if(next.job.kind==="preview")changeMode("rendered");
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
  const tr=project?.transcript;
  el("transcript-model").textContent=tr?.model||tr?.backend||"Salvato nel progetto";
  el("transcript-note").textContent=!tr?
    "Sottotitoli recuperati dal progetto. Puoi correggerli e renderizzarli anche senza rilanciare la trascrizione.":
    tr.word_timestamps_available?
    "Allineamento delle parole disponibile. Premi «Aggiungi sottotitoli» per inserirli nel video.":
    "Allineamento delle parole non disponibile: i sottotitoli useranno gli intervalli delle frasi intere.";
  if(!tr)return;
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
function drawCaptionEditor(){
  const list=el("caption-edit-list");list.replaceChildren();
  for(const cue of project?.captions||[]){
    const card=document.createElement("article");card.className="caption-edit-card";
    const heading=document.createElement("div");heading.className="caption-edit-heading";
    heading.textContent=msFormat(cue.start_ms,true)+" — "+msFormat(cue.end_ms,true);
    const input=document.createElement("textarea");
    input.className="caption-edit-input";input.rows=2;input.maxLength=300;
    input.value=cue.text;input.disabled=working();input.setAttribute("aria-label","Testo sottotitolo "+heading.textContent);
    const save=document.createElement("button");save.type="button";
    save.className="text-button";save.textContent="Salva testo";save.disabled=working();
    save.addEventListener("click",()=>run(async()=>{
      if(input.value.trim()===cue.text)return;
      await edit("caption.correct",{caption_id:cue.id,text:input.value.trim()});
    }));
    card.append(heading,input,save);
    list.append(card);
  }
}
function updateCaptionOverlay(){
  const overlay=el("caption-overlay");
  if(!overlay)return;
  const config=captionConfig();
  if(!config)return;
  overlay.classList.toggle("style-minimal",config.preset==="minimal");
  const at=Math.round(v.currentTime*1000);
  const kept=mode!=="edited"||segments().some(s=>at>=s.start_ms&&at<s.end_ms);
  const cues=project?.captions||[];
  let cue=mode==="rendered"||!kept?null:
    cues.find(c=>at>=c.start_ms&&at<c.end_ms);
  if(captionPositionMode&&mode!=="rendered"&&!cue)cue=cues[0]||null;
  overlay.hidden=!cue;
  overlay.classList.toggle("positioning",captionPositionMode&&!!cue&&mode!=="rendered");
  if(captionPositionMode&&cue){
    overlay.tabIndex=0;
    overlay.setAttribute("role","slider");
    overlay.setAttribute("aria-label","Posizione sottotitoli, usa le frecce o trascina");
    overlay.setAttribute("aria-valuetext",
      "Orizzontale "+config.x_pct+"%, verticale "+config.y_pct+"%");
  }else{
    overlay.removeAttribute("tabindex");
    overlay.removeAttribute("role");
    overlay.removeAttribute("aria-valuetext");
  }
  overlay.style.left=config.x_pct+"%";
  overlay.style.top=config.y_pct+"%";
  const videoBox=overlay.parentElement.getBoundingClientRect();
  const scale=Math.max(0.1, videoBox.width/1080);
  overlay.style.fontSize=Math.max(8,config.font_size*scale)+"px";
  overlay.style.color=config.text_color;
  overlay.style.webkitTextStroke=(config.outline_size*scale)+"px "+config.outline_color;
  overlay.style.textShadow="0 1px 2px "+config.outline_color;
  overlay.style.background=config.background?config.background_color+"CC":"transparent";
  const value=cue?.text||"";
  if(overlay.textContent!==value)overlay.textContent=value;
}
function drawTimeline(){
  const parts=el("timeline-regions");parts.replaceChildren();if(!project?.media)return;
  const duration=project.media.duration_ms,keep=segments();
  parts.classList.toggle("unanalysed", !project.plan);
  if(!project.plan) return;
  for(const s of keep){
    const index=keep.indexOf(s),prev=index?keep[index-1]:null,next=keep[index+1]||null;
    const div=document.createElement("div");div.className="timeline-region";
    div.style.left=(s.start_ms/duration*100).toFixed(4)+"%";
    div.style.width=((s.end_ms-s.start_ms)/duration*100).toFixed(4)+"%";
    div.title="Mantieni "+msFormat(s.start_ms,true)+" – "+msFormat(s.end_ms,true);
    for(const side of ["start","end"]){
      const handle=document.createElement("button");
      handle.type="button";handle.className="trim-handle "+side;
      handle.disabled=working();
      handle.setAttribute("aria-label", (side==="start"?"Inizio":"Fine")+
        " intervallo "+(index+1)+", "+msFormat(side==="start"?s.start_ms:s.end_ms,true));
      handle.title="Trascina per regolare il taglio; frecce ±0,1 secondi";
      bindTrimHandle(handle,div,s,side,prev,next,duration);
      div.append(handle);
    }
    parts.append(div);
  }
}

/* All drag/keyboard trim actions send ONE canonical segment.update command. */
function bindTrimHandle(handle,region,segment,side,previous,next,duration){
  const min=side==="start"?(previous?.end_ms||0):segment.start_ms+50;
  const max=side==="start"?segment.end_ms-50:(next?.start_ms||duration);
  const positionFor=value=>Math.max(min,Math.min(max,Math.round(value/10)*10));
  const segmentAt=value=>({
    segment_id:segment.id,
    start_ms:side==="start"?value:segment.start_ms,
    end_ms:side==="end"?value:segment.end_ms
  });
  function paint(value){
    const start=side==="start"?value:segment.start_ms;
    const end=side==="end"?value:segment.end_ms;
    region.style.left=(start/duration*100)+"%";
    region.style.width=((end-start)/duration*100)+"%";
    region.classList.add("drag-preview");
    handle.setAttribute("aria-valuetext",msFormat(value,true));
  }
  function submit(value){
    const previousValue=side==="start"?segment.start_ms:segment.end_ms;
    region.classList.remove("drag-preview");
    if(value===previousValue){drawTimeline();return;}
    run(()=>edit("segment.update",segmentAt(value)));
  }
  handle.addEventListener("click",event=>{event.stopPropagation();});
  handle.addEventListener("keydown",event=>{
    if(!["ArrowLeft","ArrowRight"].includes(event.key)||working())return;
    event.preventDefault();event.stopPropagation();
    const step=event.shiftKey?500:100;
    const initial=side==="start"?segment.start_ms:segment.end_ms;
    submit(positionFor(initial+(event.key==="ArrowRight"?step:-step)));
  });
  handle.addEventListener("pointerdown",event=>{
    if(working()||event.button!==0)return;
    event.stopPropagation();event.preventDefault();
    dragHandleActive=true;
    handle.classList.add("dragging");
    handle.setPointerCapture(event.pointerId);
    let finalValue=side==="start"?segment.start_ms:segment.end_ms;
    const move=ev=>{
      const rect=el("timeline-track").getBoundingClientRect();
      finalValue=positionFor((ev.clientX-rect.left)/rect.width*duration);
      paint(finalValue);
    };
    const finish=ev=>{
      handle.removeEventListener("pointermove",move);
      handle.removeEventListener("pointerup",finish);
      handle.removeEventListener("pointercancel",cancel);
      if(handle.hasPointerCapture(ev.pointerId))handle.releasePointerCapture(ev.pointerId);
      handle.classList.remove("dragging");
      // Defer the seek guard reset to avoid an accidental click after drag.
      window.setTimeout(()=>{dragHandleActive=false;},0);
      submit(finalValue);
    };
    const cancel=ev=>{
      handle.removeEventListener("pointermove",move);
      handle.removeEventListener("pointerup",finish);
      handle.removeEventListener("pointercancel",cancel);
      if(handle.hasPointerCapture(ev.pointerId))handle.releasePointerCapture(ev.pointerId);
      handle.classList.remove("dragging");
      drawTimeline();dragHandleActive=false;
    };
    handle.addEventListener("pointermove",move);
    handle.addEventListener("pointerup",finish);
    handle.addEventListener("pointercancel",cancel);
  });
}
function paintWaveform(){
  const canvas=el("waveform-canvas"),track=el("timeline-track");
  if(!canvas||!track)return;
  const bounds=track.getBoundingClientRect();
  const width=Math.max(1,Math.round(bounds.width));
  const height=Math.max(1,Math.round(bounds.height));
  if(canvas.width!==width||canvas.height!==height){
    canvas.width=width;canvas.height=height;
  }
  const context=canvas.getContext("2d");if(!context)return;
  context.clearRect(0,0,width,height);
  if(!Array.isArray(waveformData)||!waveformData.length)return;
  context.fillStyle="rgba(179,215,237,.83)";
  const count=waveformData.length;
  for(let x=0;x<width;x++){
    const start=Math.floor(x*count/width);
    const end=Math.max(start+1,Math.ceil((x+1)*count/width));
    let peak=0;
    for(let i=start;i<Math.min(count,end);i++)peak=Math.max(peak,waveformData[i]);
    const barHeight=Math.max(1,(peak/1000)*(height-6));
    context.fillRect(x,Math.round((height-barHeight)/2),1,Math.ceil(barHeight));
  }
}

function transport(){
  updateCaptionOverlay();
  const duration=project?.media?.duration_ms||0;
  const at=Math.max(0,Math.min(duration,(v.currentTime||0)*1000));
  const edited=mode==="edited"&&!!project?.plan;
  const rendered=mode==="rendered";
  const sourceAt=rendered?sourceFromOutput(at):at;
  el("current-time").textContent=msFormat(rendered?at:edited?outputTime(at):at,true);
  el("total-time").textContent=msFormat(rendered||edited?editedDuration():duration,true);
  el("playhead").style.left=(duration?sourceAt/duration*100:0)+"%";
  el("timeline-track").setAttribute("aria-label","Timeline originale, posizione "+
    msFormat(sourceAt,true)+". Frecce ±5 secondi. Maniglie per regolare i tagli.");
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
  if(kind==="analyze" && !cutDraft)throw Error("Impostazioni non ancora disponibili.");
  const body=kind==="analyze"?{kind,settings:{...cutDraft}}:{kind};
  if(kind==="transcribe"){
    const allow=el("asr-download").checked;
    if(allow&&!window.confirm(
      "Autorizzi Pausio a scaricare dal sito Hugging Face il modello selezionato, "+
      "solo se non è già presente? Il modello Large Turbo richiede circa 1,6 GB "+
      "di spazio. Il video e l'audio non vengono inviati online."
    ))return;
    body.asr={model:el("asr-model").value,language:el("asr-language").value,
      allow_model_download:allow};
  }
  if(kind==="analyze"){
    for(const input of document.querySelectorAll("[data-cut-setting]")){
      if(!input.checkValidity())throw Error("Controlla i limiti dei parametri avanzati.");
    }
  }
  update(await post("/api/jobs",body));
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
  if(!project?.media||(chosen==="edited"&&
    (!project.plan||editedDuration()>=project.media.duration_ms))||
    chosen==="rendered"&&!project.preview_ready)return;
  const oldMode=mode;
  const oldTime=(v.currentTime||0)*1000;
  const sourceTime=oldMode==="rendered"?sourceFromOutput(oldTime):oldTime;
  const nextTime=chosen==="rendered"?outputTime(sourceTime):
    chosen==="edited"?nextSimulatedSourceTime(sourceTime):sourceTime;
  v.pause();mode=chosen;
  if(chosen==="rendered"||oldMode==="rendered"){
    const url=chosen==="rendered"?"/api/preview?v="+encodeURIComponent(mediaKey)+
      "&rev="+project.project_revision:"/api/media?v="+encodeURIComponent(mediaKey);
    v.src=url;
    v.addEventListener("loadedmetadata",()=>{
      v.currentTime=Math.max(0,Math.min(v.duration||0,nextTime/1000));
      transport();
    },{once:true});
    v.load();
  }else{
    v.currentTime=nextTime/1000;
    if(chosen==="edited"){
      toast("Simulazione tramite salti: usa «Genera preview» per controllare il montaggio FFmpeg.");
    }
  }
  previewSourceMode=chosen;
  syncSimulationLoop();
  update(project);
}
function followEdits(){
  if(mode!=="edited"||!project?.plan||v.paused||v.seeking)return;
  const at=Math.round(v.currentTime*1000),all=segments();
  if(!all.length)return;
  const selected=all.findIndex(s=>at>=s.start_ms-3&&at<s.end_ms);
  if(selected>=0){highlight(selected);return;}
  const next=all.find(s=>s.start_ms>at);
  if(next){
    highlight(all.indexOf(next));
    v.currentTime=next.start_ms/1000;
  }else{
    // The final kept interval has finished. Never play the discarded tail.
    v.pause();
    v.currentTime=all[all.length-1].end_ms/1000;
  }
}
// HTMLMediaElement.timeupdate can fire only ~4 times per second. That misses
// short excluded intervals (especially Dynamic). While actively playing an
// edit simulation, check every animation frame; retain timeupdate as fallback
// when a tab is backgrounded. Do not run the loop in other preview modes.
function simulationTick(){
  simulationFrame=null;
  if(mode!=="edited"||v.paused||v.ended)return;
  followEdits();
  transport();
  if(mode==="edited"&&!v.paused)simulationFrame=requestAnimationFrame(simulationTick);
}
function syncSimulationLoop(){
  if(mode==="edited"&&!v.paused&&!v.ended){
    if(simulationFrame===null)simulationFrame=requestAnimationFrame(simulationTick);
  }else if(simulationFrame!==null){
    cancelAnimationFrame(simulationFrame);
    simulationFrame=null;
  }
}
function play(){
  if(!project?.media)return;
  if(!v.paused){v.pause();return;}
  if(mode==="edited"&&segments().length){
    v.currentTime=nextSimulatedSourceTime(Math.round(v.currentTime*1000))/1000;
  }else if(v.ended)v.currentTime=0;
  v.play().catch(()=>toast("Codec non riproducibile. Usa MP4 H.264 per la preview.","error"));
}
function jump(seconds){
  if(!project?.media)return;
  const max=(mode==="rendered"?editedDuration():project.media.duration_ms)/1000;
  v.currentTime=Math.max(0,Math.min(max,(v.currentTime||0)+seconds));
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
el("cut-preset").addEventListener("change",event=>{
  const preset=event.target.value;
  if(preset!=="custom"){
    cutDraft={preset,...project.cut_presets[preset]};
    renderCutControls();
  }else{
    cutDraft={...cutDraft,preset:"custom"};
    renderCutControls();
    el("cut-advanced").open=true;
  }
  syncCutControls(project,working());
});
for(const input of document.querySelectorAll("[data-cut-setting]")){
  input.addEventListener("change",()=>{
    if(!cutDraft)return;
    const value=Number(input.value);
    if(!Number.isInteger(value)||!input.checkValidity()){
      toast("Parametro non valido: correggi il numero nell'intervallo indicato.","error");
      return;
    }
    cutDraft={...cutDraft,preset:"custom",[input.dataset.cutSetting]:value};
    renderCutControls();
    syncCutControls(project,working());
  });
}
el("analyze-action").addEventListener("click",()=>run(()=>startJob("analyze")));
el("transcribe-action").addEventListener("click",()=>run(()=>startJob("transcribe")));
el("caption-generate").addEventListener("click",()=>run(async()=>{
  if((project?.captions||[]).length&&!window.confirm(
    "Rigenerare i sottotitoli dalla trascrizione? Le correzioni precedenti verranno sostituite."
  ))return;
  const result=await post("/api/captions/generate",{
    revision:project.project_revision,style:
      captionDraft?.preset==="custom"?"social":(captionDraft?.preset||"social")
  });
  const chosen={...captionDraft};
  update(result);
  if(chosen.preset==="custom"){
    await edit("caption.configure",{config:chosen});
  }
  toast("Sottotitoli aggiunti al video. Correggi le frasi e genera una preview FFmpeg.");
}));
el("caption-style").addEventListener("change",()=>run(async()=>{
  const preset=el("caption-style").value;
  if(preset==="custom"){el("caption-appearance").open=true;return;}
  captionDraft={...project.caption_presets[preset]};
  renderCaptionSettings();updateCaptionOverlay();
  await commitCaptionSettings();
}));
for(const input of document.querySelectorAll("[data-caption-setting]")){
  const field=input.dataset.captionSetting;
  input.addEventListener("input",()=>{
    if(!(project?.captions||[]).length)return;
    previewCaptionSetting(field,input.type==="checkbox"?input.checked:
      input.type==="color"?input.value.toUpperCase():Number(input.value));
  });
  input.addEventListener("change",()=>run(()=>commitCaptionSettings()));
}
el("caption-drag-toggle").addEventListener("click",()=>{
  if(!(project?.captions||[]).length)return;
  if(mode==="rendered")changeMode("original");
  v.pause();
  captionPositionMode=!captionPositionMode;
  el("caption-drag-toggle").setAttribute("aria-pressed",String(captionPositionMode));
  el("caption-drag-toggle").textContent=captionPositionMode?
    "✓ Posizione attiva · trascina sul video":"Sposta sull'anteprima";
  updateCaptionOverlay();
  if(captionPositionMode)el("caption-overlay").focus();
});
const overlay=el("caption-overlay");
function captionPointerAt(event){
  const bounds=overlay.parentElement.getBoundingClientRect();
  if(!bounds.width||!bounds.height)return;
  const x=Math.round(100*(event.clientX-bounds.left)/bounds.width);
  const y=Math.round(100*(event.clientY-bounds.top)/bounds.height);
  previewCaptionSetting("x_pct",Math.max(15,Math.min(85,x)));
  previewCaptionSetting("y_pct",Math.max(15,Math.min(85,y)));
}
overlay.addEventListener("pointerdown",event=>{
  if(!captionPositionMode||working()||mode==="rendered")return;
  event.preventDefault();v.pause();
  captionPointer=event.pointerId;
  overlay.setPointerCapture(event.pointerId);
  captionPointerAt(event);
});
overlay.addEventListener("pointermove",event=>{
  if(captionPointer===event.pointerId)captionPointerAt(event);
});
overlay.addEventListener("pointerup",event=>{
  if(captionPointer!==event.pointerId)return;
  captionPointerAt(event);captionPointer=null;
  run(()=>commitCaptionSettings());
});
overlay.addEventListener("pointercancel",()=>{captionPointer=null;refresh().catch(()=>{});});
overlay.addEventListener("keydown",event=>{
  if(!captionPositionMode||working())return;
  if(!["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(event.key))return;
  event.preventDefault();event.stopPropagation();
  const step=event.shiftKey?5:1;
  const field=event.key==="ArrowLeft"||event.key==="ArrowRight"?"x_pct":"y_pct";
  const delta=event.key==="ArrowLeft"||event.key==="ArrowUp"?-step:step;
  previewCaptionSetting(field,Math.max(15,Math.min(85,captionDraft[field]+delta)));
  run(()=>commitCaptionSettings());
});
el("caption-clear").addEventListener("click",()=>run(async()=>{
  if(!window.confirm("Rimuovere i sottotitoli dal montaggio?"))return;
  await edit("caption.clear",{});
}));
el("export-action").addEventListener("click",()=>run(()=>startJob("render")));
el("preview-action").addEventListener("click",()=>run(()=>startJob("preview")));
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
v.addEventListener("play",()=>{followEdits();syncSimulationLoop();transport();});
v.addEventListener("pause",()=>{syncSimulationLoop();transport();});
v.addEventListener("ended",()=>{syncSimulationLoop();transport();});
v.addEventListener("seeked",()=>{followEdits();transport();});
v.addEventListener("loadedmetadata",transport);
v.addEventListener("error",()=>{if(project?.file)toast("Impossibile riprodurre il codec nel browser. Usa MP4 H.264.","error");});
el("timeline-track").addEventListener("click",event=>{
  if(!project?.media||dragHandleActive)return;const bounds=event.currentTarget.getBoundingClientRect();
  const sourceMs=Math.max(0,Math.min(1,(event.clientX-bounds.left)/bounds.width))*project.media.duration_ms;
  v.currentTime=(mode==="rendered"?outputTime(sourceMs):sourceMs)/1000;
});
el("timeline-track").addEventListener("keydown",event=>{
  if(!project?.media)return;
  if(["ArrowLeft","ArrowRight","Home","End"].includes(event.key))event.preventDefault();
  if(event.key==="ArrowLeft")jump(-5);if(event.key==="ArrowRight")jump(5);
  if(event.key==="Home")v.currentTime=mode==="rendered"?0:0;
  if(event.key==="End")v.currentTime=(mode==="rendered"?editedDuration():project.media.duration_ms)/1000;
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
  if(project?.job?.status==="running"||project?.importing||
     project?.waveform_status==="running")refresh().catch(()=>{});
},850);
refresh().catch(error=>toast(error.message,"error"));
function resizeTimeline(){
  const surface=el("timeline-surface"),track=el("timeline-track");
  if(!surface||!track)return;
  const width=Math.max(200,(surface.clientWidth-16)*timelineZoom);
  const cursor=surface.clientWidth>0?surface.scrollLeft/Math.max(1,track.scrollWidth):0;
  track.style.width=width+"px";
  el("timeline-ruler-content").style.width=width+"px";
  surface.scrollLeft=Math.max(0,cursor*width);
  el("timeline-ruler").scrollLeft=surface.scrollLeft;
  paintWaveform();
}
el("timeline-zoom").addEventListener("change",event=>{
  timelineZoom=Number(event.target.value)||1;
  resizeTimeline();
});
el("timeline-surface").addEventListener("scroll",()=>{
  el("timeline-ruler").scrollLeft=el("timeline-surface").scrollLeft;
});
/* Keep visual, keyboard and screen-reader navigation order consistent. */
function syncTimelineOrder(){
  const timeline=document.querySelector(".timeline-panel");
  const workbench=document.querySelector(".workbench");
  const inspector=document.querySelector(".inspector");
  if(window.matchMedia("(max-width: 650px)").matches){
    if(timeline.parentElement!==workbench || timeline.nextElementSibling!==inspector)
      inspector.before(timeline);
  }else if(timeline.parentElement===workbench){
    workbench.after(timeline);
  }
}
window.addEventListener("resize",()=>{
  syncTimelineOrder();
  resizeTimeline();
});
syncTimelineOrder();
resizeTimeline();

