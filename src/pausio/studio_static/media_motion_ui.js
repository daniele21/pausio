"use strict";
/* Shared, bounded media transition UI for both image and video inserts.
   Saving remains one ordinary typed ProjectTape update, not browser state. */
(() => {
  function make(clip) {
    const outer=document.createElement("div");
    const details=document.createElement("details");
    details.className="pip-advanced";
    const summary=document.createElement("summary");
    summary.textContent="Animazioni di entrata e uscita";
    details.append(summary);
    const enabledLabel=document.createElement("label");
    const enabled=document.createElement("input");enabled.type="checkbox";
    enabled.checked=Boolean(clip.motion);
    enabledLabel.append(enabled,document.createTextNode(" Personalizza animazioni"));
    details.append(enabledLabel);
    const controls=document.createElement("div");controls.className="visual-fx-edit-grid";
    const makeSelect=(title,options,current)=>{
      const label=document.createElement("label");label.textContent=title;
      const field=document.createElement("select");field.setAttribute("aria-label",title+" inserto");
      for(const [value,description] of options){
        const opt=document.createElement("option");opt.value=value;opt.textContent=description;
        field.append(opt);
      }
      field.value=current;label.append(field);controls.append(label);return field;
    };
    const makeDuration=(title,current)=>{
      const label=document.createElement("label");label.textContent=title;
      const field=document.createElement("input");field.type="number";
      field.min="0";field.max="800";field.step="10";
      field.value=String(current);field.setAttribute("aria-label",title+" inserto");
      label.append(field);controls.append(label);return field;
    };
    const enter=makeSelect("Animazione entrata",[
      ["fade","Dissolvenza"],["slide_up","Slide dal basso"],
      ["slide_left","Slide da sinistra"],["none","Nessuna"]
    ],clip.motion?.enter||"fade");
    const enterMs=makeDuration("Durata entrata (ms)",clip.motion?.enter_ms??220);
    const leave=makeSelect("Animazione uscita",[
      ["fade","Dissolvenza"],["slide_down","Slide verso il basso"],
      ["slide_right","Slide verso destra"],["none","Nessuna"]
    ],clip.motion?.exit||"fade");
    const exitMs=makeDuration("Durata uscita (ms)",clip.motion?.exit_ms??200);
    const sync=()=>{
      for(const node of [enter,enterMs,leave,exitMs])node.disabled=!enabled.checked;
      for(const [mode,duration] of [[enter,enterMs],[leave,exitMs]]){
        if(mode.value==="none")duration.value="0";
      }
    };
    const syncDuration=(mode,duration)=>{
      if(mode.value==="none")duration.value="0";
      else if(Number(duration.value)===0)duration.value="200";
      sync();
    };
    enter.addEventListener("change",()=>syncDuration(enter,enterMs));
    leave.addEventListener("change",()=>syncDuration(leave,exitMs));
    enabled.addEventListener("change",sync);
    details.append(controls);
    const hint=document.createElement("p");hint.className="caption-hint";
    hint.textContent="Fade e slide configurabili separatamente (80–800 ms). " +
      "Il risultato effettivo si vede nella preview FFmpeg.";
    details.append(hint);
    outer.append(details);
    sync();
    return {node:outer,read:()=>{
      if(!enabled.checked)return null;
      for(const field of [enterMs,exitMs]){
        if(!field.checkValidity()||!Number.isInteger(Number(field.value))){
          throw Error("Durata dell'animazione non valida.");
        }
      }
      return {enter:enter.value,exit:leave.value,
        enter_ms:Number(enterMs.value),exit_ms:Number(exitMs.value)};
    }};
  }
  window.pausioMediaMotion={make};
})();
