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
