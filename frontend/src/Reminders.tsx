import React,{useEffect,useRef,useState} from 'react';
import {Video,X,BellRing} from 'lucide-react';

type Mt={id:string;title:string;start_at:string;end_at?:string;status?:string;join_url?:string|null};
const KEY='isift.reminded';
const when=(m:Mt)=>{const x=Math.round((new Date(m.start_at).getTime()-Date.now())/60000);return x>0?`Starts in ${x} min`:x>-1?'Starting now':`In progress, started ${-x} min ago`};
const seen=():Record<string,number>=>{try{return JSON.parse(localStorage.getItem(KEY)||'{}')}catch{return {}}};
const mark=(k:string)=>{try{const s=seen();s[k]=Date.now();for(const x of Object.keys(s))if(Date.now()-s[x]>864e5)delete s[x];localStorage.setItem(KEY,JSON.stringify(s))}catch{}};

/** iSift's own "starting soon" reminder, shown as an iSift card and, once allowed, as a desktop notification headed "iSift".
 *  It works while iSift is open (in the browser or installed as an app on the laptop). */
export function Reminders({request}:{request:any}){
  const [list,setList]=useState<Mt[]>([]);const [due,setDue]=useState<Mt[]>([]);const [perm,setPerm]=useState<string>(()=>{try{return 'Notification' in window?Notification.permission:'denied'}catch{return 'denied'}});
  const snoozed=useRef<Record<string,number>>({});
  useEffect(()=>{let on=true;const get=()=>request('/meetings').then((m:any)=>{if(on&&Array.isArray(m))setList(m)}).catch(()=>{});get();const t=setInterval(get,60000);return()=>{on=false;clearInterval(t)}},[]);
  useEffect(()=>{
    const check=()=>{const now=Date.now();const s=seen();const out:Mt[]=[];
      for(const m of list){if(m.status==='cancelled'||!m.start_at)continue;const st=new Date(m.start_at).getTime();const mins=(st-now)/60000;
        const en=m.end_at?new Date(m.end_at).getTime():st+36e5;if(mins>5||now>en)continue;if(s[m.id+'@'+m.start_at]&&!(snoozed.current[m.id]&&snoozed.current[m.id]<=now))continue;if(snoozed.current[m.id]&&snoozed.current[m.id]>now)continue;out.push(m)}
      setDue(out)};
    check();const t=setInterval(check,15000);return()=>clearInterval(t)},[list]);
  const notified=useRef<Record<string,boolean>>({});
  useEffect(()=>{if(perm!=='granted')return;for(const m of due){const k=m.id+'@'+m.start_at;if(notified.current[k])continue;notified.current[k]=true;
    try{const mins=Math.max(0,Math.round((new Date(m.start_at).getTime()-Date.now())/60000));const n=new Notification('iSift: '+m.title,{body:when(m),icon:'/icon-192.png',tag:k});n.onclick=()=>{window.focus();n.close()}}catch{}}},[due,perm]);
  const done=(m:Mt)=>{mark(m.id+'@'+m.start_at);setDue(d=>d.filter(x=>x.id!==m.id))};
  const snooze=(m:Mt)=>{snoozed.current[m.id]=Date.now()+60000;setDue(d=>d.filter(x=>x.id!==m.id))};
  const join=(m:Mt)=>{done(m);if(m.join_url){try{const u=new URL(m.join_url,location.href);if(u.origin===location.origin&&u.hash){location.hash=u.hash;return}}catch{}window.open(m.join_url,'_blank','noopener')}};
  const allow=async()=>{try{setPerm(await Notification.requestPermission())}catch{}};
  if(!due.length)return null;
  return <div className="notifalerts" role="region" aria-label="Meeting reminders">{due.slice(0,3).map(m=>{const mins=Math.max(0,Math.round((new Date(m.start_at).getTime()-Date.now())/60000));
    return <div key={m.id} className="notifcard" role="alert"><Video size={20}/><div><b>iSift: {m.title}</b><p>{when(m)}</p>
      <div className="notifact">{m.join_url&&<button type="button" className="primary" onClick={()=>join(m)}>Join</button>}<button type="button" className="secondary" onClick={()=>snooze(m)}>Snooze</button><button type="button" className="secondary" onClick={()=>done(m)}>Dismiss</button></div>
      {perm==='default'&&<button type="button" className="textbtn" onClick={allow}><BellRing size={13}/> Also show reminders as desktop notifications</button>}</div>
      <button type="button" className="iconbtn" aria-label="Dismiss" onClick={()=>done(m)}><X size={15}/></button></div>})}</div>;
}
