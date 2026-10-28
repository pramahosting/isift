import React,{useEffect,useRef,useState} from 'react';
import {Download,LoaderCircle} from 'lucide-react';

/** One Download button that opens a short list of formats (PDF, the original Word / Excel / PowerPoint file, and so on). */
export function DownloadMenu({items,label}:{items:{label:string;run:()=>Promise<void>}[];label:string}){
  const [open,setOpen]=useState(false);const [busy,setBusy]=useState('');const [err,setErr]=useState('');const box=useRef<HTMLSpanElement>(null);
  useEffect(()=>{if(!open)return;const h=(e:MouseEvent)=>{if(box.current&&!box.current.contains(e.target as Node))setOpen(false)};document.addEventListener('mousedown',h);return()=>document.removeEventListener('mousedown',h)},[open]);
  const go=async(it:{label:string;run:()=>Promise<void>})=>{setErr('');setBusy(it.label);try{await it.run();setOpen(false)}catch(e:any){setErr(e?.message||'The file could not be created.')}finally{setBusy('')}};
  return <span className="dlmenu" ref={box}>
    <button type="button" className="iconbtn" title={label} aria-label={label} aria-haspopup="menu" aria-expanded={open} onMouseDown={e=>e.preventDefault()} onClick={()=>setOpen(o=>!o)}>{busy?<LoaderCircle size={16} className="spin"/>:<Download size={16}/>}</button>
    {open&&<div className="dlmenu-pop" role="menu" aria-label={label}><b>Download as</b>
      {items.map(it=><button key={it.label} type="button" role="menuitem" disabled={!!busy} onClick={()=>go(it)}>{busy===it.label?'Preparing…':it.label}</button>)}
      {err&&<p className="syncerr" role="alert">{err}</p>}</div>}
  </span>;
}
