import React,{useCallback,useEffect,useRef,useState} from 'react';
import {Phone,PhoneOff,PhoneIncoming,X} from 'lucide-react';

/** Calling other iSift users, like a phone call: press Call, type who, they get a ringing pop-up, both land in a private room.
 *  One small websocket per signed-in tab carries the ringing; the call itself is an ordinary two-person meeting room. */
type Who={name:string;email:string};
const wsUrl=(api:string)=>{const base=api.startsWith('http')?api:location.origin+api;return base.replace(/^http/,'ws')+'/ws/calls'};

function useRing(on:boolean){
  useEffect(()=>{
    if(!on)return;let ctx:AudioContext|null=null,t:any=null;
    try{ctx=new (window.AudioContext||(window as any).webkitAudioContext)();const beep=()=>{if(!ctx)return;const o=ctx.createOscillator(),g=ctx.createGain();o.frequency.value=440;g.gain.value=0.08;o.connect(g);g.connect(ctx.destination);o.start();o.stop(ctx.currentTime+0.35)};beep();t=setInterval(beep,1800)}catch{}
    return()=>{clearInterval(t);try{ctx?.close()}catch{}};
  },[on]);
}

const RKEY='isift.recentcalls';
export function recentCalled():{email:string;name:string;at:number}[]{try{return JSON.parse(localStorage.getItem(RKEY)||'[]')}catch{return []}}
function rememberCalled(email:string,name:string){try{const l=recentCalled().filter(x=>x.email!==email);l.unshift({email,name,at:Date.now()});localStorage.setItem(RKEY,JSON.stringify(l.slice(0,10)));window.dispatchEvent(new Event('isift:recent'))}catch{}}

/** The Phone page in the left menu: type an address or tap a contact to ring them. The ringing itself is handled by CallLayer. */
export function PhonePage({request,canCall}:{request:any;canCall:boolean}){
  const [contacts,setContacts]=useState<any[]>([]),[q,setQ]=useState(''),[recent,setRecent]=useState(recentCalled());
  useEffect(()=>{request('/contacts').then((l:any)=>setContacts(Array.isArray(l)?l.filter((c:any)=>c.email):[])).catch(()=>{})},[request]);
  useEffect(()=>{const f=()=>setRecent(recentCalled());window.addEventListener('isift:recent',f);return()=>window.removeEventListener('isift:recent',f)},[]);
  const ring=(email:string)=>window.dispatchEvent(new CustomEvent('isift:call',{detail:{to:email}}));
  const list=contacts.filter(c=>!q.trim()||`${c.name||''} ${c.email}`.toLowerCase().includes(q.trim().toLowerCase())).slice(0,60);
  const ok=/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(q.trim());
  return <div className="phone-page">
    {!canCall&&<div className="panel pad"><p className="muted">Calling other people is part of the Individual and Business plans. You can still receive calls here. Upgrade your plan, or ask an administrator to allow it for you.</p></div>}
    <section className="panel"><div className="panelhead"><h2><Phone size={18}/> Call someone</h2></div>
      <p className="muted pad small">Type an iSift email address or pick a contact. They must be signed in to iSift right now; they get a ringing pop-up and, when they accept, you both land in a private two-person room.</p>
      <div className="phone-dial pad"><input type="search" placeholder="Search contacts or type an email" value={q} onChange={e=>setQ(e.target.value)} aria-label="Search contacts or type an email"/><button className="primary" disabled={!canCall||!ok} onClick={()=>ring(q.trim())}><Phone size={15}/> Call</button></div></section>
    {recent.length>0&&<section className="panel"><div className="panelhead"><h2>Recent</h2></div>{recent.map(r=><div key={r.email} className="phone-row"><div><b>{r.name||r.email}</b><small className="muted"> {r.email}</small></div><button className="secondary" disabled={!canCall} onClick={()=>ring(r.email)} aria-label={`Call ${r.name||r.email}`}><Phone size={14}/> Call</button></div>)}</section>}
    <section className="panel"><div className="panelhead"><h2>Contacts</h2></div>{list.length?list.map(c=><div key={c.id||c.email} className="phone-row"><div><b>{c.name||c.email}</b>{c.name&&<small className="muted"> {c.email}</small>}</div><button className="secondary" disabled={!canCall} onClick={()=>ring(c.email)} aria-label={`Call ${c.name||c.email}`}><Phone size={14}/> Call</button></div>):<p className="muted pad">{contacts.length?'No contact matches.':'No contacts yet. Add people under Commbox, or type an email above.'}</p>}</section>
  </div>;
}

export function CallLayer({token,request,api,canCall,children}:{token:string;request:any;api:string;canCall:boolean;children?:React.ReactNode}){
  const [open,setOpen]=useState(false),[to,setTo]=useState(''),[err,setErr]=useState(''),[busy,setBusy]=useState(false);
  const [out,setOut]=useState<{id:string;name:string}|null>(null);
  const [inc,setInc]=useState<{id:string;code:string;from:Who;until:number}|null>(null);
  const [sugg,setSugg]=useState<string[]>([]);const [note,setNote]=useState('');
  const outRef=useRef(out);outRef.current=out;
  useRing(!!inc||!!out);
  const placeRef=useRef<(who:string)=>void>(()=>{});
  useEffect(()=>{const f=(e:any)=>{const who=e?.detail?.to;if(who)placeRef.current(who);else{setErr('');setOpen(true)}};window.addEventListener('isift:call',f);return()=>window.removeEventListener('isift:call',f)},[]);     // the Dashboard tile opens the same box
  const go=(code:string)=>{setOut(null);setInc(null);setOpen(false);location.hash=`#/room/${code}`};

  useEffect(()=>{
    if(!token)return;let sock:WebSocket|null=null,alive=true,ping:any=null,retry:any=null,tries=0;
    const connect=()=>{
      sock=new WebSocket(wsUrl(api));
      sock.onopen=()=>{tries=0;sock!.send(JSON.stringify({type:'auth',token}));ping=setInterval(()=>{try{sock!.send('{"type":"ping"}')}catch{}},25000)};
      sock.onmessage=ev=>{let m:any;try{m=JSON.parse(ev.data)}catch{return}
        if(m.type==='incoming')setInc({id:m.call_id,code:m.code,from:m.from,until:Date.now()+(m.seconds||45)*1000});
        else if(m.type==='ended')setInc(c=>c&&c.id===m.call_id?null:c);
        else if(m.type==='accepted'&&outRef.current?.id===m.call_id)go(m.code);
        else if(m.type==='declined'&&outRef.current?.id===m.call_id){setOut(null);setNote(`${m.by?.name||'They'} declined the call.`)}
        else if(m.type==='missed'&&outRef.current?.id===m.call_id){setOut(null);setNote('No answer.')}};
      sock.onclose=()=>{clearInterval(ping);if(alive){retry=setTimeout(connect,Math.min(30000,2000*2**tries++))}};
    };
    connect();
    return()=>{alive=false;clearInterval(ping);clearTimeout(retry);try{sock?.close()}catch{}};
  },[token,api]);

  useEffect(()=>{if(!note)return;const t=setTimeout(()=>setNote(''),5000);return()=>clearTimeout(t)},[note]);
  useEffect(()=>{if(!open)return;request('/contacts').then((l:any)=>setSugg((Array.isArray(l)?l:[]).map((c:any)=>c.email).filter(Boolean).slice(0,200))).catch(()=>{})},[open]);

  const dial=async(who:string,fromBox:boolean)=>{setErr('');setBusy(true);
    try{const r=await request('/calls',{method:'POST',body:JSON.stringify({to:who.trim(),base_url:location.origin+location.pathname})});setOut({id:r.call_id,name:r.to.name});setOpen(false);setTo('');rememberCalled(who.trim(),r.to.name)}
    catch(x:any){if(fromBox)setErr(x.message||'Could not place the call.');else setNote(x.message||'Could not place the call.')}finally{setBusy(false)}};
  const place=(e?:React.FormEvent)=>{e?.preventDefault();dial(to,true)};
  placeRef.current=who=>{dial(who,false)};
  const hangUp=async()=>{const c=out;setOut(null);if(c)try{await request(`/calls/${c.id}/cancel`,{method:'POST'})}catch{}};
  const answer=async(accept:boolean)=>{const c=inc;setInc(null);if(!c)return;try{const r=await request(`/calls/${c.id}/answer`,{method:'POST',body:JSON.stringify({accept})});if(accept&&r.code)go(r.code)}catch(x:any){setNote(x.message||'This call has ended.')}};

  return <>
    <button type="button" className="callbtn" title={canCall?'Call someone':'Calling is part of the Individual and Business plans'} aria-label="Call someone" onClick={()=>{setErr('');setOpen(true)}}><Phone size={16}/> <span>Call</span></button>
    {children}
    {open&&<div className="call-modal" role="dialog" aria-label="Call someone"><form className="call-card" onSubmit={place}>
      <div className="call-head"><b>Call someone</b><button type="button" className="iconbtn" aria-label="Close" onClick={()=>setOpen(false)}><X size={16}/></button></div>
      {!canCall?<p className="muted">Calling other people is part of the Individual and Business plans. You can still receive calls. Upgrade your plan, or ask an administrator to allow it for you.</p>:<>
      <label>Their iSift email<input type="email" list="call-sugg" value={to} onChange={e=>setTo(e.target.value)} placeholder="name@company.com" autoFocus required/></label>
      <datalist id="call-sugg">{sugg.map(s=><option key={s} value={s}/>)}</datalist>
      <p className="muted small">They must be signed in to iSift right now. The call opens a private two-person room.</p>
      {err&&<div className="alert" role="alert">{err}</div>}
      <div className="actions"><button className="primary" disabled={busy||!to.trim()}><Phone size={15}/> {busy?'Calling…':'Call'}</button><button type="button" className="secondary" onClick={()=>setOpen(false)}>Cancel</button></div></>}
    </form></div>}
    {out&&<div className="call-toast out" role="status"><Phone size={18}/><div><b>Calling {out.name}…</b><small>Waiting for them to answer</small></div><button type="button" className="call-end" aria-label="Hang up" onClick={hangUp}><PhoneOff size={16}/></button></div>}
    {inc&&<div className="call-toast in" role="alertdialog" aria-label="Incoming call"><PhoneIncoming size={20}/><div><b>{inc.from.name}</b><small>is calling you</small></div>
      <button type="button" className="call-end" aria-label="Decline" onClick={()=>answer(false)}><PhoneOff size={16}/></button><button type="button" className="call-ok" aria-label="Accept" onClick={()=>answer(true)}><Phone size={16}/></button></div>}
    {note&&<div className="call-toast note" role="status">{note}</div>}
  </>;
}
