import React,{useEffect,useRef,useState} from 'react';
import {Bell,Video,X,CheckCircle2,BellRing} from 'lucide-react';
import {pushSupported,permission,needsHomeScreen,enablePush,refreshPush,disablePush,deviceOn} from './push';

type Item={id:string;kind:string;title:string;text:string;url:string;from:string;at:string;read:boolean};
const ago=(t:string)=>{const s=Math.max(0,(Date.now()-new Date(t).getTime())/1000);return s<60?'just now':s<3600?`${Math.floor(s/60)} min ago`:s<86400?`${Math.floor(s/3600)} h ago`:new Date(t).toLocaleDateString()};
const goTo=(url:string)=>{try{const u=new URL(url,location.href);if(u.origin===location.origin&&u.hash){location.hash=u.hash;return true}}catch{}return false};

/** The bell in the top bar, plus pop-up alerts for new meeting invitations ("Ann invited you to ..."). */
export function Notifications({request}:{request:any}){
  const [d,setD]=useState<{items:Item[];unread:number}>({items:[],unread:0});const [open,setOpen]=useState(false);const [hidden,setHidden]=useState<string[]>([]);
  const box=useRef<HTMLSpanElement>(null);
  const [on,setOn]=useState(false),[perm,setPerm]=useState(permission()),[pmsg,setPmsg]=useState(''),[pbusy,setPbusy]=useState(false);
  useEffect(()=>{refreshPush(request).then(()=>deviceOn().then(setOn));
    const m=(e:MessageEvent)=>{if(e.data?.type==='isift-open'){try{const u=new URL(e.data.url);if(u.hash)location.hash=u.hash}catch{}}};
    try{navigator.serviceWorker?.addEventListener('message',m)}catch{}return()=>{try{navigator.serviceWorker?.removeEventListener('message',m)}catch{}}},[]);
  // Turn alerts on without a pop-up card: on the person's first click in iSift on this device (browsers only allow the permission question after a click), ask the browser once. Already-allowed devices are registered silently above.
  useEffect(()=>{if(!pushSupported()||permission()!=='default')return;let ask=0;try{ask=Number(localStorage.getItem('isift.pushask')||0)}catch{}if(Date.now()-ask<2592e6)return;
    const go=()=>{try{localStorage.setItem('isift.pushask',String(Date.now()))}catch{}enablePush(request).then(()=>{setPerm(permission());deviceOn().then(setOn)}).catch(()=>{})};
    window.addEventListener('pointerdown',go,{once:true});return()=>window.removeEventListener('pointerdown',go)},[]);
  const turnOn=async()=>{setPbusy(true);setPmsg('');try{const w=await enablePush(request);setPmsg(w);setPerm(permission());setOn(await deviceOn())}catch(e:any){setPmsg(e?.message||'Notifications could not be turned on.')}setPbusy(false)};
  const turnOff=async()=>{setPbusy(true);await disablePush(request);setOn(false);setPmsg('Notifications are off on this device.');setPbusy(false)};
  const test=async()=>{setPmsg('');try{await request('/push/test',{method:'POST'});setPmsg('Test sent. It should appear in a few seconds.')}catch(e:any){setPmsg(e.message)}};
  const poll=()=>request('/notifications').then((r:any)=>setD(r)).catch(()=>{});
  useEffect(()=>{poll();const t=setInterval(poll,10000);const f=()=>poll();window.addEventListener('focus',f);return()=>{clearInterval(t);window.removeEventListener('focus',f)}},[]);
  useEffect(()=>{if(!open)return;const h=(e:MouseEvent)=>{if(box.current&&!box.current.contains(e.target as Node))setOpen(false)};document.addEventListener('mousedown',h);return()=>document.removeEventListener('mousedown',h)},[open]);
  const read=(ids?:string[])=>request('/notifications/read',{method:'POST',body:JSON.stringify(ids?{ids}:{all:true})}).then(poll).catch(()=>{});
  const open1=(i:Item)=>{read([i.id]);setOpen(false);if(i.url&&!goTo(i.url))window.open(i.url,'_blank','noopener')};
  const alerts=d.items.filter(i=>!i.read&&i.kind==='invite'&&!hidden.includes(i.id)).slice(0,3);
  return <>
    <span className="notif" ref={box}>
      <button type="button" className="iconbtn notifbtn" aria-label={`Alerts${d.unread?`, ${d.unread} new`:''}`} aria-expanded={open} title="Alerts" onClick={()=>setOpen(o=>!o)}><Bell size={17}/>{d.unread>0&&<i className="notifdot">{d.unread>9?'9+':d.unread}</i>}</button>
      {open&&<div className="notifmenu" role="dialog" aria-label="Alerts"><div className="notifhead"><b>Alerts</b>{d.unread>0&&<button type="button" className="textbtn" onClick={()=>read()}><CheckCircle2 size={14}/> Mark all read</button>}</div>
        {d.items.length?<ul>{d.items.map(i=><li key={i.id} className={i.read?'':'new'}><button type="button" onClick={()=>open1(i)}><b>{i.title}</b>{i.text&&<span>{i.text}</span>}<small>{ago(i.at)}{i.url?(i.kind.startsWith('share')?' · Open':' · Join'):''}</small></button></li>)}</ul>:<p className="muted small notifnone">No alerts yet. Meeting invitations show here.</p>}<div className="notifpush">{on?<><span><BellRing size={14}/> Notifications are on for this device</span><button type="button" className="textbtn" onClick={test}>Send test</button><button type="button" className="textbtn" onClick={turnOff} disabled={pbusy}>Turn off</button></>
          :perm==='denied'?<span className="muted small">Notifications are blocked for this site. Allow them in your browser settings to get alerts.</span>
          :<button type="button" className="textbtn" onClick={turnOn} disabled={pbusy}><BellRing size={14}/> Turn on notifications (meetings, invitations, email)</button>}{pmsg&&<small className="muted" role="status">{pmsg}</small>}</div></div>}
    </span>
    {alerts.length>0&&<div className="notifalerts" role="region" aria-label="Meeting invitations">{alerts.map(i=><div key={i.id} className="notifcard" role="alert"><Video size={20}/><div><b>{i.title}</b><p>{i.text}</p><div className="notifact"><button type="button" className="primary" onClick={()=>open1(i)}>Join now</button><button type="button" className="secondary" onClick={()=>{setHidden(h=>[...h,i.id]);read([i.id])}}>Dismiss</button></div></div><button type="button" className="iconbtn" aria-label="Dismiss" onClick={()=>{setHidden(h=>[...h,i.id]);read([i.id])}}><X size={15}/></button></div>)}</div>}
  </>;
}
