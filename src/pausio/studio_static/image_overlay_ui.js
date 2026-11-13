"use strict";
/* Image PIP editor: image bytes stay local and every edit is a portable command. */
(() => {
  const el=id=>document.getElementById(id);
  const items=()=>project?.image_overlays||[];
  let sending=false;
  const makeId=()=>crypto.randomUUID().replaceAll("-","");
  function fieldsFor(image){
    const wrapper=document.createElement("div");
    wrapper.className="visual-fx-entry";
    wrapper.dataset.pipId=image.id;
    const heading=document.createElement("strong");
    heading.textContent=image.filename+" · "+(image.start_ms/1000).toFixed(2)+" s";
    const detail=document.createElement("p");
    detail.textContent=image.available
      ?"Asset locale verificato al prossimo render.":"Asset mancante: reimporta lo stesso file.";
    const grid=document.createElement("div");grid.className="visual-fx-edit-grid";
    const editable={};
    const settings=[
      ["Inizio output (s)","start_ms",0,172800,1000],
      ["Durata (s)","duration_ms",0.4,12,1000],
      ["Larghezza (%)","width_pct",20,70,1],
      ["Orizzontale (%)","x_pct",0,100,1],
      ["Verticale (%)","y_pct",0,100,1]
    ];
    for(const [label,key,min,max,divisor] of settings){
      const wrap=document.createElement("label");wrap.textContent=label;
      const input=document.createElement("input");input.type="number";
      input.step=divisor===1000?"0.1":"1";
      input.min=String(min);input.max=String(max);
      input.value=String(image[key]/divisor);
      input.setAttribute("aria-label",label+" immagine PIP");
      wrap.append(input);grid.append(wrap);
      editable[key]={input,divisor};
    }
    const actions=document.createElement("div");actions.className="visual-fx-entry-actions";
    function button(label,callback){
      const node=document.createElement("button");node.type="button";
      node.className="button button-outline";node.textContent=label;
      node.addEventListener("click",()=>run(callback));
      node.disabled=working()||sending;
      return node;
    }
    actions.append(
      button("Salva posizione",async()=>{
        const {available,...payload}=image;
        for(const [key,obj] of Object.entries(editable)){
          if(!obj.input.checkValidity()||!Number.isFinite(Number(obj.input.value)))
            throw Error("Parametro PIP fuori dai limiti: "+key);
          payload[key]=Math.round(Number(obj.input.value)*obj.divisor);
        }
        await edit("image.overlay.update",{image:payload});
      }),
      button("Rimuovi",()=>edit("image.overlay.remove",{image_id:image.id}))
    );
    wrapper.append(heading,detail,grid,actions);
    return wrapper;
  }
  function draw(){
    const ready=!!project?.plan&&!working()&&!sending;
    el("pip-image-import").disabled=!ready;
    el("pip-image-preview").disabled=!ready;
    el("pip-image-status").textContent=project?.plan
      ? items().length+"/4 immagini · massimo 12 MB / 12 MP ciascuna. "+
        "La simulazione mostra solo i tagli: genera una preview FFmpeg per vedere il PIP."
      : "Importa e analizza prima un video.";
    const list=el("pip-image-list");list.replaceChildren();
    for(const image of items())list.append(fieldsFor(image));
  }
  async function importImage(file){
    if(!file)return;
    if(!project?.plan)throw Error("Prepara prima un montaggio.");
    if(!file.size||file.size>12*1024*1024)
      throw Error("Scegli un'immagine PNG/JPG/WebP fino a 12 MB.");
    const extension=(file.name.split(".").pop()||"").toLowerCase();
    if(!["png","jpg","jpeg","webp"].includes(extension))
      throw Error("Formato non valido: scegli PNG, JPG oppure WebP.");
    const revision=project.project_revision;
    const sourceAt=Math.round((v.currentTime||0)*1000);
    const outputAt=mode==="rendered"?sourceAt:outputTime(sourceAt);
    const max=editedDuration();
    const anchor=Math.max(0,Math.min(max-1,Math.round(outputAt)));
    sending=true;draw();
    try{
      const response=await fetch("/api/image/import",{
        method:"POST",cache:"no-store",body:file,
        headers:{
          "Content-Type":"application/octet-stream",
          "X-Pausio-Client":"studio",
          "X-Filename":encodeURIComponent(file.name),
          "X-Pausio-Revision":String(revision),
          "X-Pausio-Start-Ms":String(anchor)
        }
      });
      let data;
      try{data=await response.json();}catch{throw Error("Risposta immagine non valida.");}
      if(!response.ok)throw Error(data.error||"Import immagine non riuscito.");
      update(data);
      toast("Immagine B-roll salvata nel progetto. Genera una preview FFmpeg per vederla.");
    }finally{
      sending=false;draw();
      el("pip-image-input").value="";
    }
  }
  el("pip-image-import").addEventListener("click",()=>el("pip-image-input").click());
  el("pip-image-input").addEventListener("change",()=>run(
    ()=>importImage(el("pip-image-input").files?.[0])
  ));
  el("pip-image-preview").addEventListener("click",()=>run(()=>startJob("preview")));
  window.pausioImages={update:draw};
  if(project)draw();
})();
