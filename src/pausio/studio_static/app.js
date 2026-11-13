"use strict";
/* Pausio Studio: native browser UI, local APIs only, no telemetry or CDN. */
const el = id => document.getElementById(id);
const v = el("preview-video");
let project = null, mediaKey = null, mode = "original", uploading = false;
let lastJobNotice = "", toastTimeout = 0, dragLevel = 0;
let didNotifyRecovery = false;
let waveformData = null, waveformRequestedFor = null, timelineZoom = 1, previewSourceMode = "original";
let dragHandleActive = false;
const fxWaveforms=new Map(),fxWaveformsPending=new Set();
let simulationFrame = null;
let captionDraft = null, captionSource = null, captionMediaKey = null;
let captionPositionMode = false;
let captionPointer = null;
const captionNumberFields = ["x_pct","y_pct","font_size","outline_size"];
const captionColorFields = ["text_color","outline_color","background_color"];
const captionFontFields = ["font_family"];
const fontFallBack = new Set(["Georgia","Times New Roman","Courier New"]);
function captionConfig(){ return captionDraft||project?.caption_config||project?.caption_presets?.social; }
function renderCaptionSettings(){
  if(!captionDraft)return;
  el("caption-style").value=captionDraft.preset;
  for(const field of [...captionNumberFields,...captionColorFields,...captionFontFields]){
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
  const picker=el("caption-font-family");
  const families=next.caption_fonts||["Arial"];
  if(picker.options.length!==families.length||
     families.some((name,i)=>picker.options[i]?.value!==name)){
    picker.replaceChildren(...families.map(name=>{
      const option=document.createElement("option");
      option.value=name;option.textContent=name;option.style.fontFamily='"'+name+'", sans-serif';
      return option;
    }));
  }
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

/* The video player is the clock: HTML audio elements monitor local FX live,
   while the FFmpeg preview/export already contain the final mix. Do not double play.
   Commands/FFmpeg remain the source of truth for the actual rendered sound. */
let fxMonitoringEnabled = true;
let fxAudioContext = null;
let voiceGainNode = null, voiceSourceNode = null;
let audioMixerDraft = null;
const clipMixerDrafts = new Map();
const baseAudioMix = () => ({voice_gain_db:0,voice_muted:false,fx_gain_db:0,fx_muted:false});
const currentAudioMix = () => audioMixerDraft || project?.audio_mix || baseAudioMix();
const currentClipMix = clip => clipMixerDrafts.get(clip.id) || clip;
const gainPercent = db => Math.round(Math.pow(10,db/20)*100);
const gainText = db => gainPercent(db)+"% · "+(db>0?"+":"")+db+" dB";
const gainScalar = db => Math.pow(10,db/20);

function syncVoicePlayback(){
  if(!project?.media)return;
  const mix=currentAudioMix();
  // FFmpeg preview includes voice gain/mute already; never apply it twice.
  const level=mode==="rendered"?1:mix.voice_muted?0:gainScalar(mix.voice_gain_db);
  if(voiceGainNode){
    v.volume=1;
    voiceGainNode.gain.value=level;
  }else{
    v.volume=Math.max(0,Math.min(1,level));
  }
}

const liveFxPlayers = new Map();
function pauseLiveFx(){
  for(const {audio} of liveFxPlayers.values())if(!audio.paused)audio.pause();
}
function disposeLiveFx(id){
  const player=liveFxPlayers.get(id);if(!player)return;
  player.audio.pause();player.audio.removeAttribute("src");player.audio.load();
  if(player.source)player.source.disconnect();
  if(player.gain)player.gain.disconnect();
  liveFxPlayers.delete(id);
}
function reconcileLiveFx(){
  const allowed=new Map((project?.audio_clips||[])
    .filter(c=>c.available).map(c=>[c.id,c]));
  for(const [id,player] of liveFxPlayers){
    if(!allowed.has(id)||allowed.get(id).asset_sha256!==player.sha)disposeLiveFx(id);
  }
}
function unlockFxAudio(){
  if(!project?.media)return;
  if(!fxAudioContext){
    const AudioContextType=window.AudioContext||window.webkitAudioContext;
    if(AudioContextType){
      try{fxAudioContext=new AudioContextType();}
      catch{/* HTMLAudioElement fallback still works on supported browsers. */}
    }
  }
  if(fxAudioContext&&!voiceGainNode){
    try{
      voiceSourceNode=fxAudioContext.createMediaElementSource(v);
      voiceGainNode=fxAudioContext.createGain();
      voiceSourceNode.connect(voiceGainNode);
      voiceGainNode.connect(fxAudioContext.destination);
    }catch{
      // Native volume is a safe fallback; amplification above 0 dB needs Web Audio.
      voiceGainNode=null;
    }
  }
  syncVoicePlayback();
  if(fxAudioContext?.state==="suspended")
    fxAudioContext.resume().catch(()=>toast("Audio del browser sospeso. Premi Play o ascolta la preview FFmpeg.","error"));
}
function createLiveFxPlayer(clip){
  const audio=new Audio();
  audio.preload="auto";
  audio.src="/api/audio/"+encodeURIComponent(clip.asset_sha256);
  audio.loop=false;
  const player={audio,sha:clip.asset_sha256,gain:null,source:null,starting:false,failed:false};
  if(fxAudioContext){
    try{
      const source=fxAudioContext.createMediaElementSource(audio);
      const gain=fxAudioContext.createGain();
      source.connect(gain);gain.connect(fxAudioContext.destination);
      player.source=source;player.gain=gain;
    }catch{/* If Web Audio is unavailable, the media element uses its own volume. */}
  }
  audio.addEventListener("error",()=>{
    if(!player.failed){
      player.failed=true;
      toast("Il browser non riesce a riprodurre questo FX. Usa «Genera preview» per ascoltarlo con FFmpeg.","error");
    }
    audio.pause();
  });
  liveFxPlayers.set(clip.id,player);
  return player;
}
function monitoredOutputMs(){
  if(!project?.media||!fxMonitoringEnabled||mode==="rendered"||v.paused||v.ended||v.seeking)
    return null;
  const source=Math.round((v.currentTime||0)*1000);
  if(!project.plan)return source;
  // FX commands are in the edited timeline: never play them in a removed gap.
  const kept=segments().some(seg=>source>=seg.start_ms&&source<seg.end_ms);
  return kept?outputTime(source):null;
}
function syncLiveFx(){
  reconcileLiveFx();
  const time=monitoredOutputMs();
  if(time===null){pauseLiveFx();return;}
  const current=new Set();
  for(const clip of project.audio_clips||[]){
    if(!clip.available)continue;
    const relative=time-clip.start_ms;
    if(relative<0||relative>=clip.duration_ms)continue;
    current.add(clip.id);
    const player=liveFxPlayers.get(clip.id)||createLiveFxPlayer(clip);
    if(player.failed)continue;
    const {audio,gain}=player;
    const mix=currentAudioMix(),selected=currentClipMix(clip);
    const effectiveGain=(mix.fx_muted||selected.muted||v.muted)?0:
      gainScalar(selected.gain_db+mix.fx_gain_db);
    if(gain){gain.gain.value=effectiveGain;audio.volume=1;}
    else{audio.volume=Math.max(0,Math.min(1,effectiveGain));}
    audio.playbackRate=v.playbackRate;
    const position=relative/1000;
    // Resync after seeking or cut simulation jumps; avoid excessive micro-seeks.
    if(Math.abs((audio.currentTime||0)-position)>.12){
      try{audio.currentTime=position;}catch{/* Seek will be retried after metadata. */}
    }
    if(audio.paused&&!player.starting){
      player.starting=true;
      audio.play().catch(error=>{
        // A seek/pause or cut boundary can abort a pending play() normally.
        // Do not permanently mark a valid asset broken for this case.
        if(error?.name==="AbortError"||v.paused||mode==="rendered"||
           !fxMonitoringEnabled)return;
        if(!player.failed){
          player.failed=true;
          toast("Impossibile ascoltare l'FX live. Prova la preview FFmpeg.","error");
        }
      }).finally(()=>{player.starting=false;});
    }
  }
  for(const [id,player] of liveFxPlayers)
    if(!current.has(id)&&!player.audio.paused)player.audio.pause();
}
function updateFxMonitorUI(){
  const clips=project?.audio_clips||[];
  const toggle=el("fx-monitor-toggle"),status=el("fx-monitor-status");
  toggle.hidden=!project?.media||!clips.length;
  status.hidden=!project?.media||!clips.length;
  if(!clips.length)return;
  toggle.disabled=mode==="rendered";
  toggle.setAttribute("aria-pressed",String(mode==="rendered"||fxMonitoringEnabled));
  toggle.textContent=mode==="rendered"?"♫ FX nel video":fxMonitoringEnabled?"♫ FX attivi":"♫ FX spenti";
  status.textContent=mode==="rendered"?
    "L'anteprima FFmpeg contiene già gli effetti: nessuna duplicazione audio.":
    fxMonitoringEnabled?"FX udibili durante Play, insieme alla voce. Anteprima live; verifica il mix finale con «Genera preview».":
    "Ascolto degli FX disattivato: il rendering finale li include comunque.";
}

function paintAudioMixer(){
  const mix=currentAudioMix();
  for(const bus of ["voice","fx"]){
    const muted=mix[bus+"_muted"],gain=mix[bus+"_gain_db"];
    const slider=el(bus+"-gain"),label=el(bus+"-gain-label"),button=el(bus+"-mute");
    if(document.activeElement!==slider||!audioMixerDraft)slider.value=String(gain);
    slider.setAttribute("aria-valuetext",gainText(gain)+(muted?" · silenziato":""));
    label.textContent=muted?"Silenz.: "+gainText(gain):gainText(gain);
    button.setAttribute("aria-pressed",String(muted));
    button.textContent=muted?"Riattiva":"Silenzia";
    button.closest(".mixer-track").classList.toggle("is-muted",muted);
  }
}
function drawAudioMixer(){
  paintAudioMixer();
  const has=!!project?.media,busy=working();
  for(const bus of ["voice","fx"]){
    const emptyFx=bus==="fx"&&!(project?.audio_clips||[]).length;
    for(const suffix of ["gain","mute","reset"])
      el(bus+"-"+suffix).disabled=!has||busy||emptyFx;
  }
}
async function commitAudioBus(bus,changes){
  const before=project?.audio_mix||baseAudioMix();
  const next={...before,...changes};
  const unchanged=Object.keys(next).every(key=>before[key]===next[key]);
  if(unchanged){
    audioMixerDraft=null;paintAudioMixer();syncVoicePlayback();syncLiveFx();
    return;
  }
  await edit("audio.mixer.configure",next);
}
function ensureLiveAudioPreview(){
  // Switching via changeMode() would rebuild and detach the slider while
  // dragging. Switch only the media source; the next saved event redraws UI.
  if(mode!=="rendered"||!project?.media)return;
  const sourceAt=sourceFromOutput(Math.round((v.currentTime||0)*1000));
  v.pause();pauseLiveFx();
  mode="original";previewSourceMode="original";
  v.src="/api/media?v="+encodeURIComponent(mediaKey);
  v.addEventListener("loadedmetadata",()=>{
    v.currentTime=Math.min(v.duration||0,sourceAt/1000);
    transport();
  },{once:true});
  v.load();
  for(const button of document.querySelectorAll("[data-mode]")){
    const selected=button.dataset.mode==="original";
    button.classList.toggle("active",selected);
    button.setAttribute("aria-pressed",String(selected));
  }
  updateFxMonitorUI();syncVoicePlayback();transport();
}
function setupAudioMixer(){
  for(const bus of ["voice","fx"]){
    const slider=el(bus+"-gain"),field=bus+"_gain_db",muted=bus+"_muted";
    slider.addEventListener("input",()=>{
      ensureLiveAudioPreview();
      const value=Number(slider.value);
      audioMixerDraft={...currentAudioMix(),[field]:value};
      paintAudioMixer();syncVoicePlayback();syncLiveFx();
    });
    slider.addEventListener("change",()=>run(()=>commitAudioBus(bus,{[field]:Number(slider.value)})));
    el(bus+"-mute").addEventListener("click",()=>{
      ensureLiveAudioPreview();
      run(()=>commitAudioBus(bus,{[muted]:!(project?.audio_mix||baseAudioMix())[muted]}));
    });
    el(bus+"-reset").addEventListener("click",()=>{
      ensureLiveAudioPreview();
      run(()=>commitAudioBus(bus,{[field]:0,[muted]:false}));
    });
  }
}
setupAudioMixer();

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
  audioMixerDraft=null;clipMixerDrafts.clear();
  const has=!!next.file, plan=!!next.plan, approved=!!next.approved, ready=!!next.export_ready, busy=working();
  if(mode==="edited"&&(!plan||(next.media&&editedDuration()>=next.media.duration_ms))){
    mode="original";
    v.pause();
    syncSimulationLoop();
  }
  document.body.classList.toggle("has-media",has);
  syncCutControls(next, busy);
  syncCaptionSettings(next, busy);
  el("fx-panel").hidden=!has;
  el("audio-mixer").hidden=!has;
  el("fx-import").disabled=!has||busy;
  if(next.media_id && mediaKey!==next.media_id){
    mediaKey=next.media_id;mode="original";previewSourceMode="original";
    waveformData=null;waveformRequestedFor=null;
    fxWaveforms.clear();fxWaveformsPending.clear();
    for(const id of [...liveFxPlayers.keys()])disposeLiveFx(id);
    paintWaveform();
    v.pause();v.src="/api/media?v="+encodeURIComponent(mediaKey);v.load();tab("cuts");
  }
  if(mode==="rendered"&&!next.preview_ready&&next.media&&mediaKey===next.media_id){
    const sourceAt=sourceFromOutput(Math.round((v.currentTime||0)*1000));
    v.pause();pauseLiveFx();mode="original";previewSourceMode="original";
    v.src="/api/media?v="+encodeURIComponent(mediaKey);
    v.addEventListener("loadedmetadata",()=>{
      v.currentTime=Math.min(v.duration||0,sourceAt/1000);
      transport();
    },{once:true});
    v.load();
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
  drawTimeRuler();
  el("timeline-center-playhead").disabled=!has;
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
  if(next.media_id!==editorSelectionMedia){
    editorSelectionMedia=next.media_id;
    editorSelection=null;
  }
  drawSegments();drawTimeline();drawFx();drawTranscript();drawCaptionEditor();
  drawCaptionTimeline();renderWorkspaceLibraries();syncEditorSelection();
  window.pausioVideoFx?.update(next);
  window.pausioFaceReframe?.update(next);
  window.pausioVideoTransitions?.update(next);
  updateFxMonitorUI();drawAudioMixer();syncVoicePlayback();syncLiveFx();transport();
  syncDesktopCommands();
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

/* An ephemeral selection connects the existing timeline and inspector controls.
   It never owns source edits, so changing selection does not increment revision. */
let editorSelection = null;
let editorSelectionMedia = null;

function renderWorkspaceLibraries(){
  const name=el("app").dataset.workspace;
  const audioPane=el("workspace-audio-library");
  const captionPane=el("workspace-caption-library");
  const desktop=!window.matchMedia("(max-width: 1000px)").matches;
  audioPane.hidden=!desktop||name!=="audio";
  captionPane.hidden=!desktop||name!=="captions";
  el("workspace-audio-import").disabled=!project?.media||working();
  const audioList=el("workspace-audio-items");
  audioList.replaceChildren();
  const clips=project?.audio_clips||[];
  if(!clips.length){
    const info=document.createElement("p");
    info.className="workspace-library-empty";
    info.textContent="Nessun effetto importato. Aggiungi un riser o un whoosh per iniziare.";
    audioList.append(info);
  }
  for(const clip of clips){
    const button=document.createElement("button");
    button.type="button";button.className="workspace-library-item workspace-audio-item";
    button.dataset.clipId=clip.id;
    button.setAttribute("aria-pressed","false");
    const nameLine=document.createElement("strong");nameLine.textContent=clip.filename;
    const meta=document.createElement("span");
    meta.textContent=msFormat(clip.start_ms,true)+" · "+
      shortDuration(clip.duration_ms)+(clip.available?"":" · File mancante");
    button.append(nameLine,meta);
    button.addEventListener("click",()=>selectEditorItem("fx",clip.id,{seek:true}));
    audioList.append(button);
  }
  const captionList=el("workspace-caption-items");
  captionList.replaceChildren();
  const cues=project?.captions||[];
  const query=el("workspace-caption-search").value.trim().toLocaleLowerCase("it");
  const filtered=cues.filter(c=>!query||c.text.toLocaleLowerCase("it").includes(query));
  el("workspace-caption-count").textContent=
    cues.length?(filtered.length+" di "+cues.length+" frasi"):"Nessun sottotitolo generato";
  if(!filtered.length){
    const info=document.createElement("p");info.className="workspace-library-empty";
    info.textContent=cues.length?"Nessuna frase corrisponde alla ricerca.":
      "Genera i sottotitoli dalla trascrizione per visualizzarli qui.";
    captionList.append(info);
  }
  for(const cue of filtered){
    const index=cues.findIndex(c=>c.id===cue.id);
    const button=document.createElement("button");
    button.type="button";button.className="workspace-library-item workspace-caption-item";
    button.dataset.captionId=cue.id;
    button.setAttribute("aria-pressed","false");
    const time=document.createElement("span");
    time.textContent=(index+1)+". "+msFormat(cue.start_ms,true)+" – "+msFormat(cue.end_ms,true);
    const label=document.createElement("strong");label.textContent=cue.text;
    button.append(time,label);
    button.addEventListener("click",()=>selectEditorItem("caption",cue.id,{seek:true}));
    captionList.append(button);
  }
}

function selectedEditorItem(){
  if(!editorSelection||!project?.media)return null;
  if(editorSelection.type==="segment"){
    const segment=segments().find(item=>item.id===editorSelection.id);
    return segment?{type:"segment",value:segment}:null;
  }
  if(editorSelection.type==="fx"){
    const clip=(project.audio_clips||[]).find(item=>item.id===editorSelection.id);
    return clip?{type:"fx",value:clip}:null;
  }
  if(editorSelection.type==="caption"){
    const cue=(project.captions||[]).find(item=>item.id===editorSelection.id);
    return cue?{type:"caption",value:cue}:null;
  }
  return null;
}
function syncEditorSelection(){
  const selected=selectedEditorItem();
  if(!selected)editorSelection=null;
  const panel=el("selection-inspector");
  panel.hidden=!selected;
  if(selected){
    if(selected.type==="segment"){
      const index=segments().findIndex(s=>s.id===selected.value.id);
      el("selection-title").textContent="Intervallo "+(index+1)+" · Mantieni";
      el("selection-description").textContent=
        msFormat(selected.value.start_ms,true)+" – "+
        msFormat(selected.value.end_ms,true)+" · "+
        shortDuration(selected.value.end_ms-selected.value.start_ms);
    }else if(selected.type==="fx"){
      const clip=selected.value;
      el("selection-title").textContent=clip.filename;
      el("selection-description").textContent=
        "FX · "+msFormat(clip.start_ms,true)+" nel montaggio · "+
        gainText(clip.gain_db)+(clip.muted?" · Silenziato":"");
    }else{
      const cue=selected.value;
      const index=(project.captions||[]).findIndex(c=>c.id===cue.id);
      el("selection-title").textContent="Sottotitolo "+(index+1);
      el("selection-description").textContent=
        msFormat(cue.start_ms,true)+" – "+msFormat(cue.end_ms,true)+
        " · "+cue.text;
    }
    el("selection-goto").textContent=selected.type==="fx"?
      "Apri controlli effetto":selected.type==="caption"?
      "Correggi sottotitolo":"Apri intervallo";
  }
  for(const card of document.querySelectorAll(".segment-card")){
    const isSelected=selected?.type==="segment"&&card.dataset.segmentId===selected.value.id;
    card.classList.toggle("is-selected",!!isSelected);
  }
  for(const region of document.querySelectorAll(".timeline-region")){
    const isSelected=selected?.type==="segment"&&region.dataset.segmentId===selected.value.id;
    region.classList.toggle("is-selected",!!isSelected);
    region.querySelector(".region-select")?.setAttribute("aria-pressed",String(!!isSelected));
  }
  for(const item of document.querySelectorAll(".fx-item, .fx-clip-mark")){
    const isSelected=selected?.type==="fx"&&item.dataset.clipId===selected.value.id;
    item.classList.toggle("is-selected",!!isSelected);
    if(item.classList.contains("fx-clip-mark"))
      item.setAttribute("aria-pressed",String(!!isSelected));
  }
  for(const item of document.querySelectorAll(".workspace-audio-item, .workspace-caption-item")){
    const isSelected=selected&&(
      selected.type==="fx"&&item.dataset.clipId===selected.value.id||
      selected.type==="caption"&&item.dataset.captionId===selected.value.id
    );
    item.classList.toggle("is-selected",!!isSelected);
    item.setAttribute("aria-pressed",String(!!isSelected));
  }
  for(const item of document.querySelectorAll(".caption-cue-mark, .caption-edit-card")){
    const isSelected=selected?.type==="caption"&&item.dataset.captionId===selected.value.id;
    item.classList.toggle("is-selected",!!isSelected);
    if(item.classList.contains("caption-cue-mark"))
      item.setAttribute("aria-pressed",String(!!isSelected));
  }
}
function selectEditorItem(type,id,options={}){
  editorSelection={type,id};
  if(type==="segment")setWorkspace("cuts");
  else if(type==="fx")setWorkspace("audio");
  else if(type==="caption")setWorkspace("captions");
  syncEditorSelection();
  const selected=selectedEditorItem();
  if(options.seek&&selected){
    const sourceTime=type==="segment"||type==="caption"?selected.value.start_ms:
      project.plan?sourceFromOutput(selected.value.start_ms):selected.value.start_ms;
    const seekMs=mode==="rendered"?outputTime(sourceTime):sourceTime;
    v.currentTime=Math.max(0,seekMs)/1000;
  }
}
function focusEditorSelection(){
  const selected=selectedEditorItem();
  if(!selected)return;
  const selector=selected.type==="segment"?
    '.segment-card[data-segment-id="'+selected.value.id+'"]':
    selected.type==="fx"?
    '.fx-item[data-clip-id="'+selected.value.id+'"]':
    '.caption-edit-card[data-caption-id="'+selected.value.id+'"]';
  const element=document.querySelector(selector);
  if(!element)return;
  element.scrollIntoView({block:"nearest",behavior:"instant"});
  const control=selected.type==="segment"?
    element.querySelector(".start-input"):
    selected.type==="fx"?
    element.querySelector('input[aria-label^="Inizio"]'):
    element.querySelector(".caption-edit-input");
  control?.focus({preventScroll:true});
}

function drawSegments(){
  const list=el("segment-list");list.replaceChildren();
  for(const [index,s] of segments().entries()){
    const card=document.createElement("article");card.className="segment-card";card.dataset.index=index;
    card.dataset.segmentId=s.id;
    card.innerHTML='<div class="segment-top"><span class="segment-title"><span class="segment-index">'+
      String(index+1).padStart(2,"0")+'</span>Mantieni</span><span class="segment-duration">'+
      shortDuration(s.end_ms-s.start_ms)+'</span></div>'+
      '<div class="segment-fields"><label>Da (secondi)<input class="start-input" type="number" min="0" step=".01"></label>'+
      '<label>A (secondi)<input class="end-input" type="number" min="0" step=".01"></label></div>'+
      '<div class="segment-card-actions"><button type="button" class="segment-action listen">▶ Ascolta da qui</button>'+
      '<button type="button" class="segment-action remove">Escludi</button></div>';
    const choose=document.createElement("button");
    choose.type="button";choose.className="segment-select";
    choose.textContent="Seleziona intervallo";
    choose.setAttribute("aria-label","Seleziona intervallo "+(index+1)+" nella timeline");
    choose.addEventListener("click",()=>selectEditorItem("segment",s.id,{seek:true}));
    card.querySelector(".segment-top").append(choose);
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
/* Fast, read-only transcript browsing: the actual ASR stays in the local
   session. Search, selection and scrolling never create project commands. */
let transcriptSelectedIndex=-1,transcriptSourceMedia=null;
function visibleTranscriptRows(){
  return [...el("transcript-list").querySelectorAll(".transcript-item")];
}
function updateTranscriptActive(){
  if(!project?.transcript)return;
  const sourceMs=timelineSourceMs();
  for(const row of visibleTranscriptRows()){
    const inTime=sourceMs>=Number(row.dataset.startMs)&&sourceMs<Number(row.dataset.endMs);
    row.classList.toggle("is-current",inTime);
    row.classList.toggle("is-selected",Number(row.dataset.index)===transcriptSelectedIndex);
    row.querySelector(".transcript-seek")?.setAttribute("aria-current",inTime?"true":"false");
  }
}
function selectTranscriptRow(index,{play=false}={}){
  const segment=project?.transcript?.segments?.[index];
  if(!segment)return;
  transcriptSelectedIndex=index;
  // The transcript always describes the ORIGINAL source, including phrases
  // removed by a cut. A rendered preview cannot seek into discarded speech.
  if(mode!=="original"){
    mode="original";
    update(project);
  }
  v.currentTime=segment.start_ms/1000;
  updateTranscriptActive();
  const row=el("transcript-list").querySelector('[data-index="'+index+'"]');
  row?.scrollIntoView({block:"nearest"});
  if(play)v.play().catch(()=>{});
}
function navigateTranscript(offset){
  const rows=visibleTranscriptRows();
  if(!rows.length)return;
  let current=rows.findIndex(row=>Number(row.dataset.index)===transcriptSelectedIndex);
  const next=current<0?(offset>0?0:rows.length-1):
    Math.max(0,Math.min(rows.length-1,current+offset));
  const chosen=Number(rows[next].dataset.index);
  selectTranscriptRow(chosen);
  // Selecting from a rendered preview may rebuild the inspector DOM.
  // Focus the NEW live row, not a stale node from before the mode switch.
  el("transcript-list").querySelector('[data-index="'+chosen+'"] .transcript-seek')
    ?.focus({preventScroll:true});
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
  el("transcript-review").hidden=!tr;
  if(project?.media_id!==transcriptSourceMedia){
    transcriptSourceMedia=project?.media_id;
    transcriptSelectedIndex=-1;
    el("transcript-search").value="";
  }
  if(!tr)return;
  const query=el("transcript-search").value.trim().toLocaleLowerCase("it");
  const segments=tr.segments||[];
  const matches=segments.map((seg,index)=>({seg,index})).filter(({seg})=>
    !query||(seg.text||"").toLocaleLowerCase("it").includes(query));
  el("transcript-match-count").textContent=matches.length+" di "+segments.length+" frasi";
  el("transcript-previous").disabled=matches.length===0;
  el("transcript-next").disabled=matches.length===0;
  for(const {seg,index} of matches){
    const row=document.createElement("article");row.className="transcript-item";
    row.dataset.index=String(index);
    row.dataset.startMs=String(seg.start_ms);
    row.dataset.endMs=String(seg.end_ms);
    const seek=document.createElement("button");
    seek.className="transcript-seek";seek.type="button";
    seek.setAttribute("aria-label","Vai alla frase "+(index+1)+": "+seg.text);
    const time=document.createElement("span");time.className="transcript-time";
    time.textContent=msFormat(seg.start_ms,true);
    const content=document.createElement("span");content.className="transcript-line";
    content.textContent=seg.text||"(senza testo)";
    seek.append(time,content);
    seek.addEventListener("click",()=>selectTranscriptRow(index));
    row.append(seek);list.append(row);
  }
  if(!matches.length){
    const note=document.createElement("p");note.className="transcript-note";
    note.textContent=segments.length?
      "Nessuna frase corrisponde alla ricerca.":
      tr.text||"Non è stato rilevato parlato.";
    list.append(note);
  }
  updateTranscriptActive();
}

function captionMoveLimits(cue){
  const cues=project?.captions||[];
  const index=cues.findIndex(c=>c.id===cue.id);
  if(index<0||!project?.media)return null;
  const previous=cues[index-1],next=cues[index+1];
  const length=cue.end_ms-cue.start_ms;
  return {min:previous?.end_ms||0,
    max:(next?.start_ms||project.media.duration_ms)-length};
}
function submitCaptionTiming(cue,startMs,endMs){
  if(startMs===cue.start_ms&&endMs===cue.end_ms)return Promise.resolve();
  return edit("caption.retime",{caption_id:cue.id,
    start_ms:Math.round(startMs),end_ms:Math.round(endMs)});
}

function drawCaptionEditor(){
  const list=el("caption-edit-list");list.replaceChildren();
  for(const cue of project?.captions||[]){
    const card=document.createElement("article");card.className="caption-edit-card";
    card.dataset.captionId=cue.id;
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
    const timing=document.createElement("div");
    timing.className="caption-timing-fields";
    const makeTimeField=(label,value,key)=>{
      const wrapper=document.createElement("label");
      wrapper.textContent=label;
      const field=document.createElement("input");
      field.type="number";field.step=".001";field.min="0";
      field.max=String(project.media.duration_ms/1000);
      field.value=(value/1000).toFixed(3);
      field.disabled=working();
      field.className="caption-time-"+key;
      field.setAttribute("aria-label",label+" sottotitolo "+heading.textContent);
      wrapper.append(field);timing.append(wrapper);
      return field;
    };
    const timeStart=makeTimeField("Inizio (secondi)",cue.start_ms,"start");
    const timeEnd=makeTimeField("Fine (secondi)",cue.end_ms,"end");
    const saveTiming=()=>run(async()=>{
      if(!timeStart.checkValidity()||!timeEnd.checkValidity())
        throw Error("Controlla i secondi della frase.");
      const start=Math.round(Number(timeStart.value)*1000),
        end=Math.round(Number(timeEnd.value)*1000);
      await submitCaptionTiming(cue,start,end);
    });
    timeStart.addEventListener("change",saveTiming);
    timeEnd.addEventListener("change",saveTiming);

    const choose=document.createElement("button");
    choose.type="button";choose.className="caption-select";
    choose.textContent="Seleziona sulla timeline";
    choose.setAttribute("aria-label","Seleziona sottotitolo da "+msFormat(cue.start_ms,true));
    choose.addEventListener("click",()=>selectEditorItem("caption",cue.id,{seek:true}));
    // Keep Save text first for existing keyboard order and automated flows.
    card.append(heading,input,timing,save,choose);
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
  const fallback=config.font_family==="Courier New"?"monospace":
    fontFallBack.has(config.font_family)?"serif":"sans-serif";
  overlay.style.fontFamily='"'+config.font_family+'", '+fallback;
  overlay.style.color=config.text_color;
  overlay.style.webkitTextStroke=(config.outline_size*scale)+"px "+config.outline_color;
  overlay.style.textShadow="0 1px 2px "+config.outline_color;
  overlay.style.background=config.background?config.background_color+"CC":"transparent";
  const value=cue?.text||"";
  if(overlay.textContent!==value)overlay.textContent=value;
}

/* FX are stored in EDITED time, but the displayed source waveform uses SOURCE time.
   Split FX into pieces at every kept-interval boundary, avoiding false alignment. */
function fxSourcePieces(clip){
  const duration=project?.media?.duration_ms||0;
  const keep=project?.plan?segments():[{start_ms:0,end_ms:duration}];
  const total=project?.plan?editedDuration():duration;
  const last=Math.min(total,clip.start_ms+clip.duration_ms);
  let elapsed=0;
  const pieces=[];
  for(const segment of keep){
    const len=segment.end_ms-segment.start_ms;
    const from=Math.max(elapsed,clip.start_ms),to=Math.min(elapsed+len,last);
    if(from<to)pieces.push({
      sourceStart:segment.start_ms+from-elapsed,
      sourceEnd:segment.start_ms+to-elapsed,
      assetStart:from-clip.start_ms,
      assetEnd:to-clip.start_ms
    });
    elapsed+=len;
  }
  return pieces;
}
function requestFxWaveform(clip){
  const sha=clip.asset_sha256;
  if(!clip.available||fxWaveforms.has(sha)||fxWaveformsPending.has(sha))return;
  fxWaveformsPending.add(sha);
  fetch("/api/audio/waveform/"+sha,{cache:"no-store"}).then(async res=>{
    if(!res.ok)throw Error("Waveform FX non disponibile.");
    return res.json();
  }).then(data=>{
    if(data.asset_sha256!==sha||!Array.isArray(data.values))throw Error("Waveform errata");
    fxWaveforms.set(sha,data.values);paintFxWaveforms();
  }).catch(()=>fxWaveforms.set(sha,[])).finally(()=>fxWaveformsPending.delete(sha));
}
function paintFxWaveforms(){
  for(const canvas of document.querySelectorAll(".fx-clip-waveform")){
    const peaks=fxWaveforms.get(canvas.dataset.sha);
    const bounds=canvas.getBoundingClientRect();
    const w=Math.max(1,Math.round(bounds.width)),h=Math.max(1,Math.round(bounds.height));
    if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
    const ctx=canvas.getContext("2d");if(!ctx)continue;
    ctx.clearRect(0,0,w,h);
    if(!peaks?.length)continue;
    const from=Number(canvas.dataset.from),to=Number(canvas.dataset.to),duration=Number(canvas.dataset.duration);
    ctx.fillStyle="rgba(241,217,252,.82)";
    for(let x=0;x<w;x++){
      const a=Math.floor((from+(to-from)*x/w)/duration*peaks.length);
      const b=Math.max(a+1,Math.ceil((from+(to-from)*(x+1)/w)/duration*peaks.length));
      let peak=0;
      for(let i=a;i<Math.min(b,peaks.length);i++)peak=Math.max(peak,peaks[i]);
      const height=Math.max(1,peak/1000*(h-8));
      ctx.fillRect(x,Math.round((h-height)/2),1,Math.ceil(height));
    }
  }
}
function bindFxDrag(mark,clip,sourceStart){
  const edited=project?.plan?editedDuration():project.media.duration_ms;
  const max=Math.max(0,Math.min(project.media.duration_ms,edited)-1);
  const clamp=x=>Math.max(0,Math.min(max,Math.round(x)));
  const commit=ms=>ms===clip.start_ms?Promise.resolve():edit("audio.update",
    {clip_id:clip.id,start_ms:ms,gain_db:clip.gain_db});
  mark.addEventListener("click",event=>event.stopPropagation());
  mark.addEventListener("keydown",event=>{
    if(!["ArrowLeft","ArrowRight"].includes(event.key)||working())return;
    event.preventDefault();event.stopPropagation();
    const step=event.shiftKey?500:100;
    run(()=>commit(clamp(clip.start_ms+(event.key==="ArrowRight"?step:-step))));
  });
  mark.addEventListener("pointerdown",event=>{
    if(event.button!==0||working())return;
    event.preventDefault();event.stopPropagation();
    dragHandleActive=true;mark.classList.add("dragging");
    mark.setPointerCapture(event.pointerId);
    const firstX=event.clientX;
    const width=el("timeline-track").getBoundingClientRect().width;
    const sourceDuration=project.media.duration_ms;
    const map=project.plan?outputTime:(x=>x);
    let pending=clip.start_ms;
    const move=ev=>{
      const delta=(ev.clientX-firstX)/Math.max(1,width)*sourceDuration;
      const at=Math.max(0,Math.min(sourceDuration,sourceStart+delta));
      pending=clamp(clip.start_ms+Math.round((map(at)-map(sourceStart))/100)*100);
      mark.style.transform="translateX("+(ev.clientX-firstX)+"px)";
    };
    const finish=ev=>{cleanup(ev);run(()=>commit(pending));};
    const cancel=ev=>cleanup(ev);
    const cleanup=ev=>{
      mark.removeEventListener("pointermove",move);
      mark.removeEventListener("pointerup",finish);
      mark.removeEventListener("pointercancel",cancel);
      if(mark.hasPointerCapture(ev.pointerId))mark.releasePointerCapture(ev.pointerId);
      mark.classList.remove("dragging");mark.style.transform="";
      window.setTimeout(()=>{dragHandleActive=false;},0);
    };
    mark.addEventListener("pointermove",move);
    mark.addEventListener("pointerup",finish);
    mark.addEventListener("pointercancel",cancel);
  });
}

function drawFx(){
  const list=el("fx-list"),lane=el("fx-lane");list.replaceChildren();lane.replaceChildren();
  const clips=project?.audio_clips||[];
  const duration=project?.media?.duration_ms||0;
  el("fx-track-empty").hidden=clips.length>0;
  el("fx-hint").textContent=clips.length?
    clips.length+" effetto/i audio · Waveform e FX condividono la scala. Le clip sono suddivise visivamente dove ci sono tagli. Trascina o usa ← →.":
    "Nessun effetto. Posiziona il cursore sul video e importa un riser, un whoosh o un altro audio.";
  for(const clip of clips){
    const pieces=fxSourcePieces(clip);
    for(const [index,frag] of pieces.entries()){
      const mark=document.createElement("button");
      mark.type="button";
      mark.className="fx-clip-mark"+(clip.available?"":" missing")+
        ((clip.muted||currentAudioMix().fx_muted)?" is-muted":"");
      mark.dataset.clipId=clip.id;
      mark.addEventListener("click",()=>{if(!dragHandleActive)selectEditorItem("fx",clip.id,{seek:true});});
      mark.title=clip.filename+" · inizio nel montaggio "+msFormat(clip.start_ms,true)+" · trascina o usa le frecce";
      mark.setAttribute("aria-label","Sposta effetto "+clip.filename+", inizio "+
        msFormat(clip.start_ms,true)+" nel montaggio. Frecce ±0,1 s; Shift ±0,5 s.");
      mark.disabled=working();
      mark.style.left=(frag.sourceStart/duration*100).toFixed(4)+"%";
      mark.style.width=((frag.sourceEnd-frag.sourceStart)/duration*100).toFixed(4)+"%";
      const canvas=document.createElement("canvas");canvas.className="fx-clip-waveform";
      canvas.dataset.sha=clip.asset_sha256;canvas.dataset.from=frag.assetStart;
      canvas.dataset.to=frag.assetEnd;canvas.dataset.duration=clip.duration_ms;
      canvas.setAttribute("aria-hidden","true");mark.append(canvas);
      if(index===0){
        const title=document.createElement("span");title.className="fx-clip-title";
        title.textContent=clip.filename;mark.append(title);
      }
      bindFxDrag(mark,clip,frag.sourceStart);
      lane.append(mark);
    }
    if(clip.available)requestFxWaveform(clip);
    const item=document.createElement("div");item.className="fx-item";
    item.dataset.clipId=clip.id;
    const name=document.createElement("div");name.className="fx-item-name";
    const label=document.createElement("strong");label.textContent=clip.filename;
    const status=document.createElement("span");
    status.textContent=!clip.available?"File mancante · reimporta per ricollegare":
      !pieces.length?"Fuori dalla durata montata · modifica inizio":
      "Durata "+shortDuration(clip.duration_ms)+" · FX incluso nella preview e nell'export";
    if(!clip.available)status.className="fx-missing";
    const choose=document.createElement("button");
    choose.type="button";choose.className="fx-select";
    choose.textContent="Seleziona";
    choose.setAttribute("aria-label","Seleziona effetto "+clip.filename);
    choose.addEventListener("click",()=>selectEditorItem("fx",clip.id,{seek:true}));
    name.append(label,status,choose);item.append(name);
    const controls=[
      ["Inizio (sec)","start_ms",clip.start_ms/1000,.001,0,Math.max(0,((project.plan?editedDuration():duration)-1)/1000)],
      ["Volume (dB)","gain_db",clip.gain_db,1,-36,12]
    ];
    for(const [title,key,val,step,min,max] of controls){
      const wrapper=document.createElement("label");wrapper.textContent=title;
      const input=document.createElement("input");input.type="number";
      input.min=min;input.max=max;input.step=step;
      input.value=String(val);input.disabled=working();
      input.setAttribute("aria-label",title+" "+clip.filename);
      if(key==="gain_db"){
        input.addEventListener("input",()=>{
          if(!input.checkValidity())return;
          const value=Number(input.value);
          clipMixerDrafts.set(clip.id,{...currentClipMix(clip),gain_db:value});
          const slider=item.querySelector(".clip-volume-range");
          const out=item.querySelector(".clip-mixer output");
          if(slider)slider.value=String(value);
          if(out)out.textContent=gainText(value);
          syncLiveFx();
        });
      }
      input.addEventListener("change",()=>run(async()=>{
        if(key==="gain_db")ensureLiveAudioPreview();
        if(!input.checkValidity()||!Number.isFinite(Number(input.value)))
          throw Error("Valore audio fuori dai limiti.");
        const value=key==="start_ms"?Math.round(Number(input.value)*1000):Number(input.value);
        if(key==="gain_db"){
          if(value===clip.gain_db)return;
          await edit("audio.clip.mix",{clip_id:clip.id,gain_db:value,
            muted:clip.muted===true});
        }else{
          await edit("audio.update",{clip_id:clip.id,
            start_ms:value,gain_db:clip.gain_db});
        }
      }));
      wrapper.append(input);item.append(wrapper);
    }
    const clipMixer=document.createElement("div");
    clipMixer.className="clip-mixer"+(clip.muted?" is-muted":"");
    const mixLabel=document.createElement("label");mixLabel.textContent="Volume effetto";
    const slider=document.createElement("input");slider.type="range";
    slider.className="clip-volume-range";
    slider.min="-36";slider.max="12";slider.step="1";slider.value=String(clip.gain_db);
    slider.disabled=working();
    slider.setAttribute("aria-label","Regola volume "+clip.filename);
    slider.setAttribute("aria-valuetext",gainText(clip.gain_db));
    const level=document.createElement("output");level.textContent=gainText(clip.gain_db);
    const mixerButtons=document.createElement("div");mixerButtons.className="clip-mixer-controls";
    const clipMute=document.createElement("button");clipMute.type="button";
    clipMute.className="clip-mute";clipMute.disabled=working();
    clipMute.textContent=clip.muted?"Riattiva":"Silenzia";
    clipMute.setAttribute("aria-label",(clip.muted?"Riattiva":"Silenzia")+" effetto "+clip.filename);
    clipMute.setAttribute("aria-pressed",String(!!clip.muted));
    clipMute.addEventListener("click",()=>{
      ensureLiveAudioPreview();
      run(()=>edit("audio.clip.mix",{
        clip_id:clip.id,gain_db:clip.gain_db,muted:!clip.muted
      }));
    });
    const clipReset=document.createElement("button");clipReset.type="button";
    clipReset.className="clip-reset";clipReset.disabled=working();
    clipReset.textContent="↺";
    clipReset.title="Ripristina volume effetto al livello iniziale (-12 dB)";
    clipReset.setAttribute("aria-label","Ripristina volume effetto "+clip.filename);
    clipReset.addEventListener("click",()=>{
      ensureLiveAudioPreview();
      run(async()=>{
        if(clip.gain_db===-12&&!clip.muted)return;
        await edit("audio.clip.mix",{clip_id:clip.id,gain_db:-12,muted:false});
      });
    });
    slider.addEventListener("input",()=>{
      ensureLiveAudioPreview();
      const value=Number(slider.value);
      level.textContent=gainText(value);
      slider.setAttribute("aria-valuetext",gainText(value));
      const number=item.querySelector('input[aria-label^="Volume (dB)"]');
      if(number)number.value=String(value);
      clipMixerDrafts.set(clip.id,{...currentClipMix(clip),gain_db:value});
      syncLiveFx();
    });
    slider.addEventListener("change",()=>run(async()=>{
      const value=Number(slider.value);
      if(value===clip.gain_db)return;
      await edit("audio.clip.mix",{clip_id:clip.id,gain_db:value,muted:!!clip.muted});
    }));
    mixerButtons.append(clipMute,clipReset);
    clipMixer.append(mixLabel,slider,level,mixerButtons);
    item.append(clipMixer);
    if(clip.available){
      const audio=document.createElement("audio");audio.controls=true;audio.preload="none";
      audio.src="/api/audio/"+clip.asset_sha256;
      audio.setAttribute("aria-label","Ascolta "+clip.filename);
      item.append(audio);
    }
    const remove=document.createElement("button");remove.type="button";remove.className="fx-remove";
    remove.textContent="Rimuovi";remove.disabled=working();
    remove.setAttribute("aria-label","Rimuovi effetto "+clip.filename);
    remove.addEventListener("click",()=>run(()=>edit("audio.remove",{clip_id:clip.id})));
    item.append(remove);list.append(item);
  }
  paintFxWaveforms();
}


/* Caption cue timestamps are on the original source ruler. Excluded spans
   remain visible here but will not appear in the rendered output timeline.
   Clicking a cue is a selection/seek only; correction still uses caption.correct. */
/* Cue interaction lives on SOURCE milliseconds. All drags commit only once
   on pointerup, via caption.retime; position previews are never project edits. */
let captionSnapEnabled=true;
function captionSnapTargets(cue){
  const others=(project?.captions||[]).filter(c=>c.id!==cue.id);
  return [
    ...others.flatMap(c=>[c.start_ms,c.end_ms]),
    ...segments().flatMap(seg=>[seg.start_ms,seg.end_ms])
  ];
}
function snapCueTime(value,cue,duration,trackWidth,event){
  if(!captionSnapEnabled||event?.altKey)return {value,snapped:false};
  const threshold=Math.max(25,Math.min(180,Math.round(8/trackWidth*duration)));
  const matches=captionSnapTargets(cue)
    .map(candidate=>({distance:Math.abs(candidate-value),candidate}))
    .filter(match=>match.distance<=threshold)
    .sort((a,b)=>a.distance-b.distance);
  return matches.length?{value:matches[0].candidate,snapped:true}:
    {value,snapped:false};
}
function captionEditBounds(cue,kind){
  const limits=captionMoveLimits(cue);
  if(!limits||!project?.media)return null;
  if(kind==="move")return limits;
  if(kind==="start")return {min:limits.min,max:cue.end_ms-80};
  return {min:cue.start_ms+80,max:project.captions.findIndex(c=>c.id===cue.id)<
    project.captions.length-1?
    project.captions[project.captions.findIndex(c=>c.id===cue.id)+1].start_ms:
    project.media.duration_ms};
}
function drawCaptionTimeline(){
  const track=el("timeline-caption-track"),lane=el("caption-cue-lane");
  lane.replaceChildren();
  const duration=project?.media?.duration_ms||0;
  const cues=project?.captions||[];
  const has=duration>0&&cues.length>0;
  track.hidden=!has;
  el("timeline-surface").classList.toggle("has-captions",has);
  if(!has)return;
  for(const [index,cue] of cues.entries()){
    const mark=document.createElement("button");
    mark.type="button";mark.className="caption-cue-mark";
    mark.dataset.captionId=cue.id;
    mark.setAttribute("aria-pressed","false");
    mark.setAttribute("aria-label","Sottotitolo "+(index+1)+": "+
      cue.text+", da "+msFormat(cue.start_ms,true)+" a "+msFormat(cue.end_ms,true));
    mark.title=cue.text+" · Trascina per spostare; frecce ±0,1 s (⇧ ±0,5 s)";
    mark.textContent=cue.text;
    mark.disabled=working();
    let skipNextClick=false;
    const handles={};
    function paint(start,end,snapped=false){
      mark.style.left=(start/duration*100).toFixed(4)+"%";
      mark.style.width=((end-start)/duration*100).toFixed(4)+"%";
      mark.classList.toggle("snapped",snapped);
      if(handles.start)handles.start.style.left=(start/duration*100).toFixed(4)+"%";
      if(handles.end)handles.end.style.left=(end/duration*100).toFixed(4)+"%";
    }
    function submit(start,end){
      paint(cue.start_ms,cue.end_ms);
      if(start===cue.start_ms&&end===cue.end_ms)return;
      run(()=>submitCaptionTiming(cue,start,end));
    }
    function bindCueDrag(control,kind){
      control.addEventListener("click",event=>{
        event.stopPropagation();
        if(kind==="move"&&!skipNextClick)
          selectEditorItem("caption",cue.id,{seek:true});
      });
      control.addEventListener("keydown",event=>{
        if(!["ArrowLeft","ArrowRight"].includes(event.key)||working())return;
        event.preventDefault();event.stopPropagation();
        const bounds=captionEditBounds(cue,kind);
        if(!bounds||bounds.max<bounds.min)return;
        const delta=(event.key==="ArrowRight"?1:-1)*(event.shiftKey?500:100);
        const original=kind==="end"?cue.end_ms:cue.start_ms;
        const value=Math.max(bounds.min,Math.min(bounds.max,original+delta));
        const start=kind==="start"||kind==="move"?value:cue.start_ms;
        const end=kind==="end"?value:kind==="move"?
          value+cue.end_ms-cue.start_ms:cue.end_ms;
        submit(start,end);
      });
      control.addEventListener("pointerdown",event=>{
        if(event.button!==0||working())return;
        const bounds=captionEditBounds(cue,kind);
        if(!bounds||bounds.max<bounds.min)return;
        event.preventDefault();event.stopPropagation();
        const startX=event.clientX,original=kind==="end"?cue.end_ms:cue.start_ms;
        const rect=el("timeline-track").getBoundingClientRect();
        const width=Math.max(1,rect.width);
        let moved=false,pendingStart=cue.start_ms,pendingEnd=cue.end_ms;
        control.setPointerCapture(event.pointerId);
        control.classList.add("dragging");
        const move=ev=>{
          if(Math.abs(ev.clientX-startX)<4&&!moved)return;
          moved=true;
          const delta=Math.round((ev.clientX-startX)/width*duration/10)*10;
          const raw=original+delta;
          const threshold=Math.max(25,Math.min(180,8/width*duration));
          let value=Math.max(bounds.min,Math.min(bounds.max,raw));
          let snapped=false;
          if(kind==="move"){
            // Snap whichever moving edge is closest, preserving cue duration.
            const length=cue.end_ms-cue.start_ms;
            const candidates=[
              snapCueTime(value,cue,duration,width,ev),
              snapCueTime(value+length,cue,duration,width,ev)
            ].map((result,i)=>({...result,start:result.value-(i?length:0)}))
              .filter(result=>result.snapped&&result.start>=bounds.min&&result.start<=bounds.max);
            if(candidates.length){
              candidates.sort((a,b)=>Math.abs(a.start-value)-Math.abs(b.start-value));
              value=candidates[0].start;snapped=true;
            }
            pendingStart=value;pendingEnd=value+length;
          }else{
            const result=snapCueTime(value,cue,duration,width,ev);
            if(result.snapped&&result.value>=bounds.min&&result.value<=bounds.max){
              value=result.value;snapped=true;
            }
            if(kind==="start")pendingStart=value;
            else pendingEnd=value;
          }
          paint(pendingStart,pendingEnd,snapped);
          control.title=snapped?"Agganciato a un confine":
            "Sorgente "+msFormat(kind==="end"?pendingEnd:pendingStart,true);
        };
        const cleanup=ev=>{
          control.removeEventListener("pointermove",move);
          control.removeEventListener("pointerup",finish);
          control.removeEventListener("pointercancel",cancel);
          if(control.hasPointerCapture(ev.pointerId))control.releasePointerCapture(ev.pointerId);
          control.classList.remove("dragging");
        };
        const finish=ev=>{
          cleanup(ev);
          if(moved){
            skipNextClick=true;
            submit(pendingStart,pendingEnd);
            window.setTimeout(()=>{skipNextClick=false;},0);
          }
        };
        const cancel=ev=>{cleanup(ev);paint(cue.start_ms,cue.end_ms);};
        control.addEventListener("pointermove",move);
        control.addEventListener("pointerup",finish);
        control.addEventListener("pointercancel",cancel);
      });
    }
    bindCueDrag(mark,"move");
    lane.append(mark);
    for(const kind of ["start","end"]){
      const handle=document.createElement("button");
      handle.type="button";handle.className="caption-edge-handle "+kind;
      handle.dataset.captionId=cue.id;
      handle.disabled=working();
      handle.setAttribute("aria-label",
        (kind==="start"?"Accorcia o allunga l’inizio":"Accorcia o allunga la fine")+
        " del sottotitolo "+(index+1));
      handle.title=(kind==="start"?"Inizio":"Fine")+
        " · trascina o usa ← → ±100 ms, ⇧ ±500 ms";
      bindCueDrag(handle,kind);
      handles[kind]=handle;
      lane.append(handle);
    }
    paint(cue.start_ms,cue.end_ms);
  }
}

function drawTimeline(){
  const parts=el("timeline-regions");parts.replaceChildren();if(!project?.media)return;
  const duration=project.media.duration_ms,keep=segments();
  parts.classList.toggle("unanalysed", !project.plan);
  if(!project.plan) return;
  for(const s of keep){
    const index=keep.indexOf(s),prev=index?keep[index-1]:null,next=keep[index+1]||null;
    const div=document.createElement("div");div.className="timeline-region";
    div.dataset.segmentId=s.id;
    const choose=document.createElement("button");
    choose.type="button";choose.className="region-select";
    choose.setAttribute("aria-pressed","false");
    choose.setAttribute("aria-label","Seleziona intervallo "+(index+1)+", "+
      msFormat(s.start_ms,true)+" – "+msFormat(s.end_ms,true));
    choose.addEventListener("click",event=>{
      // Mouse: keep the original ruler scrub position. Keyboard: seek to start.
      const keyboard=event.detail===0;
      if(keyboard)event.stopPropagation();
      selectEditorItem("segment",s.id,{seek:keyboard});
    });
    div.append(choose);
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
  el("timeline-source-clock").textContent=duration?
    "Sorgente "+rulerClock(sourceAt):"Sorgente —";
  el("timeline-track").setAttribute("aria-label","Timeline originale, posizione "+
    msFormat(sourceAt,true)+". Frecce ±5 secondi. Maniglie per regolare i tagli.");
  el("play-pause").textContent=v.paused?"▶":"Ⅱ";
  el("play-pause").setAttribute("aria-label",v.paused?"Riproduci":"Pausa");
  el("video-workspace").classList.toggle("playing",!v.paused);
  updateTranscriptActive();
}

/* Presentation state for desktop workspace. Video edits still flow only through
   typed project commands; the current view and dock height are not project edits. */
const WORKSPACE_LABELS = {
  media: ["Media del progetto","Importa e gestisci il video originale.","Revisione tagli"],
  cuts: ["Tagli AI","Scegli il ritmo, analizza le pause e rivedi gli intervalli.","Revisione tagli"],
  transcript: ["Trascrizione","Trascrivi localmente e rivedi le parole riconosciute.","Trascrizione"],
  captions: ["Sottotitoli","Genera, correggi e posiziona i sottotitoli nella preview.","Sottotitoli"],
  audio: ["Audio e riser","Importa effetti, spostali sulla timeline e regola il volume.","Effetti audio"],
  settings: ["Progetto e impostazioni","Gestisci autosalvataggio, cronologia e file di progetto.","Revisione tagli"]
};
function setWorkspace(name, persist=true){
  if(!Object.hasOwn(WORKSPACE_LABELS,name))name="media";
  const [title,description,inspectorTitle]=WORKSPACE_LABELS[name];
  el("app").dataset.workspace=name;
  el("workspace-context-title").textContent=title;
  el("workspace-context-description").textContent=description;
  document.querySelector(".inspector-head h2").textContent=inspectorTitle;
  for(const button of document.querySelectorAll("[data-workspace-nav]")){
    const active=button.dataset.workspaceNav===name;
    button.classList.toggle("active",active);
    if(active)button.setAttribute("aria-current","page");
    else button.removeAttribute("aria-current");
  }
  if(name==="transcript"||name==="captions")tab("transcript");
  else tab("cuts");
  renderWorkspaceLibraries();
  if(persist){try{localStorage.setItem("pausio-studio-workspace",name);}catch(_error){}}
}
function syncDesktopCommands(){
  for(const [target,source] of [
    ["desktop-undo-action","undo-action"],
    ["desktop-redo-action","redo-action"],
    ["desktop-approve-action","approve-action"]]){
    el(target).disabled=el(source).disabled;
  }
  const canDownload=!el("download-action").hidden;
  el("desktop-export-action").disabled=!canDownload&&el("export-action").disabled;
  el("desktop-export-action").textContent=canDownload?"Scarica MP4":"Esporta MP4";
}
function initializeDesktopWorkspace(){
  let chosen="media";
  try{chosen=localStorage.getItem("pausio-studio-workspace")||"media";}catch(_error){}
  setWorkspace(chosen,false);
  for(const button of document.querySelectorAll("[data-workspace-nav]")){
    button.addEventListener("click",()=>setWorkspace(button.dataset.workspaceNav));
  }
  el("desktop-undo-action").addEventListener("click",()=>el("undo-action").click());
  el("desktop-redo-action").addEventListener("click",()=>el("redo-action").click());
  el("desktop-approve-action").addEventListener("click",()=>el("approve-action").click());
  el("workspace-audio-import").addEventListener("click",()=>el("fx-input").click());
  el("workspace-caption-search").addEventListener("input",()=>{
    renderWorkspaceLibraries();syncEditorSelection();
  });
  el("workspace-caption-transcribe").addEventListener("click",()=>setWorkspace("transcript"));
  el("transcript-search").addEventListener("input",drawTranscript);
  el("transcript-search").addEventListener("keydown",event=>{
    if(event.key==="ArrowDown"||event.key==="ArrowUp"){
      event.preventDefault();navigateTranscript(event.key==="ArrowDown"?1:-1);
    }
  });
  el("transcript-previous").addEventListener("click",()=>navigateTranscript(-1));
  el("transcript-next").addEventListener("click",()=>navigateTranscript(1));
  try{captionSnapEnabled=localStorage.getItem("pausio-caption-snap")!=="off";}catch(_error){}
  el("timeline-snap").checked=captionSnapEnabled;
  el("timeline-snap").addEventListener("change",event=>{
    captionSnapEnabled=event.target.checked;
    try{localStorage.setItem("pausio-caption-snap",captionSnapEnabled?"on":"off");}catch(_error){}
  });
  el("selection-clear").addEventListener("click",()=>{editorSelection=null;syncEditorSelection();});
  el("selection-goto").addEventListener("click",focusEditorSelection);
  el("desktop-export-action").addEventListener("click",()=>{
    if(!el("download-action").hidden)el("download-action").click();
    else el("export-action").click();
  });
  const dock=el("editor-dock"),handle=el("dock-resizer");
  const min=210,max=440;
  function applyHeight(value,save=true){
    const upper=Math.max(min,Math.min(max,window.innerHeight-350));
    const height=Math.round(Math.max(min,Math.min(upper,value)));
    dock.style.setProperty("--dock-height",height+"px");
    handle.setAttribute("aria-valuenow",String(height));
    handle.setAttribute("aria-valuemax",String(upper));
    if(save){try{localStorage.setItem("pausio-studio-dock-height",String(height));}catch(_error){}}
    resizeTimeline();
  }
  let initial=285;
  try{initial=Number(localStorage.getItem("pausio-studio-dock-height"))||285;}catch(_error){}
  applyHeight(initial,false);
  let drag=null;
  handle.addEventListener("pointerdown",event=>{
    if(event.button!==0||window.matchMedia("(max-width: 1000px)").matches)return;
    drag={y:event.clientY,height:dock.getBoundingClientRect().height};
    handle.setPointerCapture(event.pointerId);
    event.preventDefault();
  });
  handle.addEventListener("pointermove",event=>{
    if(!drag)return;
    applyHeight(drag.height+drag.y-event.clientY,false);
  });
  handle.addEventListener("pointerup",event=>{
    if(!drag)return;
    drag=null;
    if(handle.hasPointerCapture(event.pointerId))handle.releasePointerCapture(event.pointerId);
    applyHeight(dock.getBoundingClientRect().height);
  });
  handle.addEventListener("pointercancel",()=>{drag=null;});
  handle.addEventListener("keydown",event=>{
    if(!["ArrowUp","ArrowDown","Home"].includes(event.key))return;
    event.preventDefault();
    const current=dock.getBoundingClientRect().height;
    applyHeight(event.key==="Home"?285:current+(event.key==="ArrowUp"?20:-20));
  });
  window.addEventListener("resize",()=>{
    applyHeight(dock.getBoundingClientRect().height,false);
    renderWorkspaceLibraries();
    syncEditorSelection();
  });
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
  for(const id of [...liveFxPlayers.keys()])disposeLiveFx(id);
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
  v.pause();pauseLiveFx();mode=chosen;
  syncVoicePlayback();
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
  if(v.paused||v.ended)return;
  if(mode==="edited")followEdits();
  syncLiveFx();
  transport();
  if(!v.paused&&(mode==="edited"||(mode!=="rendered"&&fxMonitoringEnabled&&
       (project?.audio_clips||[]).length))){
    simulationFrame=requestAnimationFrame(simulationTick);
  }
}
function syncSimulationLoop(){
  const active=!v.paused&&!v.ended&&(mode==="edited"||
    (mode!=="rendered"&&fxMonitoringEnabled&&(project?.audio_clips||[]).length));
  if(active){
    if(simulationFrame===null)simulationFrame=requestAnimationFrame(simulationTick);
  }else if(simulationFrame!==null){
    cancelAnimationFrame(simulationFrame);
    simulationFrame=null;
  }
  if(!active)pauseLiveFx();
}
function play(){
  if(!project?.media)return;
  if(!v.paused){v.pause();return;}
  if(mode==="edited"&&segments().length){
    v.currentTime=nextSimulatedSourceTime(Math.round(v.currentTime*1000))/1000;
  }else if(v.ended)v.currentTime=0;
  unlockFxAudio();
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
function importAudio(file){
  if(!file)return;
  if(!project?.media)return toast("Importa prima un video.","error");
  if(working())return toast("Completa prima l'operazione in corso.","error");
  const ext=(file.name.split(".").pop()||"").toLowerCase();
  if(!["mp3","wav","m4a","aac","flac","ogg"].includes(ext))
    return toast("Scegli un audio MP3, WAV, M4A, AAC, FLAC o OGG.","error");
  if(!file.size||file.size>60*1024*1024)
    return toast("Audio vuoto oppure superiore a 60 MB.","error");
  const sourceTime=mode==="rendered"?sourceFromOutput((v.currentTime||0)*1000):(v.currentTime||0)*1000;
  const anchor=mode==="rendered"?(v.currentTime||0)*1000:project.plan?outputTime(sourceTime):sourceTime;
  uploading=true;el("job-banner").hidden=false;el("job-message").textContent="Importazione FX · 0%";
  const xhr=new XMLHttpRequest();xhr.open("POST","/api/audio/import");
  xhr.setRequestHeader("Content-Type","application/octet-stream");
  xhr.setRequestHeader("X-Pausio-Client","studio");
  xhr.setRequestHeader("X-Pausio-Revision",String(project.project_revision));
  xhr.setRequestHeader("X-Pausio-Start-Ms",String(Math.max(0,Math.min(project.media.duration_ms-1,
    Math.round(anchor)))));
  xhr.setRequestHeader("X-Filename",encodeURIComponent(file.name));
  xhr.upload.addEventListener("progress",event=>{
    if(event.lengthComputable)el("job-message").textContent=
      "Importazione FX · "+Math.round(event.loaded/event.total*100)+"%";
  });
  xhr.addEventListener("load",()=>{
    uploading=false;el("fx-input").value="";
    let result={};try{result=JSON.parse(xhr.responseText);}catch{}
    if(xhr.status===200){
      update(result);toast("Audio importato sul Mac. Regola posizione e volume nella traccia FX.");
    }else{
      el("job-banner").hidden=true;
      toast(result.error||"Importazione audio non riuscita.","error");
      refresh().catch(()=>{});
    }
  });
  xhr.addEventListener("error",()=>{uploading=false;el("job-banner").hidden=true;
    toast("Connessione al server locale interrotta.","error");refresh().catch(()=>{});});
  xhr.send(file);
}
el("fx-monitor-toggle").addEventListener("click",()=>{
  if(mode==="rendered")return;
  fxMonitoringEnabled=!fxMonitoringEnabled;
  if(fxMonitoringEnabled)unlockFxAudio();else pauseLiveFx();
  updateFxMonitorUI();syncLiveFx();syncSimulationLoop();
});
el("fx-import").addEventListener("click",()=>el("fx-input").click());
el("fx-input").addEventListener("change",()=>importAudio(el("fx-input").files?.[0]));

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
      input.type==="color"?input.value.toUpperCase():
      input.tagName==="SELECT"?input.value:Number(input.value));
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
v.addEventListener("timeupdate",()=>{followEdits();syncLiveFx();transport();});
v.addEventListener("play",()=>{unlockFxAudio();followEdits();syncLiveFx();syncSimulationLoop();transport();});
v.addEventListener("pause",()=>{pauseLiveFx();syncSimulationLoop();transport();});
v.addEventListener("ended",()=>{pauseLiveFx();syncSimulationLoop();transport();});
v.addEventListener("waiting",pauseLiveFx);
v.addEventListener("stalled",pauseLiveFx);
v.addEventListener("playing",()=>{syncLiveFx();syncSimulationLoop();});
v.addEventListener("seeking",pauseLiveFx);
v.addEventListener("seeked",()=>{followEdits();syncLiveFx();transport();});
v.addEventListener("ratechange",syncLiveFx);
v.addEventListener("volumechange",syncLiveFx);
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
/* The ruler and every media lane use SOURCE time. The playback counter may
   show edited/output time; zoom and ruler must never silently change basis. */
const TIMELINE_ZOOMS=[1,2,4,8];
function timelineSourceMs(){
  const t=Math.max(0,(v.currentTime||0)*1000);
  return mode==="rendered"?sourceFromOutput(t):t;
}
function rulerClock(ms){
  const total=Math.max(0,Math.round(ms));
  const hh=Math.floor(total/3600000),mm=Math.floor(total%3600000/60000),
    ss=Math.floor(total%60000/1000),tenths=Math.floor(total%1000/100);
  if(hh)return String(hh).padStart(2,"0")+":"+
    String(mm).padStart(2,"0")+":"+String(ss).padStart(2,"0");
  return String(mm).padStart(2,"0")+":"+String(ss).padStart(2,"0")+
    (project?.media?.duration_ms<60000?"."+tenths:"");
}
function drawTimeRuler(){
  const parent=el("timeline-ruler-content"),duration=project?.media?.duration_ms||0;
  parent.replaceChildren();
  if(!duration)return;
  const width=Math.max(200,el("timeline-track").getBoundingClientRect().width);
  const desiredMs=duration*92/width;
  const steps=[100,200,250,500,1000,2000,2500,5000,10000,15000,
    30000,60000,120000,300000,600000,900000,1800000,3600000];
  const step=steps.find(x=>x>=desiredMs)||3600000*Math.ceil(desiredMs/3600000);
  const drawTick=(ms,isEnd=false)=>{
    const tick=document.createElement("span");
    tick.className="timeline-time-tick";
    tick.style.left=(ms/duration*100)+"%";
    if(ms===0)tick.classList.add("first");
    if(isEnd)tick.classList.add("last");
    tick.textContent=rulerClock(ms);
    parent.append(tick);
  };
  drawTick(0);
  for(let ms=step;ms<duration;ms+=step)drawTick(ms);
  if(duration>=step*.7)drawTick(duration,true);
}
function timelineLocate(sourceMs=timelineSourceMs(),position=.5){
  if(!project?.media)return;
  const surface=el("timeline-surface"),track=el("timeline-track");
  const ratio=Math.max(0,Math.min(1,sourceMs/project.media.duration_ms));
  const x=8+ratio*track.getBoundingClientRect().width;
  surface.scrollLeft=Math.max(0,Math.min(surface.scrollWidth-surface.clientWidth,
    x-surface.clientWidth*Math.max(0,Math.min(1,position))));
  el("timeline-ruler").scrollLeft=surface.scrollLeft;
}
function resizeTimeline(anchorMs=null){
  const surface=el("timeline-surface"),track=el("timeline-track");
  if(!surface||!track)return;
  const oldWidth=Math.max(1,track.getBoundingClientRect().width);
  const oldScroll=surface.scrollLeft;
  const anchor=anchorMs!==null&&project?.media?
    Math.max(0,Math.min(1,anchorMs/project.media.duration_ms)):null;
  const oldAnchorX=anchor===null?null:8+oldWidth*anchor-oldScroll;
  const width=Math.max(200,(surface.clientWidth-16)*timelineZoom);
  track.style.width=width+"px";
  el("timeline-ruler-content").style.width=width+"px";
  if(anchor!==null){
    // Keep the same source timestamp under the same screen x when possible.
    // When the playhead is off-screen, center it instead of preserving an
    // invisible anchor. This also works through a rendered output preview.
    const viewportX=oldAnchorX>=0&&oldAnchorX<=surface.clientWidth?
      oldAnchorX:surface.clientWidth/2;
    surface.scrollLeft=Math.max(0,8+width*anchor-viewportX);
  }else{
    const oldRange=Math.max(1,oldWidth+16-surface.clientWidth);
    const newRange=Math.max(0,width+16-surface.clientWidth);
    surface.scrollLeft=Math.max(0,oldScroll/oldRange*newRange);
  }
  el("timeline-ruler").scrollLeft=surface.scrollLeft;
  drawTimeRuler();paintWaveform();paintFxWaveforms();
}
function setTimelineZoom(value){
  const next=TIMELINE_ZOOMS.includes(Number(value))?Number(value):1;
  const anchor=project?.media?timelineSourceMs():null;
  timelineZoom=next;
  el("timeline-zoom").value=String(next);
  el("timeline-zoom-out").disabled=next===TIMELINE_ZOOMS[0];
  el("timeline-zoom-in").disabled=next===TIMELINE_ZOOMS.at(-1);
  resizeTimeline(anchor);
}
el("timeline-zoom").addEventListener("change",event=>{
  setTimelineZoom(event.target.value);
});
el("timeline-zoom-out").addEventListener("click",()=>{
  setTimelineZoom(TIMELINE_ZOOMS[Math.max(0,TIMELINE_ZOOMS.indexOf(timelineZoom)-1)]);
});
el("timeline-zoom-in").addEventListener("click",()=>{
  setTimelineZoom(TIMELINE_ZOOMS[Math.min(TIMELINE_ZOOMS.length-1,
    TIMELINE_ZOOMS.indexOf(timelineZoom)+1)]);
});
el("timeline-center-playhead").addEventListener("click",()=>timelineLocate());
el("timeline-surface").addEventListener("scroll",()=>{
  el("timeline-ruler").scrollLeft=el("timeline-surface").scrollLeft;
});
/* Preserve the original single-column mobile audio flow. Reparent the same
   live FX controls; never duplicate DOM controls or listeners. */
function syncFxPanelOrder(){
  const fx=el("fx-panel"),inspector=document.querySelector(".inspector");
  const small=window.matchMedia("(max-width: 1000px)").matches;
  if(small && fx.parentElement!==el("app"))el("file-input").before(fx);
  else if(!small && fx.parentElement!==inspector)
    inspector.querySelector(".inspector-bottom").before(fx);
}
/* Keep visual, keyboard and screen-reader navigation order consistent. */
function syncTimelineOrder(){
  const timeline=document.querySelector(".timeline-panel");
  const workbench=document.querySelector(".workbench");
  const inspector=document.querySelector(".inspector");
  if(window.matchMedia("(max-width: 650px)").matches){
    if(timeline.parentElement!==workbench || timeline.nextElementSibling!==inspector)
      inspector.before(timeline);
  }else{
    const dock=el("editor-dock"),handle=el("dock-resizer");
    if(timeline.parentElement!==dock || timeline.previousElementSibling!==handle)
      handle.after(timeline);
  }
}
window.addEventListener("resize",()=>{
  syncTimelineOrder();
  syncFxPanelOrder();
  resizeTimeline();
});
syncTimelineOrder();
syncFxPanelOrder();
resizeTimeline();
setTimelineZoom(timelineZoom);
initializeDesktopWorkspace();

