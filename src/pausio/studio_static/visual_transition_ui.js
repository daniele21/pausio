"use strict";
/* Source-KEEP-bound visual dips. No fabricated video handles or audio overlap.
   All output-affecting choices pass via the canonical v3/v4 event reducer. */
(() => {
  const e=id=>document.getElementById(id);
  const transitions=()=>project?.video_transitions||[];
  const makeButton=(name,callback)=>{
    const node=document.createElement("button");
    node.type="button";node.className="button button-outline";
    node.textContent=name;node.addEventListener("click",callback);return node;
  };
  const fmt=ms=>(ms/1000).toFixed(2)+"s";
  const identity=()=>crypto.randomUUID?crypto.randomUUID().replaceAll("-",""):
    [...crypto.getRandomValues(new Uint8Array(16))].map(b=>b.toString(16).padStart(2,"0")).join("");
  function update(){
    const part=segments();
    const busy=working();
    const choices=e("transition-boundary");
    const previous=choices.value;
    choices.replaceChildren();
    const occupied=new Set(transitions().map(t=>t.left_segment_id));
    for(let i=0;i<part.length-1;i++){
      const left=part[i],right=part[i+1];
      if(left.end_ms-left.start_ms<1200||right.end_ms-right.start_ms<1200)continue;
      if(occupied.has(left.id))continue;
      const o=document.createElement("option");o.value=left.id+"|"+right.id;
      o.textContent="Taglio "+(i+1)+" → "+(i+2)+" · "+
        fmt(left.end_ms)+" / "+fmt(right.start_ms);
      choices.append(o);
    }
    if([...choices.options].some(x=>x.value===previous))choices.value=previous;
    e("transition-add").disabled=!project?.plan||busy||!choices.options.length;
    choices.disabled=!project?.plan||busy||!choices.options.length;
    e("transition-duration").disabled=!project?.plan||busy;
    const list=e("transition-list");list.replaceChildren();
    for(const transition of transitions()){
      const item=document.createElement("div");
      item.className="visual-fx-entry";
      const title=document.createElement("strong");title.textContent=
        "Dip to black · "+transition.duration_ms+" ms";
      const desc=document.createElement("p");
      const idx=part.findIndex(seg=>seg.id===transition.left_segment_id);
      desc.textContent="Tra segmenti "+(idx+1)+" e "+(idx+2)+" · video soltanto, audio continuo";
      const actions=document.createElement("div");
      actions.className="visual-fx-entry-actions";
      const duration=document.createElement("select");
      for(const n of [200,300,400,600]){
        const o=document.createElement("option");o.value=String(n);
        o.textContent=n+" ms";duration.append(o);
      }
      duration.value=String(transition.duration_ms);
      duration.setAttribute("aria-label","Durata dip al taglio "+(idx+1));
      actions.append(duration);
      actions.append(makeButton("Salva",()=>run(()=>edit("video.transition.update",{
        transition:{...transition,duration_ms:Number(duration.value)}
      }))));
      actions.append(makeButton("Rimuovi",()=>run(()=>edit("video.transition.remove",{
        transition_id:transition.id
      }))));
      item.append(title,desc,actions);list.append(item);
    }
    e("transition-status").textContent=transitions().length?
      transitions().length+" transizioni manuali · nessuna modifica al tempo del parlato":
      "Nessuna transizione: i tagli restano diretti.";
    drawMarkers(part);
  }
  function drawMarkers(parts){
    const track=e("timeline-track");if(!track||!project?.media)return;
    let layer=e("transition-marks");
    if(!layer){
      layer=document.createElement("div");layer.id="transition-marks";
      layer.className="transition-marks";track.append(layer);
    }
    layer.replaceChildren();
    const mediaMs=project.media.duration_ms;
    for(const t of transitions()){
      const seg=parts.find(x=>x.id===t.left_segment_id);if(!seg)continue;
      const marker=makeButton("◊",()=>{
        e("visual-transition-panel")?.scrollIntoView({block:"nearest",behavior:"smooth"});
        e("transition-boundary")?.focus({preventScroll:true});
      });
      marker.className="transition-mark";
      marker.style.left=(seg.end_ms/mediaMs*100).toFixed(4)+"%";
      marker.title="Dip to black · "+t.duration_ms+" ms";
      marker.setAttribute("aria-label",marker.title);
      layer.append(marker);
    }
  }
  e("transition-add").addEventListener("click",()=>run(async()=>{
    const tuple=e("transition-boundary").value.split("|");
    if(tuple.length!==2)throw Error("Nessun taglio idoneo.");
    const transition={
      id:identity(),left_segment_id:tuple[0],right_segment_id:tuple[1],
      kind:"dip_black",duration_ms:Number(e("transition-duration").value)
    };
    await edit("video.transition.add",{transition});
  }));
  window.pausioVideoTransitions={update};
  if(project)update();
})();
