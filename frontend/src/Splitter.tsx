import React,{useState} from 'react';

/** A drag handle (mouse, touch or arrow keys) that remembers its width. `invert` is for a handle on the left edge of the pane it sizes. */
export function useSplit(key:string,def:number,lo:number,hi:number,invert=false){
  const clamp=(n:number)=>Math.min(hi,Math.max(lo,n));
  const [w,setW]=useState<number>(()=>{try{return clamp(Number(localStorage.getItem(key))||def)}catch{return def}});
  const save=(n:number)=>{try{localStorage.setItem(key,String(n))}catch{}};
  const onPointerDown=(e:React.PointerEvent)=>{e.preventDefault();const x0=e.clientX,w0=w,sg=invert?-1:1;
    const mv=(ev:PointerEvent)=>setW(clamp(w0+sg*(ev.clientX-x0)));
    const up=(ev:PointerEvent)=>{window.removeEventListener('pointermove',mv);window.removeEventListener('pointerup',up);document.body.style.userSelect='';save(clamp(w0+sg*(ev.clientX-x0)))};
    document.body.style.userSelect='none';window.addEventListener('pointermove',mv);window.addEventListener('pointerup',up)};
  const onKeyDown=(e:React.KeyboardEvent)=>{const d=e.key==='ArrowLeft'?-20:e.key==='ArrowRight'?20:0;if(!d)return;e.preventDefault();const n=clamp(w+(invert?-d:d));setW(n);save(n)};
  const onDoubleClick=()=>{setW(def);save(def)};
  return {w,handle:{className:'ol-rz',role:'separator','aria-orientation':'vertical' as const,tabIndex:0,title:'Drag to resize. Double-click to reset.',onPointerDown,onKeyDown,onDoubleClick}};
}
