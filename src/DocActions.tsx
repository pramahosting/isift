import React,{useLayoutEffect,useState} from 'react';
import {createPortal} from 'react-dom';

/** Puts the Download and Print buttons of any document in one fixed place: the top right of the document header (the #doc-actions slot). Falls back to where they are written if there is no slot. */
export function DocActions({children}:{children:React.ReactNode}){
  const [el,setEl]=useState<HTMLElement|null>(null);
  useLayoutEffect(()=>{setEl(document.getElementById('doc-actions'))},[]);
  return el?createPortal(children,el):<>{children}</>;
}
