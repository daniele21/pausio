/* Pausio Mobile Capture. No backend, analytics or external services. */
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
    autoplay: $("auto-scroll")
  };
  const STORE_KEY = "pausio-mobile-capture-v1";
  let stream = null, recorder = null, chunks = [], output = null, blobUrl = null;
  let outputName = "", mode = "idle", facing = "user", raf = 0, lastFrame = 0;
  let startedAt = 0, pausedScroll = false, countdownId = 0;
  let savedAfterRecording = false, recordedMime = "";

  function notice(message, error = false) {
    els.status.textContent = message;
    els.status.classList.toggle("error", error);
  }
  function setMode(next) {
    mode = next;
    els.camera.hidden = !["idle", "error", "starting"].includes(next);
    els.camera.textContent = next === "starting" ? "Apertura fotocamera…" : "Attiva fotocamera";
    els.start.hidden = next !== "preview";
    els.stop.hidden = next !== "recording";
    els.next.hidden = next !== "finished";
    els.flip.hidden = next !== "preview";
    els.pause.hidden = next !== "preview" && next !== "recording";
    els.panel.hidden = next !== "finished";
    els.placeholder.hidden = !["idle", "error", "starting"].includes(next);
    els.live.hidden = ["finished", "idle", "error", "starting"].includes(next);
    els.playback.hidden = next !== "finished";
    els.prompter.hidden = next === "finished" || next === "idle" || next === "error";
    els.timer.classList.toggle("live", next === "recording");
    els.state.textContent = {idle:"PRONTO", error:"ERRORE", starting:"APERTURA…", preview:"CAMERA ATTIVA",
      countdown:"PREPARATI", recording:"REC", stopping:"SALVATAGGIO", finished:"TAKE PRONTO"}[next] || "PRONTO";
    const locked = ["countdown","recording","stopping"].includes(next);
    for (const el of [els.script,els.speed,els.font,els.position,els.autoplay]) el.disabled = locked;
    els.pause.textContent = pausedScroll ? "▶" : "Ⅱ";
    els.pause.setAttribute("aria-label", pausedScroll ? "Riprendi scorrimento" : "Pausa scorrimento");
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
    } catch (_) { /* Storage unavailable in private browsing. */ }
  }
  function remember() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({version:1,
        script:els.script.value.slice(0,15000), speed:+els.speed.value, font:+els.font.value,
        position:els.position.value, autoplay:els.autoplay.checked}));
    } catch (_) { /* Capture and downloads do not require localStorage. */ }
  }
  function refreshPrompter() {
    els.text.textContent = els.script.value.trim() || "Scrivi uno script nelle impostazioni.";
    els.prompter.style.setProperty("--font-size", els.font.value + "px");
    els.prompter.classList.toggle("middle", els.position.value === "middle");
    $("speed-value").textContent = els.speed.value + " parole/min";
    $("font-value").textContent = els.font.value + " px";
  }
  function stopAnimation() { cancelAnimationFrame(raf); raf = 0; lastFrame = 0; }
  function tick(now) {
    if (mode !== "recording" && mode !== "preview") { stopAnimation(); return; }
    if (mode === "recording") {
      const elapsed = Math.max(0, Math.floor((now - startedAt) / 1000));
      els.clock.textContent = String(Math.floor(elapsed / 60)).padStart(2, "0")
        + ":" + String(elapsed % 60).padStart(2, "0");
    }
    if (lastFrame && !pausedScroll && els.autoplay.checked && mode === "recording") {
      const fontPx = +els.font.value;
      const charsPerLine = Math.max(10, els.scroll.clientWidth / (fontPx * .54));
      const wordsPerLine = Math.max(1.6, charsPerLine / 6);
      const pxPerSecond = ((+els.speed.value / 60) / wordsPerLine) * fontPx * 1.4;
      els.scroll.scrollTop += Math.min((now - lastFrame) / 1000, .15) * pxPerSecond;
    }
    lastFrame = now;
    raf = requestAnimationFrame(tick);
  }
  function resetScroll() {
    stopAnimation(); els.scroll.scrollTop = 0; pausedScroll = false; els.clock.textContent = "00:00";
  }
  function supportedMime() {
    if (!window.MediaRecorder) return "";
    const candidates = [
      'video/mp4;codecs="avc1.42E01E,mp4a.40.2"', "video/mp4",
      "video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"
    ];
    return candidates.find(type => MediaRecorder.isTypeSupported(type)) || "";
  }
  async function releaseCamera() {
    if (stream) for (const track of stream.getTracks()) track.stop();
    stream = null;
    els.live.pause();
    els.live.srcObject = null;
  }
  async function activateCamera() {
    if (["starting", "countdown", "recording", "stopping"].includes(mode)) return;
    if (!window.isSecureContext && !["localhost", "127.0.0.1"].includes(location.hostname)) {
      setMode("error");
      notice("La fotocamera richiede HTTPS. Apri il link direttamente in Chrome o Safari.", true);
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setMode("error");
      notice("Questo browser non supporta la registrazione diretta. Usa Safari aggiornato su iPhone o Chrome aggiornato su Android, tramite HTTPS.", true);
      return;
    }
    try {
      setMode("starting");
      notice("Apertura fotocamera e microfono… Se compare una richiesta del browser, scegli Consenti.");
      els.camera.disabled = true;
      els.flip.disabled = true;
      await releaseCamera();
      const candidate = await navigator.mediaDevices.getUserMedia({
        video: {facingMode: {ideal:facing}, width:{ideal:1080}, height:{ideal:1920},
          aspectRatio:{ideal:9/16}, frameRate:{ideal:30}},
        audio: true
      });
      stream = candidate;
      els.live.srcObject = stream;
      els.live.classList.toggle("mirrored", facing === "user");
      resetScroll();
      refreshPrompter();
      // Reveal the video BEFORE asking the browser to play it. Safari can leave
      // play() pending indefinitely when its target is display:none.
      setMode("preview");
      try {
        const playback = els.live.play();
        if (playback && typeof playback.catch === "function") {
          playback.catch(() => {
            if (mode === "preview") {
              notice("Fotocamera attiva, ma l'anteprima non parte: tocca il video per riprovare. Se non funziona, apri la pagina in Chrome o Safari.", true);
            }
          });
        }
      } catch (_) {
        notice("Fotocamera attiva: tocca il video per attivare l'anteprima.", true);
      }
      const dimensions = candidate.getVideoTracks()[0]?.getSettings?.() || {};
      const width = dimensions.width, height = dimensions.height;
      els.format.textContent = width && height ? width + "×" + height + " · originale" : "Formato automatico";
      if (width && height && width >= height) {
        notice("La fotocamera registra in orizzontale (" + width + "×" + height + "). Ruota il telefono in verticale e riattiva la fotocamera prima del take.", true);
      } else {
        notice("Controlla l'inquadratura, poi tocca Registra. Il gobbo sarà visibile solo sullo schermo.");
      }
    } catch (error) {
      await releaseCamera();
      setMode("error");
      const denied = ["NotAllowedError","PermissionDeniedError","SecurityError"].includes(error?.name);
      notice(denied ? "Accesso negato: consenti fotocamera e microfono nelle impostazioni del sito, poi premi di nuovo Attiva fotocamera. Se sei in un browser integrato, apri il link in Chrome o Safari." :
        "Non riesco ad aprire fotocamera e microfono (" + (error?.name || "errore") + "). Chiudi altre app che li usano e riprova.", true);
    } finally {
      els.camera.disabled = false;
      els.flip.disabled = false;
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
      recorder = new MediaRecorder(stream, mimeType ? {mimeType} : undefined);
      recordedMime = recorder.mimeType || mimeType || "video/webm";
      chunks = [];
      recorder.ondataavailable = event => { if (event.data && event.data.size) chunks.push(event.data); };
      recorder.onerror = () => { notice("Registrazione interrotta. Prova a salvare il take, se disponibile.", true); };
      recorder.onstop = finishRecording;
      recorder.start(1000);
      startedAt = performance.now();
      setMode("recording");
      notice("Registrazione in corso. Non bloccare lo schermo e non uscire dal browser.");
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
    els.details.textContent = outputName.split(".").pop().toUpperCase() + " · " +
      (output.size / (1024 * 1024)).toFixed(1) + " MB · " + seconds + " s · senza gobbo";
    savedAfterRecording = false;
    const file = new File([output], outputName, {type});
    els.share.hidden = !(navigator.canShare && navigator.canShare({files:[file]}));
    setMode("finished");
    notice("Take pronto. Tocca Scarica video oppure Condividi / Salva su File. Verifica il file prima di abbandonare la pagina.");
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
  async function newTake() {
    if (mode !== "finished") return;
    if (!savedAfterRecording && !window.confirm("Hai salvato il video sul telefono? Iniziando un nuovo take perderai l'anteprima attuale.")) return;
    els.playback.pause();
    els.playback.removeAttribute("src");
    els.playback.load();
    if (blobUrl) URL.revokeObjectURL(blobUrl);
    blobUrl = null; output = null; outputName = "";
    setMode("idle");
    notice("Pronto per un altro take. Il copione e le impostazioni restano disponibili.");
    await activateCamera();
  }
  els.camera.addEventListener("click", activateCamera);
  els.live.addEventListener("click", () => {
    if (mode !== "preview") return;
    const pending = els.live.play();
    if (pending && typeof pending.catch === "function") {
      pending.catch(() => notice("Il browser ha bloccato l'anteprima: controlla i permessi della fotocamera.", true));
    }
  });
  els.flip.addEventListener("click", async () => { if (mode !== "preview") return; facing = facing === "user" ? "environment" : "user"; await activateCamera(); });
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
  prefs(); refreshPrompter(); setMode("idle");
  notice("Pagina pronta. Tocca Attiva fotocamera e consenti l'accesso a fotocamera e microfono.");
  if (!window.isSecureContext && !["localhost","127.0.0.1"].includes(location.hostname)) {
    els.camera.disabled = true;
    notice("La fotocamera da browser richiede HTTPS. Apri questa pagina da un sito HTTPS.", true);
  }
})();
