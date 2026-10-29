import {useEffect,useRef,useState} from 'react';
import {ChevronDown,Trash2} from 'lucide-react';

/* A drop-down list of files. Each file has a delete button at its end, so a file can be removed without opening it. */
export type PickItem={id:string;title:string;meta?:string;canDelete?:boolean};
export function FilePicker({label,items,value,onPick,onDelete,disabled}:{label:string;items:PickItem[];value:string;onPick:(id:string)=>void;onDelete:(it:PickItem)=>void;disabled?:boolean}){
  const [open,setOpen]=useState(false);const box=useRef<HTMLDivElement>(null);
  useEffect(()=>{if(!open)return;const d=(e:MouseEvent)=>{if(box.current&&!box.current.contains(e.target as Node))setOpen(false)};const k=(e:KeyboardEvent)=>{if(e.key==='Escape')setOpen(false)};document.addEventListener('mousedown',d);document.addEventListener('keydown',k);return()=>{document.removeEventListener('mousedown',d);document.removeEventListener('keydown',k)}},[open]);
  const cur=items.find(i=>i.id===value);
  return <div className="fp" ref={box}><span className="fp-label">{label}</span>
    <button type="button" className="fp-btn" aria-haspopup="listbox" aria-expanded={open} aria-label={label} disabled={disabled} onClick={()=>setOpen(o=>!o)}><span className="fp-cur">{cur?cur.title:'Choose…'}</span><ChevronDown size={16}/></button>
    {open&&<div className="fp-list" role="listbox" aria-label={label}>{items.length===0&&<p className="muted small pad">Nothing here yet.</p>}{items.map(it=><div key={it.id} className={`fp-row${it.id===value?' on':''}`} role="option" aria-selected={it.id===value}>
      <button type="button" className="fp-item" onClick={()=>{setOpen(false);onPick(it.id)}}><b>{it.title}</b>{it.meta&&<small className="muted">{it.meta}</small>}</button>
      {it.canDelete!==false&&<button type="button" className="fp-del" aria-label={`Delete ${it.title}`} title={`Delete ${it.title}`} onClick={e=>{e.stopPropagation();setOpen(false);onDelete(it)}}><Trash2 size={15}/></button>}</div>)}</div>}
  </div>;
}
