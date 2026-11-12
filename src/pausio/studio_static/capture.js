/* Pausio Capture: mobile/desktop vertical recording, no analytics or cloud services. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const els = {
    live: $("camera-video"), playback: $("result-video"), placeholder: $("camera-placeholder"),
    frame: $("camera-frame"), prompter: $("prompter"), scroll: $("prompter-scroll"),
    text: $("prompter-text"), status: $("status"), state: $("capture-state"),
    timer: $("timer"), clock: $("timer-text"), format: $("format-pill"),
    camera: $("activate-camera"), start: $("record-start"), stop: $("record-stop"),
    next: $("new-take"), flip: $("switch-camera"), pause: $("toggle-scroll"),
    countdown: $("countdown"), panel: $("download-panel"), download: $("download-video"),
    share: $("share-video"), details: $("file-details"), script: $("script-input"),
    speed: $("speed"), font: $("font-size"), position: $("prompter-position"),
    autoplay: $("auto-scroll"),
    portrait: $("portrait-canvas"), videoDevice: $("video-device"), audioDevice: $("audio-device"),
    quality: $("capture-quality"), panX: $("crop-x"), panY: $("crop-y"), zoom: $("crop-zoom"),
    resetCrop: $("crop-reset"), meter: $("audio-level"), meterFill: $("audio-level-fill"),
    meterValue: $("audio-level-value"), sourceInfo: $("capture-tech-info"),
    openStudio: $("open-in-studio"),
    rehearse: $("rehearsal-toggle"), rehearsalRestart: $("rehearsal-restart"),
    rehearsalHint: $("rehearsal-hint"), rehearsalHintText: $("rehearsal-hint-text")
  };
  const STORE_KEY = "pausio-mobile-capture-v1";
  let stream = null, recorder = null, chunks = [], output = null, blobUrl = null;
  let outputName = "", mode = "idle", facing = "user", raf = 0, lastFrame = 0;
  let startedAt = 0, pausedScroll = false, countdownId = 0;
  let savedAfterRecording = false, recordedMime = "";
  // A rehearsal is strictly presentation state: no MediaRecorder, no take,
  // no microphone or camera permission required.
  let rehearsalState = "stopped", rehearsalElapsedMs = 0;
  let compositionActive = false, composeRaf = 0, lastPaint = 0, portraitStream = null;
  let meterRaf = 0, audioContext = null, audioAnalyser = null, meterSource = null;
  let inputWidth = 0, inputHeight = 0, recordedDimensions = null;
  const isLocalStudio = location.hostname === "127.0.0.1";

  function notice(message, error = false) {
    els.status.textContent = message;
    els.status.classList.toggle("error", error);
  }
  function setMode(next) {
    mode = next;
    els.camera.hidden = next !== "idle" && next !== "error";
    els.start.hidden = next !== "preview";
    els.stop.hidden = next !== "recording";
    els.next.hidden = next !== "finished";
    els.flip.hidden = next !== "preview";
    els.pause.hidden = next !== "recording";
    els.panel.hidden = next !== "finished";
    els.placeholder.hidden = next !== "idle" && next !== "error" ||
      rehearsalState !== "stopped";
    els.live.hidden = next === "finished" || next === "idle" || next === "error";
    els.portrait.hidden = !compositionActive ||
      next === "finished" || next === "idle" || next === "error";
    els.playback.hidden = next !== "finished";
    els.prompter.hidden = next === "finished" || next === "error" ||
      (next === "idle" && rehearsalState === "stopped");
    els.timer.classList.toggle("live", next === "recording");
    els.state.textContent = {idle:"PRONTO", error:"ERRORE", preview:"CAMERA ATTIVA",
      countdown:"PREPARATI", recording:"REC", stopping:"SALVATAGGIO", finished:"TAKE PRONTO"}[next] || "PRONTO";
    const locked = ["countdown","recording","stopping"].includes(next);
    for (const el of [els.script,els.speed,els.font,els.position,els.autoplay,
      els.videoDevice,els.audioDevice,els.quality,els.panX,els.panY,els.zoom,els.resetCrop])
      el.disabled = locked;
    els.flip.hidden = next !== "preview";
    els.pause.textContent = pausedScroll ? "▶" : "Ⅱ";
    els.pause.setAttribute("aria-label", pausedScroll ? "Riprendi scorrimento" : "Pausa scorrimento");
    els.openStudio.hidden = next !== "finished" || !isLocalStudio;
    syncRehearsalControls();
  }
  function prefs() {
    try {
      const data = JSON.parse(localStorage.getItem(STORE_KEY) || "null");
      if (!data || data.version !== 1) return;
      if (typeof data.script === "string") els.script.value = data.script.slice(0, 15000);
      if (Number.isFinite(data.speed)) els.speed.value = Math.max(50, Math.min(220, data.speed));
      if (Number.isFinite(data.font)) els.font.value = Math.max(20, Math.min(44, data.font));
      if (["top","middle"].includes(data.position)) els.position.value = data.position;
      if (typeof data.autoplay === "boolean") els.autoplay.checked = data.autoplay;
      if ([540,720,1080].includes(data.quality)) els.quality.value = String(data.quality);
      for (const [el,key,min,max] of [
        [els.panX,"panX",0,100],[els.panY,"panY",0,100],[els.zoom,"zoom",100,180]
      ]) if (Number.isFinite(data[key])) el.value = Math.max(min,Math.min(max,data[key]));
    } catch (_) { /* Storage unavailable in private browsing. */ }
  }
  function remember() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({version:1,
        script:els.script.value.slice(0,15000), speed:+els.speed.value, font:+els.font.value,
        position:els.position.value, autoplay:els.autoplay.checked,
        quality:+els.quality.value,panX:+els.panX.value,panY:+els.panY.value,
        zoom:+els.zoom.value}));
    } catch (_) { /* Capture and downloads do not require localStorage. */ }
  }
  function refreshPrompter() {
    const nextText=els.script.value.trim()||"Scrivi uno script nelle impostazioni.";
    // Updating the speed slider must NOT replace the text node and send the
    // active rehearsal back to the start on some browsers.
    if(els.text.textContent!==nextText){
      els.text.textContent=nextText;
      if(rehearsalState!=="stopped"){
        els.scroll.scrollTop=0;
        rehearsalElapsedMs=0;
        lastFrame=0;
        els.clock.textContent="00:00";
      }
    }
    els.prompter.style.setProperty("--font-size", els.font.value + "px");
    els.prompter.classList.toggle("middle", els.position.value === "middle");
    $("speed-value").textContent = els.speed.value + " parole/min";
    $("font-value").textContent = els.font.value + " px";
    syncRehearsalControls();
  }
  function syncRehearsalControls() {
    const available=mode==="idle"||mode==="preview";
    const practicing=available&&rehearsalState!=="stopped";
    const playing=practicing&&rehearsalState==="playing";
    els.rehearse.hidden=!available;
    els.rehearse.disabled=!els.script.value.trim();
    els.rehearse.setAttribute("aria-pressed",String(playing));
    els.rehearse.textContent=playing?"Ⅱ Pausa prova":
      rehearsalState==="paused"?"▶ Riprendi prova":"▶ Prova gobbo";
    els.rehearse.title=playing?"Metti in pausa la prova, senza registrare":
      "Prova lo scorrimento del gobbo senza avviare la registrazione";
    els.rehearsalRestart.hidden=!practicing;
    els.rehearsalHint.hidden=!practicing;
    els.rehearsalHintText.textContent=(playing?"PROVA GOBBO":"PROVA IN PAUSA")+
      " · "+els.speed.value+" parole/min · Nessun video registrato";
    els.timer.classList.toggle("rehearsal-live",playing);
    els.frame.classList.toggle("rehearsing",practicing);
    // The original webcam remains available if already activated.
    els.placeholder.hidden=practicing||(mode!=="idle"&&mode!=="error");
    els.prompter.hidden=mode==="finished"||mode==="error"||
      (mode==="idle"&&!practicing);
    if(practicing)els.state.textContent=playing?"PROVA GOBBO":"PROVA IN PAUSA";
    else if(available)els.state.textContent=mode==="preview"?"CAMERA ATTIVA":"PRONTO";
  }
  function stopAnimation(){cancelAnimationFrame(raf);raf=0;lastFrame=0;}
  function tick(now) {
    const rehearsing=rehearsalState==="playing"&&
      (mode==="idle"||mode==="preview");
    if(mode!=="recording"&&!rehearsing){stopAnimation();return;}
    if(mode==="recording"){
      const elapsed=Math.max(0,Math.floor((now-startedAt)/1000));
      els.clock.textContent=String(Math.floor(elapsed/60)).padStart(2,"0")+
        ":"+String(elapsed%60).padStart(2,"0");
    }else if(rehearsing){
      if(lastFrame)rehearsalElapsedMs+=Math.min(Math.max(now-lastFrame,0),150);
      const seconds=Math.floor(rehearsalElapsedMs/1000);
      els.clock.textContent=String(Math.floor(seconds/60)).padStart(2,"0")+
        ":"+String(seconds%60).padStart(2,"0");
    }
    if(lastFrame&&
      (rehearsing||(mode==="recording"&&!pausedScroll&&els.autoplay.checked))){
      const fontPx=+els.font.value;
      const charsPerLine=Math.max(10,els.scroll.clientWidth/(fontPx*.54));
      const wordsPerLine=Math.max(1.6,charsPerLine/6);
      const pxPerSecond=((+els.speed.value/60)/wordsPerLine)*fontPx*1.4;
      els.scroll.scrollTop+=Math.min(Math.max(now-lastFrame,0)/1000,.15)*pxPerSecond;
    }
    lastFrame=now;
    raf=requestAnimationFrame(tick);
  }
  function resetScroll(){
    stopAnimation();
    rehearsalState="stopped";
    rehearsalElapsedMs=0;
    els.scroll.scrollTop=0;
    pausedScroll=false;
    els.clock.textContent="00:00";
    syncRehearsalControls();
  }
  function toggleRehearsal(){
    if(!["idle","preview"].includes(mode)||!els.script.value.trim())return;
    if(rehearsalState==="playing"){
      rehearsalState="paused";
      stopAnimation();
      syncRehearsalControls();
      notice("Prova in pausa. Regola la velocità e premi Riprendi prova.");
      return;
    }
    if(rehearsalState==="stopped"){
      els.scroll.scrollTop=0;
      rehearsalElapsedMs=0;
      els.clock.textContent="00:00";
    }
    stopAnimation(); // Resume without counting hidden-tab or paused time.
    rehearsalState="playing";
    syncRehearsalControls();
    notice("Prova del gobbo: nessun video viene registrato. Regola la velocità in diretta.");
    raf=requestAnimationFrame(tick);
  }
  function restartRehearsal(){
    if(!["idle","preview"].includes(mode)||!els.script.value.trim())return;
    stopAnimation();
    els.scroll.scrollTop=0;
    rehearsalElapsedMs=0;
    els.clock.textContent="00:00";
    rehearsalState="playing";
    syncRehearsalControls();
    notice("Gobbo ripartito dall'inizio, senza registrare.");
    raf=requestAnimationFrame(tick);
  }
  function supportedMime() {
    if (!window.MediaRecorder) return "";
    const candidates = [
      'video/mp4;codecs="avc1.42E01E,mp4a.40.2"', "video/mp4",
      "video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"
    ];
    return candidates.find(type => MediaRecorder.isTypeSupported(type)) || "";
  }
  const captureQuality = () => Number(els.quality.value) || 720;
  const cameraDimensions = () => {
    const settings = stream?.getVideoTracks()[0]?.getSettings?.() || {};
    return {width:els.live.videoWidth || settings.width || 0,
      height:els.live.videoHeight || settings.height || 0};
  };
  function updateFramingLabels() {
    $("crop-x-value").textContent=els.panX.value+"%";
    $("crop-y-value").textContent=els.panY.value+"%";
    $("crop-zoom-value").textContent=els.zoom.value+"%";
  }
  function stopCompositor() {
    cancelAnimationFrame(composeRaf);composeRaf=0;lastPaint=0;
    if(portraitStream) for(const track of portraitStream.getTracks())track.stop();
    portraitStream=null;compositionActive=false;
    els.portrait.hidden=true;
    els.frame.classList.remove("is-composing");
  }
  function drawPortraitFrame() {
    if(!compositionActive||els.live.readyState<2)return;
    const {width,height}=cameraDimensions();
    if(!width||!height)return;
    // Scale to a source crop with an exact 9:16 aspect ratio. This matches
    // the real MediaRecorder frames: CSS object-fit alone does NOT crop output.
    const ratio=9/16, zoom=Number(els.zoom.value)/100;
    const boxWidth=Math.min(width,height*ratio)/zoom;
    const boxHeight=boxWidth/ratio;
    const left=(width-boxWidth)*(Number(els.panX.value)/100);
    const top=(height-boxHeight)*(Number(els.panY.value)/100);
    const context=els.portrait.getContext("2d",{alpha:false});
    if(context)context.drawImage(els.live,left,top,boxWidth,boxHeight,
      0,0,els.portrait.width,els.portrait.height);
  }
  function renderPortraitLoop(now) {
    if(!compositionActive||!stream)return;
    if(!lastPaint||now-lastPaint>=32){
      drawPortraitFrame();
      lastPaint=now;
    }
    composeRaf=requestAnimationFrame(renderPortraitLoop);
  }
  function configureComposition() {
    stopCompositor();
    if(!stream)return;
    updateFramingLabels();
    const {width,height}=cameraDimensions();
    inputWidth=width;inputHeight=height;
    const verticalNative=width>0&&height>0&&
      Math.abs(width/height-9/16)<0.001 &&
      !window.matchMedia("(pointer: fine) and (min-width: 860px)").matches &&
      Number(els.panX.value)===50&&Number(els.panY.value)===50&&
      Number(els.zoom.value)===100;
    compositionActive=!verticalNative;
    if(compositionActive){
      if(typeof els.portrait.captureStream!=="function")
        throw Error("Il browser non supporta il video verticale da canvas. Usa Chrome o Safari aggiornato.");
      const quality=captureQuality();
      els.portrait.width=quality;els.portrait.height=Math.round(quality*16/9);
      els.portrait.hidden=false;
      els.frame.classList.add("is-composing");
      els.portrait.classList.toggle("mirrored",facing==="user");
      drawPortraitFrame();
      composeRaf=requestAnimationFrame(renderPortraitLoop);
    }
    const outWidth=compositionActive?els.portrait.width:width;
    const outHeight=compositionActive?els.portrait.height:height;
    recordedDimensions={width:outWidth,height:outHeight};
    els.format.textContent=outWidth+"×"+outHeight+" · 9:16";
    els.sourceInfo.textContent=width+"×"+height+
      (compositionActive?" dalla webcam → "+outWidth+"×"+outHeight+
        " · crop 9:16. L'anteprima mostra esattamente il ritaglio registrato.":
        " · registrazione verticale nativa, senza ricodifica del ritaglio.");
  }
  async function refreshDeviceChoices() {
    if(!navigator.mediaDevices?.enumerateDevices)return;
    let devices;
    try{devices=await navigator.mediaDevices.enumerateDevices();}catch(_error){return;}
    const maps=[
      [els.videoDevice,"videoinput","Fotocamera automatica","Webcam"],
      [els.audioDevice,"audioinput","Microfono predefinito","Microfono"]
    ];
    for(const [select,kind,auto,label] of maps){
      const chosen=select.value;
      select.replaceChildren(new Option(auto,""));
      const options=devices.filter(d=>d.kind===kind);
      for(const [index,device] of options.entries()){
        if(!device.deviceId)continue;
        select.add(new Option(device.label||label+" "+(index+1),device.deviceId));
      }
      if([...select.options].some(option=>option.value===chosen))select.value=chosen;
    }
  }
  function stopMeter() {
    cancelAnimationFrame(meterRaf);meterRaf=0;
    try{meterSource?.disconnect();}catch(_error){}
    meterSource=null;audioAnalyser=null;
    const previous=audioContext;audioContext=null;
    if(previous)previous.close().catch(()=>{});
    els.meterFill.style.width="0%";
    els.meter.setAttribute("aria-valuenow","0");
    els.meterValue.textContent="—";
  }
  function startMeter() {
    stopMeter();
    const track=stream?.getAudioTracks()[0];
    const Context=window.AudioContext||window.webkitAudioContext;
    if(!track||!Context)return;
    try{
      audioContext=new Context();
      meterSource=audioContext.createMediaStreamSource(new MediaStream([track]));
      audioAnalyser=audioContext.createAnalyser();
      audioAnalyser.fftSize=256;
      meterSource.connect(audioAnalyser); // no output: avoid microphone feedback
      const samples=new Uint8Array(audioAnalyser.fftSize);
      const tickMeter=()=>{
        if(!audioAnalyser||!stream)return;
        audioAnalyser.getByteTimeDomainData(samples);
        let power=0;
        for(const sample of samples)power+=Math.pow((sample-128)/128,2);
        const rms=Math.sqrt(power/samples.length);
        const level=Math.min(100,Math.round(rms*350));
        els.meterFill.style.width=level+"%";
        els.meter.setAttribute("aria-valuenow",String(level));
        els.meterValue.textContent=level+"%";
        meterRaf=requestAnimationFrame(tickMeter);
      };
      meterRaf=requestAnimationFrame(tickMeter);
    }catch(_error){stopMeter();}
  }
  function recordingInputStream() {
    if(!stream)throw Error("Attiva prima la fotocamera.");
    if(!compositionActive)return stream;
    drawPortraitFrame();
    portraitStream=els.portrait.captureStream(30);
    const track=portraitStream.getVideoTracks()[0];
    if(!track)throw Error("Il browser non ha creato una traccia video verticale.");
    return new MediaStream([track,...stream.getAudioTracks()]);
  }

  async function releaseCamera() {
    stopCompositor();stopMeter();
    if(stream)for(const track of stream.getTracks())track.stop();
    stream=null;
    els.live.pause();
    els.live.srcObject=null;
    inputWidth=0;inputHeight=0;
  }
  async function activateCamera() {
    if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){
      setMode("error");
      notice("Questo browser non supporta Capture. Usa Safari o Chrome aggiornato, su localhost oppure HTTPS.",true);
      return;
    }
    try{
      els.camera.disabled=true;els.flip.disabled=true;
      await releaseCamera();
      const desktop=window.matchMedia("(pointer: fine) and (min-width: 860px)").matches;
      const video=els.videoDevice.value?
        {deviceId:{exact:els.videoDevice.value},width:{ideal:1920},height:{ideal:1080},frameRate:{ideal:30}}:
        {facingMode:{ideal:facing},width:{ideal:desktop?1920:1080},
          height:{ideal:desktop?1080:1920},
          aspectRatio:{ideal:desktop?16/9:9/16},frameRate:{ideal:30}};
      const audio=els.audioDevice.value?{deviceId:{exact:els.audioDevice.value}}:true;
      stream=await navigator.mediaDevices.getUserMedia({video,audio});
      if(!stream.getVideoTracks().length||!stream.getAudioTracks().length)
        throw Error("Fotocamera o microfono assenti.");
      els.live.srcObject=stream;
      els.live.classList.toggle("mirrored",facing==="user");
      await els.live.play();
      configureComposition();
      await refreshDeviceChoices();
      startMeter();
      resetScroll();refreshPrompter();
      setMode("preview");
      notice("Inquadratura "+els.format.textContent+
        ". Controlla il microfono e avvia Registra. Il gobbo non sarà nel file.");
    }catch(error){
      await releaseCamera();setMode("error");
      const denied=["NotAllowedError","PermissionDeniedError","SecurityError"].includes(error?.name);
      notice(denied?"Fotocamera o microfono non autorizzati. Abilita entrambi nei permessi del browser.":
        "Non riesco ad attivare fotocamera e microfono ("+
        (error?.message||error?.name||"errore")+"). Chiudi eventuali altre app e riprova.",true);
    }finally{
      els.camera.disabled=false;els.flip.disabled=false;
    }
  }
  function cancelCountdown() {
    countdownId++;
    els.countdown.hidden = true;
  }
  async function startRecording() {
    if (mode !== "preview" || !stream || !els.script.value.trim()) {
      notice("Inserisci uno script e attiva la fotocamera prima di registrare.", true);
      return;
    }
    resetScroll();
    els.countdown.hidden = false;
    setMode("countdown");
    const seq = ++countdownId;
    for (const number of [3,2,1]) {
      if (seq !== countdownId) return;
      els.countdown.textContent = String(number);
      await new Promise(resolve => setTimeout(resolve, 750));
    }
    if (seq !== countdownId || !stream || mode !== "countdown") return;
    els.countdown.hidden = true;
    try {
      const mimeType = supportedMime();
      const input=recordingInputStream();
      recorder=new MediaRecorder(input,mimeType?{mimeType,
        videoBitsPerSecond:captureQuality()===1080?6000000:3500000
      }:{videoBitsPerSecond:captureQuality()===1080?6000000:3500000});
      recordedMime = recorder.mimeType || mimeType || "video/webm";
      chunks = [];
      recorder.ondataavailable = event => { if (event.data && event.data.size) chunks.push(event.data); };
      recorder.onerror = () => { notice("Registrazione interrotta. Prova a salvare il take, se disponibile.", true); };
      recorder.onstop = finishRecording;
      recorder.start(1000);
      startedAt = performance.now();
      setMode("recording");
      notice("REC verticale "+recordedDimensions.width+"×"+recordedDimensions.height+
        ". Il gobbo è visibile soltanto sullo schermo. Non chiudere il browser.");
      raf = requestAnimationFrame(tick);
    } catch (error) {
      recorder = null;
      setMode("preview");
      notice("Impossibile avviare la registrazione su questo browser (" + (error?.name || "formato non supportato") + ").", true);
    }
  }
  function stopRecording() {
    if (mode !== "recording") return;
    stopAnimation();
    setMode("stopping");
    notice("Sto preparando il video per il download. Tieni aperta questa pagina.");
    try {
      if (recorder && recorder.state !== "inactive") {
        recorder.requestData();
        recorder.stop();
      } else { finishRecording(); }
    } catch (_) { finishRecording(); }
  }
  async function finishRecording() {
    if (mode !== "stopping" && mode !== "recording") return;
    stopAnimation();
    await releaseCamera();
    const type = recordedMime.includes("mp4") ? "video/mp4" : "video/webm";
    output = new Blob(chunks, {type});
    chunks = [];
    recorder = null;
    if (!output.size) {
      output = null;
      setMode("error");
      notice("Il browser non ha restituito dati video. Non chiudere altre registrazioni senza averne verificato l'anteprima.", true);
      return;
    }
    if (blobUrl) URL.revokeObjectURL(blobUrl);
    blobUrl = URL.createObjectURL(output);
    outputName = "pausio-take-" + new Date().toISOString().replace(/[:.]/g,"-") +
      (type === "video/mp4" ? ".mp4" : ".webm");
    els.playback.src = blobUrl;
    els.download.href = blobUrl;
    els.download.download = outputName;
    const seconds = Math.round((performance.now() - startedAt) / 1000);
    els.details.textContent=outputName.split(".").pop().toUpperCase()+" · "+
      (recordedDimensions?.width||"?")+"×"+(recordedDimensions?.height||"?")+" · "+
      (output.size/(1024*1024)).toFixed(1)+" MB · "+seconds+" s · senza gobbo";
    savedAfterRecording = false;
    const file = new File([output], outputName, {type});
    els.share.hidden = !(navigator.canShare && navigator.canShare({files:[file]}));
    setMode("finished");
    notice("Take pronto. Scarica il file e verifica video e audio."+
      (isLocalStudio?" Puoi anche importarlo direttamente in Pausio Studio.":""));
  }
  async function shareRecording() {
    if (!output || !navigator.share) return;
    try {
      const file = new File([output], outputName, {type:output.type});
      if (!navigator.canShare?.({files:[file]})) throw Error("Share non disponibile");
      await navigator.share({files:[file],title:"Pausio · Video registrato"});
      savedAfterRecording = true;
      notice("Condivisione avviata. Controlla nell'app scelta che il video sia stato salvato.");
    } catch (error) {
      if (error?.name !== "AbortError") notice("Condivisione non disponibile: usa Scarica video oppure apri il file nel browser.", true);
    }
  }
  async function importIntoStudio() {
    if(!isLocalStudio||!output||mode!=="finished")return;
    const button=els.openStudio;
    try{
      button.disabled=true;
      const stateResponse=await fetch("/api/state");
      if(!stateResponse.ok)throw Error("Studio locale non disponibile.");
      const state=await stateResponse.json();
      if(state.file&&!window.confirm("Studio contiene già un video: importare questo take sostituirà il progetto attuale. Procedere?"))
        return;
      if(!savedAfterRecording&&!window.confirm(
        "Importare il take in Studio lo salva nella sessione locale. Vuoi procedere anche senza una copia nella cartella Download?"))
        return;
      notice("Importazione locale in Pausio Studio in corso...");
      const response=await fetch("/api/import",{
        method:"POST",
        headers:{"Content-Type":"application/octet-stream",
          "X-Pausio-Client":"studio","X-Filename":encodeURIComponent(outputName)},
        body:output
      });
      const result=await response.json();
      if(!response.ok)throw Error(result?.error||"Importazione non riuscita.");
      savedAfterRecording=true;
      window.location.assign("/");
    }catch(error){
      notice("Importazione fallita: "+(error?.message||"errore")+
        ". Scarica il take prima di uscire.",true);
    }finally{button.disabled=false;}
  }
  async function newTake() {
    if (mode !== "finished") return;
    if (!savedAfterRecording && !window.confirm("Hai salvato il take sul dispositivo? Iniziando un nuovo take perderai l'anteprima attuale.")) return;
    els.playback.pause();
    els.playback.removeAttribute("src");
    els.playback.load();
    if (blobUrl) URL.revokeObjectURL(blobUrl);
    blobUrl = null; output = null; outputName = "";
    setMode("idle");
    notice("Pronto per un altro take. Il copione e le impostazioni restano disponibili.");
    await activateCamera();
  }
  els.camera.addEventListener("click",activateCamera);
  els.openStudio.addEventListener("click",importIntoStudio);
  for(const select of [els.videoDevice,els.audioDevice]){
    select.addEventListener("change",()=>{if(mode==="preview")activateCamera();});
  }
  for(const control of [els.quality,els.panX,els.panY,els.zoom]){
    control.addEventListener("input",()=>{
      if(mode!=="preview"&&mode!=="idle")return;
      updateFramingLabels();remember();
      if(mode==="preview"){
        try{configureComposition();}
        catch(error){notice("Ritaglio verticale non disponibile: "+error.message,true);}
      }
    });
  }
  els.resetCrop.addEventListener("click",()=>{
    els.panX.value="50";els.panY.value="50";els.zoom.value="100";
    updateFramingLabels();remember();
    if(mode==="preview")configureComposition();
  });
  els.flip.addEventListener("click",async()=>{
    if(mode!=="preview")return;
    facing=facing==="user"?"environment":"user";
    els.videoDevice.value="";
    await activateCamera();
  });
  els.rehearse.addEventListener("click",toggleRehearsal);
  els.rehearsalRestart.addEventListener("click",restartRehearsal);
  els.start.addEventListener("click", startRecording);
  els.stop.addEventListener("click", stopRecording);
  els.next.addEventListener("click", newTake);
  els.pause.addEventListener("click", () => { pausedScroll = !pausedScroll; els.pause.textContent = pausedScroll ? "▶" : "Ⅱ"; els.pause.setAttribute("aria-label",pausedScroll ? "Riprendi scorrimento" : "Pausa scorrimento"); });
  els.download.addEventListener("click", () => { savedAfterRecording = true; notice("Download richiesto. Verifica che il file sia realmente presente in Download o File prima di uscire."); });
  els.share.addEventListener("click", shareRecording);
  for (const el of [els.script,els.speed,els.font,els.position,els.autoplay]) {
    el.addEventListener(el === els.script ? "input" : "change", () => { refreshPrompter(); remember(); });
    if (el === els.speed || el === els.font) el.addEventListener("input", () => { refreshPrompter(); remember(); });
  }
  document.addEventListener("visibilitychange", () => {
    if(document.hidden&&rehearsalState==="playing"){
      toggleRehearsal();
      notice("Prova gobbo in pausa: torna alla pagina per riprendere.");
    }
    if (document.hidden && (mode === "recording" || mode === "countdown")) {
      notice("Non bloccare lo schermo: il browser può interrompere fotocamera e registrazione.", true);
    }
  });
  window.addEventListener("pagehide", () => { cancelCountdown(); stopAnimation(); releaseCamera(); });
  window.addEventListener("beforeunload", event => {
    if (mode === "recording" || mode === "stopping" || (mode === "finished" && !savedAfterRecording)) {
      event.preventDefault(); event.returnValue = "";
    }
  });
  prefs();refreshPrompter();updateFramingLabels();setMode("idle");
  refreshDeviceChoices().catch(()=>{});
  navigator.mediaDevices?.addEventListener?.("devicechange",()=>{
    if(mode==="idle"||mode==="preview")refreshDeviceChoices().catch(()=>{});
  });
  if (!window.isSecureContext && !["localhost","127.0.0.1"].includes(location.hostname)) {
    els.camera.disabled = true;
    notice("La fotocamera da browser richiede HTTPS. Apri questa pagina da un sito HTTPS.", true);
  }
})();
