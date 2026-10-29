import React,{useEffect,useState} from 'react';
import {X,Info} from 'lucide-react';
// One place that tells the person, in plain words, when something did not work. Nothing should fail silently.
export function help(message:string,title?:string){try{window.dispatchEvent(new CustomEvent('isift:help',{detail:{message,title}}))}catch{}}
export function HelpToaster(){
  const [t,setT]=useState<{message:string;title?:string;id:number}|null>(null);
  useEffect(()=>{let n=0,last=0;
    const show=(e:Event)=>{const d=(e as CustomEvent).detail||{};setT({message:d.message,title:d.title,id:++n})};
    const guard=(m:string)=>{const now=Date.now();if(now-last<6000)return;last=now;help(m)};
    const rej=(e:PromiseRejectionEvent)=>{const r:any=e.reason;const nm=String(r?.name||''),msg=String(r?.message||r||'');
      if(nm==='AbortError'||/ResizeObserver|play\(\)|The play request|interrupted by/i.test(msg))return;
      if(/Failed to fetch|NetworkError|Load failed|network/i.test(msg))guard('iSift could not reach the server. Check your internet connection, then try again.');
      else if(nm==='NotAllowedError')guard('Your browser blocked that. Allow camera, microphone or screen access for this site in the browser address bar, then try again.');
      else guard('Something did not work as expected. Please try once more. If it keeps happening, reload the page.')};
    const off=()=>help('You are offline. iSift will carry on when your internet connection is back.','No internet');
    window.addEventListener('isift:help',show);window.addEventListener('unhandledrejection',rej);window.addEventListener('offline',off);
    return()=>{window.removeEventListener('isift:help',show);window.removeEventListener('unhandledrejection',rej);window.removeEventListener('offline',off)}},[]);
  useEffect(()=>{if(!t)return;const x=setTimeout(()=>setT(null),12000);return()=>clearTimeout(x)},[t]);
  if(!t)return null;
  return <div className="helptoast" role="alert"><Info size={18}/><div>{t.title&&<b>{t.title}</b>}<p>{t.message}</p></div><button type="button" aria-label="Close message" onClick={()=>setT(null)}><X size={16}/></button></div>;
}
