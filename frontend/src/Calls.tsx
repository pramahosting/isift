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

export function CallLayer({token,request,api,canCall,children}:{token:string;request:any;api:string;canCall:boolean;children?:React.ReactNode}){
  const [open,setOpen]=useState(false),[to,setTo]=useState(''),[err,setErr]=useState(''),[busy,setBusy]=useState(false);
  const [out,setOut]=useState<{id:string;name:string}|null>(null);
  const [inc,setInc]=useState<{id:string;code:string;from:Who;until:number}|null>(null);
  const [sugg,setSugg]=useState<string[]>([]);const [note,setNote]=useState('');
  const outRef=useRef(out);outRef.current=out;
  useRing(!!inc||!!out);
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

  const place=async(e?:React.FormEvent)=>{e?.preventDefault();setErr('');setBusy(true);
    try{const r=await request('/calls',{method:'POST',body:JSON.stringify({to:to.trim(),base_url:location.origin+location.pathname})});setOut({id:r.call_id,name:r.to.name});setOpen(false);setTo('')}
    catch(x:any){setErr(x.message||'Could not place the call.')}finally{setBusy(false)}};
  const hangUp=async()=>{const c=out;setOut(null);if(c)try{await request(`/calls/${c.id}/cancel`,{method:'POST'})}catch{}};
  const answer=async(accept:boolean)=>{const c=inc;setInc(null);if(!c)return;try{const r=await request(`/calls/${c.id}/answer`,{method:'POST',body:JSON.stringify({accept})});if(accept&&r.code)go(r.code)}catch(x:any){setNote(x.message||'This call has ended.')}};

  return <>
    <button type="button" className="iconbtn" title={canCall?'Call someone':'Calling is part of the Individual and Business plans'} aria-label="Call someone" onClick={()=>{setErr('');setOpen(true)}}><Phone size={17}/></button>
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
