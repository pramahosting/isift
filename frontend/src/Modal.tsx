import React,{useEffect} from 'react';
import {X} from 'lucide-react';
export function Modal({title,onClose,children,wide}:{title:string;onClose:()=>void;children:React.ReactNode;wide?:boolean}){
  useEffect(()=>{const h=(e:KeyboardEvent)=>e.key==='Escape'&&onClose();window.addEventListener('keydown',h);return()=>window.removeEventListener('keydown',h)},[]);
  return <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><section className={`modal ws-modal${wide?' wide':''}`} role="dialog" aria-label={title}><div className="panelhead"><h2>{title}</h2><button className="iconbtn" aria-label="Close" onClick={onClose}><X size={18}/></button></div>{children}</section></div>;
}
