import React,{lazy,Suspense} from 'react';
// Wraps a screen that is downloaded only when it is first shown. Keeps the component's name and props, so call sites do not change.
export const lz=(load:()=>Promise<any>,pick:string)=>{
  const L=lazy(()=>load().then(m=>({default:m[pick]})));
  return (props:any)=><Suspense fallback={<div className="muted" style={{padding:24}}>Loading…</div>}><L {...props}/></Suspense>;
};
