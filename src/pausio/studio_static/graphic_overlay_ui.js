"use strict";
/* Local graphic card controls. Only project commands can change rendered output. */
(() => {
  const e=id=>document.getElementById(id);
  const graphics=()=>project?.graphic_overlays||[];
  const value=id=>e(id).value;
  const fields=["graphic-text","graphic-kind","graphic-animation","graphic-duration",
                "graphic-x","graphic-y","graphic-size","graphic-color"];
  const integer=(id,lo,hi)=>{
    const node=e(id);
    if(!node.checkValidity())throw Error("Parametro grafico fuori dai limiti: "+id);
    const number=Number(node.value);
    if(!Number.isInteger(number)||number<lo||number>hi)throw Error("Valore grafico non valido: "+id);
    return number;
  };
  const makeId=()=>crypto.randomUUID().replaceAll("-","");
  const rowFor=(graphic)=>{
    const node=document.createElement("div");
    node.className="visual-fx-entry";
    node.dataset.graphicId=graphic.id;
    const summary=document.createElement("strong");
    summary.textContent=graphic.kind.toUpperCase()+" · "+(graphic.start_ms/1000).toFixed(2)+"s";
    const input=document.createElement("input");
    input.value=graphic.text;
    input.maxLength=100;
    input.setAttribute("aria-label","Testo grafica");
    const controls=document.createElement("div");
    controls.className="visual-fx-edit-grid";
    const spec=[
      ["Posizione X","x_pct",15,85],["Posizione Y","y_pct",8,62],
      ["Dimensione","font_size",36,104]
    ];
    const edits={};
    for(const [title,key,min,max] of spec){
      const label=document.createElement("label");
      label.textContent=title;
      const field=document.createElement("input");
      field.type="number";field.min=String(min);field.max=String(max);
      field.value=String(graphic[key]);edits[key]=field;
      label.append(field);controls.append(label);
    }
    // Editing controls are projections of canonical v5 fields; save dispatches
    // a single typed update rather than storing a browser-only draft.
    const choice=(labelText,key,options)=>{
      const label=document.createElement("label");label.textContent=labelText;
      const select=document.createElement("select");
      select.setAttribute("aria-label",labelText+" grafica");
      for(const [keyValue,text] of options){
        const option=document.createElement("option");
        option.value=keyValue;option.textContent=text;select.append(option);
      }
      select.value=graphic[key];label.append(select);controls.append(label);
      return select;
    };
    const kindField=choice("Stile","kind",[
      ["headline","Titolo"],["stat","Dato"],["code","Codice"],["tip","Suggerimento"]
    ]);
    const animationField=choice("Animazione","animation",[
      ["fade","Fade"],["pop","Pop"],["slide","Slide"]
    ]);
    const durationLabel=document.createElement("label");
    durationLabel.textContent="Durata (ms)";
    const durationField=document.createElement("input");
    durationField.type="number";durationField.min="400";durationField.max="12000";
    durationField.step="100";durationField.value=String(graphic.end_ms-graphic.start_ms);
    durationField.setAttribute("aria-label","Durata grafica (ms)");
    durationLabel.append(durationField);controls.append(durationLabel);
    const colorLabel=document.createElement("label");colorLabel.textContent="Colore";
    const colorField=document.createElement("input");
    colorField.type="color";colorField.value=graphic.color.toLowerCase();
    colorField.setAttribute("aria-label","Colore grafica");
    colorLabel.append(colorField);controls.append(colorLabel);
    const actions=document.createElement("div");
    actions.className="visual-fx-entry-actions";
    const button=(title,callback)=>{
      const b=document.createElement("button");b.type="button";
      b.className="button button-outline";b.textContent=title;
      b.addEventListener("click",()=>run(callback));return b;
    };
    actions.append(
      button("Salva modifiche",async()=>{
        if(!durationField.checkValidity()||!Number.isInteger(Number(durationField.value)))
          throw Error("Durata grafica fuori dai limiti.");
        const updated={
          ...graphic,text:input.value.trim(),
          kind:kindField.value,animation:animationField.value,
          color:colorField.value.toUpperCase(),
          end_ms:graphic.start_ms+Number(durationField.value),
        };
        for(const [title,key] of spec){
          const field=edits[key];
          if(!field.checkValidity()||!Number.isInteger(Number(field.value)))
            throw Error("Valore non valido: "+title);
          updated[key]=Number(field.value);
        }
        await edit("graphic.overlay.update",{graphic:updated});
      }),
      button("Rimuovi",()=>edit("graphic.overlay.remove",{graphic_id:graphic.id})),
    );
    node.append(summary,input,controls,actions);
    return node;
  };
  function draw(){
    const available=!!project?.plan;
    e("graphic-add").disabled=!available||working();
    e("graphic-preview").disabled=!available||working();
    for(const id of fields)e(id).disabled=working();
    const list=e("graphic-list");
    list.replaceChildren();
    for(const graphic of graphics())list.append(rowFor(graphic));
    e("graphic-status").textContent=available
      ? graphics().length+"/12 schede grafiche · la simulazione mostra solo i tagli; per vedere le animazioni genera una preview FFmpeg."
      : "Analizza prima il video, poi aggiungi schede grafiche.";
    for(const node of list.querySelectorAll("input,button,select"))node.disabled=working();
  }
  async function add(){
    if(!project?.plan)throw Error("Analizza prima il video.");
    const text=value("graphic-text").trim();
    if(!text)throw Error("Scrivi il testo della scheda.");
    const duration=integer("graphic-duration",400,12000);
    const x=integer("graphic-x",15,85),y=integer("graphic-y",8,62);
    const fontSize=integer("graphic-size",36,104);
    const at=(mode==="rendered"?sourceFromOutput(v.currentTime*1000):v.currentTime*1000);
    const segment=(project.editor_segments||[]).find(s=>s.start_ms<=at&&at<s.end_ms);
    if(!segment)throw Error("Sposta il cursore dentro un intervallo mantenuto.");
    const available=segment.end_ms-segment.start_ms;
    if(available<400)throw Error("Intervallo troppo breve per una scheda grafica.");
    const length=Math.min(duration,available);
    const start=Math.max(segment.start_ms,Math.min(Math.round(at),segment.end_ms-length));
    const graphic={
      id:makeId(),segment_id:segment.id,
      start_ms:start,end_ms:start+length,
      text,kind:value("graphic-kind"),animation:value("graphic-animation"),
      x_pct:x,y_pct:y,font_size:fontSize,color:value("graphic-color").toUpperCase(),
    };
    await edit("graphic.overlay.add",{graphic});
  }
  e("graphic-add").addEventListener("click",()=>run(add));
  e("graphic-preview").addEventListener("click",()=>run(()=>startJob("preview")));
  window.pausioGraphics={update:draw};
  if(project)draw();
})();
