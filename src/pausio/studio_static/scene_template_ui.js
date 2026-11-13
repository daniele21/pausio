"use strict";
/* Full-screen social scene templates: one typed ProjectTape event per scene.
   Schema/defaults come from Python Studio snapshot, never from a JS renderer. */
(() => {
  const el=id=>document.getElementById(id);
  const scenes=()=>project?.scene_templates||[];
  const formats=()=>project?.scene_template_catalog||[];
  const output=()=>editedDuration();
  const now=()=>Math.round(mode==="rendered"?v.currentTime*1000:
                           outputTime(v.currentTime*1000));
  let cachedFormats="";
  const slug=()=>crypto.randomUUID().replaceAll("-","");
  const format=id=>formats().find(x=>x.id===id);

  function controls(target, fmt, values={}){
    target.replaceChildren();
    for(const field of fmt.fields){
      const label=document.createElement("label");
      label.textContent=field.label;
      const node=document.createElement(field.type==="textarea"?"textarea":"input");
      node.dataset.sceneField=field.key;
      if(field.type==="integer"){
        node.type="number";
        node.min=String(field.minimum);node.max=String(field.maximum);
        node.step="1";
      }else if(field.type==="text"){
        node.type="text";
        node.maxLength=field.max_length;
      }else{
        node.rows=5;
        node.maxLength=field.max_length;
      }
      node.value=String(values[field.key]??field.default);
      node.required=true;
      node.setAttribute("aria-label",field.label);
      label.append(node);
      target.append(label);
    }
  }
  function readFields(target,fmt){
    const result={};
    for(const field of fmt.fields){
      const node=target.querySelector('[data-scene-field="'+field.key+'"]');
      if(!node||!node.checkValidity())throw Error("Controlla: "+field.label);
      const value=field.type==="integer"?Number(node.value):node.value.trim();
      if((field.type==="integer"&&!Number.isInteger(value))||value===""||
         (field.type!=="integer"&&!value))
        throw Error("Valore scena non valido: "+field.label);
      result[field.key]=value;
    }
    return result;
  }
  function validatedTime(node,min,max,name){
    const value=Number(node.value);
    if(!node.checkValidity()||!Number.isInteger(value)||value<min||value>max)
      throw Error("Controlla "+name+" (millisecondi del video montato).");
    return value;
  }
  function button(label,callback,primary=false){
    const b=document.createElement("button");
    b.type="button";b.className=primary?"button button-primary":"button button-outline";
    b.textContent=label;b.disabled=working();
    b.addEventListener("click",()=>run(callback));
    return b;
  }
  async function preview(scene){
    const length=Math.min(5000,output());
    if(length<250)throw Error("Il montaggio è troppo breve.");
    const start=Math.min(Math.max(0,scene.start_ms-350),output()-length);
    update(await post("/api/jobs",{
      kind:"preview_range",range_start_ms:start,range_duration_ms:length
    }));
  }
  function makeCard(scene){
    const fmt=format(scene.template);
    if(!fmt)return document.createTextNode("Template sconosciuto.");
    const card=document.createElement("section");
    card.className="visual-fx-entry scene-card";
    card.dataset.sceneId=scene.id;
    const header=document.createElement("strong");header.textContent=fmt.label;
    const range=document.createElement("p");range.className="scene-range";
    range.textContent="Video finale: "+msFormat(scene.start_ms,true)+" – "+
      msFormat(scene.start_ms+scene.duration_ms,true);
    const actions=document.createElement("div");actions.className="scene-actions";
    actions.append(
      button("Vai al punto",()=>{
        v.pause();
        const at=mode==="rendered"?scene.start_ms:sourceFromOutput(scene.start_ms);
        v.currentTime=at/1000;
        timelineLocate(sourceFromOutput(scene.start_ms));
      }),
      button("▶ Guarda 5 s",()=>preview(scene),true)
    );
    const details=document.createElement("details");
    const summary=document.createElement("summary");
    summary.textContent="Modifica testo e durata";
    details.append(summary);
    const controlsBox=document.createElement("div");controlsBox.className="scene-content-fields";
    controls(controlsBox,fmt,scene.content);
    const startLabel=document.createElement("label");
    startLabel.textContent="Inizio nel video montato (ms)";
    const startInput=document.createElement("input");
    startInput.type="number";startInput.min="0";startInput.step="100";
    startInput.value=String(scene.start_ms);
    startLabel.append(startInput);
    const durationLabel=document.createElement("label");
    durationLabel.textContent="Durata (ms)";
    const durationInput=document.createElement("input");
    durationInput.type="number";durationInput.min="2500";durationInput.max="12000";
    durationInput.step="100";durationInput.value=String(scene.duration_ms);
    durationLabel.append(durationInput);
    const accentLabel=document.createElement("label");
    accentLabel.textContent="Accento";
    const accent=document.createElement("select");
    for(const [name,text] of [["mint","Verde acqua"],["orange","Arancione"]]){
      const option=document.createElement("option");
      option.value=name;option.textContent=text;accent.append(option);
    }
    accent.value=scene.accent;
    accentLabel.append(accent);
    const save=button("Salva modifiche",async()=>{
      const changed={...scene,
        content:readFields(controlsBox,fmt),
        start_ms:validatedTime(startInput,0,output()-1,"l'inizio"),
        duration_ms:validatedTime(durationInput,2500,12000,"la durata"),
        accent:accent.value
      };
      await edit("scene.template.update",{scene:changed});
    },true);
    details.append(controlsBox,startLabel,durationLabel,accentLabel,save);
    const remove=button("Rimuovi scena",()=>edit(
      "scene.template.remove",{scene_id:scene.id}));
    remove.classList.add("scene-remove");
    card.append(header,range,actions,details,remove);
    return card;
  }
  function ensureChoices(){
    const ids=formats().map(f=>f.id).join(",");
    if(ids===cachedFormats)return;
    cachedFormats=ids;
    const select=el("scene-template-kind");
    select.replaceChildren();
    for(const fmt of formats()){
      const option=document.createElement("option");
      option.value=fmt.id;option.textContent=fmt.label;select.append(option);
    }
    refreshFields();
  }
  function refreshFields(){
    const fmt=format(el("scene-template-kind").value);
    if(fmt)controls(el("scene-template-fields"),fmt);
  }
  async function add(){
    if(!project?.plan)throw Error("Prepara prima un montaggio.");
    const fmt=format(el("scene-template-kind").value);
    if(!fmt)throw Error("Seleziona un template.");
    const duration=validatedTime(el("scene-template-duration"),
                                 2500,12000,"la durata");
    const at=Math.max(0,Math.min(output()-duration,now()));
    const scene={
      id:slug(),template:fmt.id,start_ms:at,duration_ms:duration,
      accent:el("scene-template-accent").value,
      content:readFields(el("scene-template-fields"),fmt)
    };
    if(output()<duration)throw Error("Il video è troppo corto per questa scena.");
    await edit("scene.template.add",{scene});
  }
  function draw(){
    ensureChoices();
    const ready=!!project?.plan&&!working();
    el("scene-template-add").disabled=!ready||scenes().length>=9;
    const status=el("scene-template-status");
    status.textContent=project?.plan
      ? scenes().length+"/9 scene · sfondo a schermo intero; la voce originale continua. "
        +"Per vedere il risultato usa «Guarda 5 s»."
      : "Importa un video e prepara un montaggio per aggiungere scene.";
    const list=el("scene-template-list");list.replaceChildren();
    for(const item of scenes())list.append(makeCard(item));
    for(const node of list.querySelectorAll("input,textarea,select,button"))node.disabled=working();
  }
  el("scene-template-kind").addEventListener("change",refreshFields);
  el("scene-template-add").addEventListener("click",()=>run(add));
  window.pausioSceneTemplates={update:draw};
  if(project)draw();
})();
