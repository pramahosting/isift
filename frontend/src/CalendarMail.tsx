import React,{useEffect,useState} from 'react';
import {ChevronLeft,ChevronRight,Mail,LogIn,RefreshCw,CheckCircle2,CalendarDays,Video} from 'lucide-react';
import {Modal} from './Workspace';
import {outlookSignIn,outlookError} from './Connections';

const DOW=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
const key=(d:Date)=>`${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;

/** Month calendar of every meeting in iSift (iSift rooms, Zoom/Teams/Meet and meetings pulled from your calendars). */
export function CalendarPage({meetings,onOpen,onNew,onSync}:{meetings:any[];onOpen:(id:string)=>void;onNew:()=>void;onSync:()=>void}){
  const [cur,setCur]=useState(()=>{const d=new Date();d.setDate(1);d.setHours(0,0,0,0);return d});
  const [day,setDay]=useState<Date|null>(null);
  const first=new Date(cur);const lead=(first.getDay()+6)%7;
  const start=new Date(first);start.setDate(1-lead);
  const cells=Array.from({length:42},(_,i)=>{const d=new Date(start);d.setDate(start.getDate()+i);return d});
  const by:Record<string,any[]>={};
  for(const m of meetings){if(m.status==='cancelled')continue;const k=key(new Date(m.start_at));(by[k]=by[k]||[]).push(m)}
  Object.values(by).forEach(a=>a.sort((x,y)=>+new Date(x.start_at)-+new Date(y.start_at)));
  const todayK=key(new Date());
  const t=(m:any)=>new Date(m.start_at).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});
  const shift=(n:number)=>{const d=new Date(cur);d.setMonth(d.getMonth()+n);setCur(d)};
  const dayList=day?(by[key(day)]||[]):[];
  return <section className="panel calpage">
    <div className="calbar">
      <button className="iconbtn" aria-label="Previous month" onClick={()=>shift(-1)}><ChevronLeft size={18}/></button>
      <h2>{cur.toLocaleDateString([],{month:'long',year:'numeric'})}</h2>
      <button className="iconbtn" aria-label="Next month" onClick={()=>shift(1)}><ChevronRight size={18}/></button>
      <button className="secondary" onClick={()=>{const d=new Date();d.setDate(1);d.setHours(0,0,0,0);setCur(d)}}>Today</button>
      <span className="grow"/>
      <button className="secondary" onClick={onSync}><RefreshCw size={15}/> Sync calendars</button>
      <button className="primary" onClick={onNew}><CalendarDays size={15}/> Schedule meeting</button>
    </div>
    <div className="calgrid" role="grid" aria-label="Calendar">
      {DOW.map(d=><div key={d} className="caldow" role="columnheader">{d}</div>)}
      {cells.map(d=>{const k=key(d);const ms=by[k]||[];return <div key={k} role="gridcell" className={`calcell${d.getMonth()!==cur.getMonth()?' other':''}${k===todayK?' today':''}`}>
        <button className="calnum" onClick={()=>setDay(d)} aria-label={`${d.toDateString()}, ${ms.length} meetings`}>{d.getDate()}</button>
        {ms.slice(0,3).map(m=><button key={m.id} className="calev" title={`${t(m)} ${m.title}`} onClick={()=>onOpen(m.id)}><b>{t(m)}</b> {m.title}</button>)}
        {ms.length>3&&<button className="calmore" onClick={()=>setDay(d)}>+{ms.length-3} more</button>}
      </div>})}
    </div>
    {meetings.length===0&&<p className="muted">No meetings yet. Press Sync calendars, or sign in to Outlook on the Mail page.</p>}
    {day&&<Modal title={day.toLocaleDateString([],{weekday:'long',day:'numeric',month:'long',year:'numeric'})} onClose={()=>setDay(null)}><div className="ws-form">
      {dayList.length?dayList.map(m=><button key={m.id} className="secondary calday" onClick={()=>{setDay(null);onOpen(m.id)}}><Video size={14}/> <b>{t(m)}</b> {m.title}</button>):<p className="muted">Nothing scheduled.</p>}
      <div className="actions"><button className="primary" onClick={()=>{setDay(null);onNew()}}>Schedule meeting</button></div>
    </div></Modal>}
  </section>;
}

/** Inbox of the email pulled from Outlook. */
export function EmailPage({request,isAdmin,goSettings,onPulled}:{request:any;isAdmin:boolean;goSettings:()=>void;onPulled:()=>void}){
  const [info,setInfo]=useState<any>(null);const [mail,setMail]=useState<any>(null);const [err,setErr]=useState('');const [busy,setBusy]=useState(false);const [setup,setSetup]=useState(false);const [open,setOpen]=useState<any>(null);const [msg,setMsg]=useState('');
  const load=async()=>{try{const [c,m]=await Promise.all([request('/connections'),request('/connections/microsoft/mail')]);setInfo(c.outlook||{});setMail(m)}catch(e:any){setErr(e?.message||'Could not load email.')}};
  useEffect(()=>{load()},[]);
  const connect=async()=>{
    if(!info?.ready){setSetup(true);return}
    setErr('');setMsg('');setBusy(true);
    try{const r=await outlookSignIn(info,request);setMsg(r?.message||'Done.');await load();onPulled()}catch(e:any){setErr(outlookError(e))}finally{setBusy(false)}
  };
  const desktop=async()=>{setErr('');setMsg('');setBusy(true);try{const r=await request('/connections/outlook-desktop/pull',{method:'POST'});setMsg(r?.message||'Done.');await load();onPulled()}catch(e:any){setErr(e?.message||'Outlook could not be read.')}finally{setBusy(false)}};
  const list=mail?.mail||[];
  return <section className="panel mailpage">
    <div className="panelhead"><h2><Mail size={18}/> Inbox</h2>{mail?.connected&&<span className="muted"><CheckCircle2 size={14} className="good"/> {mail.account}{mail.at?` · pulled ${new Date(mail.at).toLocaleString()}`:''}</span>}</div>
    <div className="actions"><button className="primary" disabled={busy} onClick={connect}><LogIn size={15}/> {busy?'Waiting for sign-in…':mail?.connected?'Refresh from Outlook':'Sign in to Outlook'}</button></div>
    {msg&&<p className="muted" role="status">{msg}</p>}{err&&<p className="syncerr" role="alert">{err}</p>}
    {!mail?.connected&&<p className="muted">Sign in to Outlook / Microsoft 365 in a popup. iSift then pulls your recent email here, your calendar into the Calendar and Meetings pages, and your contacts into Contacts. Your password is typed only into Microsoft’s window.</p>}
    {mail?.connected&&!list.length&&<p className="muted">No email was returned.</p>}
    {list.length>0&&<div className="maillist" role="list">{list.map((m:any,i:number)=><button key={i} role="listitem" className={`mailrow${m.read?'':' unread'}`} onClick={()=>setOpen(m)}><b className="mf">{m.from||'Unknown'}</b><span className="ms">{m.subject}</span><span className="mp">{m.preview}</span><time>{m.at?new Date(m.at).toLocaleString([],{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}):''}</time></button>)}</div>}
    {open&&<Modal title={open.subject} onClose={()=>setOpen(null)}><div className="ws-form"><p className="muted small">From {open.from||'Unknown'}{open.at?` · ${new Date(open.at).toLocaleString()}`:''}</p><p style={{whiteSpace:'pre-wrap'}}>{open.preview||'(no preview)'}</p><p className="muted small">Only the first lines are kept in iSift. Open the message in Outlook to read it all.</p></div></Modal>}
    {setup&&<Modal title="Microsoft sign-in is not set up" onClose={()=>setSetup(false)}><div className="ws-form"><p>The Microsoft sign-in popup needs an application (client) ID that has not been added in Settings yet.</p>{isAdmin?<p className="muted small">Open <b>Admin Console → Microsoft</b>, enter “Microsoft sign-in client ID” and save.</p>:<p className="muted small">Please ask your administrator to set it up under Admin Console.</p>}<div className="actions">{isAdmin&&<button className="primary" onClick={()=>{setSetup(false);goSettings()}}>Open Admin Console</button>}<button className="secondary" onClick={()=>setSetup(false)}>Close</button></div></div></Modal>}
  </section>;
}
