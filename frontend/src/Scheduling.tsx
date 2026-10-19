import {DayPreset} from './DayPreset';
import React,{useCallback,useEffect,useMemo,useState} from 'react';
import {Sparkles,Mail,Send,CalendarPlus,Copy,Trash2,Pencil,Plus,Video,Clock3,ChevronRight,ChevronLeft,Check,Globe,X,ExternalLink} from 'lucide-react';
import {Modal} from './Workspace';

const baseUrl=()=>location.origin+location.pathname;
export const bookLink=(slug:string)=>`${baseUrl()}#/book/${slug}`;
const DAYS=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
const zones=():string[]=>{try{const f=(Intl as any).supportedValuesOf;if(f)return f('timeZone')}catch{}return ['UTC','Australia/Sydney','Australia/Melbourne','Asia/Kolkata','Europe/London','America/New_York','America/Los_Angeles']};
const myZone=()=>{try{return Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC'}catch{return 'UTC'}};
const dayKey=(d:Date|string,tz:string)=>new Intl.DateTimeFormat('en-CA',{timeZone:tz,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(d));
const timeText=(d:Date|string,tz:string)=>new Date(d).toLocaleTimeString(undefined,{timeZone:tz,hour:'numeric',minute:'2-digit'});
const longText=(d:Date|string,tz:string)=>new Date(d).toLocaleString(undefined,{timeZone:tz,weekday:'long',day:'numeric',month:'long',year:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'});

async function call(api:string,path:string,opts:any={}){
  let r:Response;try{r=await fetch(api+path,{...opts,headers:{'Content-Type':'application/json',...(opts.headers||{})}})}catch{throw new Error('Cannot reach the server. Check your connection and try again.')}
  let d:any={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.detail||`Request failed (${r.status})`);return d;
}

/* ---------------- shared: month calendar + time list ---------------- */
function Picker({api,slug,duration,tz,onPick,skipNote}:{api:string;slug:string;duration:number;tz:string;onPick:(iso:string)=>void;skipNote?:string}){
  const [month,setMonth]=useState(()=>{const n=new Date();return new Date(n.getFullYear(),n.getMonth(),1)});
  const [day,setDay]=useState('');const [err,setErr]=useState('');
  const mk=`${month.getFullYear()}-${String(month.getMonth()+1).padStart(2,'0')}`;
  const [raw,setRaw]=useState<string[]>([]);
  useEffect(()=>{let on=true;const a=new Date(month.getFullYear(),month.getMonth(),1),b=new Date(month.getFullYear(),month.getMonth()+1,0);const f=(d:Date)=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    call(api,`/public/book/${slug}/slots?start=${f(a)}&end=${f(b)}`).then(r=>{if(on){setRaw(r.slots);setErr('')}}).catch(e=>{if(on)setErr(e.message)});return()=>{on=false}},[mk,slug,api,skipNote]);
  const byDay=useMemo(()=>{const m:Record<string,string[]>={};for(const iso of raw){const k=dayKey(iso,tz);(m[k]=m[k]||[]).push(iso)}return m},[raw,tz]);
  const first=new Date(month.getFullYear(),month.getMonth(),1),offset=(first.getDay()+6)%7,count=new Date(month.getFullYear(),month.getMonth()+1,0).getDate();
  const cells:(number|null)[]=[...Array(offset).fill(null),...Array.from({length:count},(_,i)=>i+1)];
  const keyOf=(d:number)=>`${month.getFullYear()}-${String(month.getMonth()+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
  const times=(byDay[day]||[]).sort();
  return <div className="bk-pick">
    <div className="bk-cal"><div className="bk-calhead"><button type="button" className="iconbtn" aria-label="Previous month" onClick={()=>setMonth(new Date(month.getFullYear(),month.getMonth()-1,1))}><ChevronLeft size={18}/></button><b>{month.toLocaleDateString(undefined,{month:'long',year:'numeric'})}</b><button type="button" className="iconbtn" aria-label="Next month" onClick={()=>setMonth(new Date(month.getFullYear(),month.getMonth()+1,1))}><ChevronRight size={18}/></button></div>
      <div className="bk-grid">{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(d=><small key={d}>{d}</small>)}{cells.map((d,i)=>d===null?<span key={i}/>:<button type="button" key={i} disabled={!byDay[keyOf(d)]} className={`bk-day${day===keyOf(d)?' on':''}${byDay[keyOf(d)]?' has':''}`} onClick={()=>setDay(keyOf(d))} aria-label={`${month.toLocaleDateString(undefined,{month:'long'})} ${d}${byDay[keyOf(d)]?', times available':', no times'}`}>{d}</button>)}</div>
      {!Object.keys(byDay).length&&!err&&<p className="muted small">Looking for free times…</p>}{err&&<p className="syncerr" role="alert">{err}</p>}</div>
    <div className="bk-times" aria-live="polite">{day?<><b>{new Date(day+'T12:00:00').toLocaleDateString(undefined,{weekday:'long',day:'numeric',month:'long'})}</b>{times.map(t=><button type="button" key={t} className="bk-time" onClick={()=>onPick(t)}>{timeText(t,tz)}</button>)}</>:<p className="muted">Pick a highlighted day to see times.</p>}</div>
  </div>;
}

function ZonePick({tz,setTz}:{tz:string;setTz:(z:string)=>void}){
  const list=useMemo(()=>{const l=zones();return l.includes(tz)?l:[tz,...l]},[tz]);
  return <label className="bk-zone"><Globe size={14}/><select value={tz} onChange={e=>setTz(e.target.value)} aria-label="Your time zone">{list.map(z=><option key={z} value={z}>{z.replace(/_/g,' ')}</option>)}</select></label>;
}

/* ---------------- the public page a guest sees ---------------- */
/** "Close this window": browsers only allow a script to close a tab it opened, so if that is refused we say so plainly. */
function CloseWindow(){
  const [stuck,setStuck]=useState(false);
  const close=()=>{try{window.close()}catch{}setTimeout(()=>setStuck(true),250)};
  return <div className="bk-close"><button type="button" className="secondary" onClick={close}><X size={14}/> Close this window</button>{stuck&&<p className="muted small" role="status">Your browser would not close this tab by itself. Everything is saved, so you can close the tab yourself.</p>}</div>}

export function BookingPublic({slug,api,email='',name='',embed=false}:{slug:string;api:string;email?:string;name?:string;embed?:boolean}){
  const [info,setInfo]=useState<any>(null);const [err,setErr]=useState('');const [tz,setTz]=useState(myZone());const [pick,setPick]=useState('');
  const [f,setF]=useState({name:name,email:email,note:''});

const [busy,setBusy]=useState(false);const [done,setDone]=useState<any>(null);
  useEffect(()=>{call(api,`/public/book/${slug}`).then(setInfo).catch(e=>setErr(e.message))},[api,slug]);
  useEffect(()=>{if(!embed)return;const send=()=>{try{window.parent.postMessage({type:'isift:resize',height:document.documentElement.scrollHeight},'*')}catch{}};send();const ro=new ResizeObserver(send);ro.observe(document.body);return()=>ro.disconnect()},[embed,pick,done,info]);
    useEffect(()=>{if(embed&&done)try{window.parent.postMessage({type:'isift:booked',booking:{slug,start_at:done.start_at,join_url:done.join_url,token:done.token}},'*')}catch{}},[embed,done]);
  const book=async(e:React.FormEvent)=>{e.preventDefault();setErr('');setBusy(true);try{setDone(await call(api,`/public/book/${slug}`,{method:'POST',body:JSON.stringify({...f,start:pick,timezone:tz,base_url:baseUrl()})}))}catch(x:any){setErr(x.message);if(/taken|available/i.test(x.message))setPick('')}finally{setBusy(false)}};
  if(err&&!info)return <div className="bk-page"><div className="bk-card narrow"><h1>Booking page not found</h1><p className="muted">{err}</p></div></div>;
  if(!info)return <div className="bk-page"><div className="bk-card narrow"><p className="muted">Loading…</p></div></div>;
  if(done)return <div className={`bk-page${embed?' bk-embed':''}`}><div className="bk-card narrow bk-done"><span className="bk-check"><Check size={26}/></span><h1>You are booked</h1>
    <p><b>{info.title}</b> with {info.host}</p><p className="bk-when"><Clock3 size={15}/> {longText(done.start_at,tz)}</p>
    <p className="muted small">{done.email==='sent'?`A confirmation with the link was emailed to ${f.email}.`:'Save the links below. No confirmation email was sent.'}</p>
    <div className="actions"><a className="primary btn" href={done.join_url}><Video size={16}/> Join link</a><a className="secondary btn" href={`${api}/public/booking/${done.token}/ics`}><CalendarPlus size={16}/> Add to calendar</a></div>
    <p className="muted small">Need to change it? <a href={`#/booking/${done.token}`}>Cancel or reschedule</a></p><CloseWindow/></div></div>;
  return <div className={`bk-page${embed?' bk-embed':''}`}><div className={`bk-card${pick?' two':' three'}`}>
    <aside className="bk-side"><small className="muted">{info.host}</small><h1>{info.title}</h1><p className="bk-dur"><Clock3 size={15}/> {info.duration_minutes} minutes</p><p className="bk-dur"><Video size={15}/> Video call link, no install</p>{info.description&&<p className="muted">{info.description}</p>}<ZonePick tz={tz} setTz={setTz}/></aside>
    {!pick?<Picker api={api} slug={slug} duration={info.duration_minutes} tz={tz} onPick={setPick}/>
    :<form className="bk-form" onSubmit={book}><button type="button" className="linkbtn" onClick={()=>{setPick('');setErr('')}}><ChevronLeft size={15}/> Choose another time</button>
      <p className="bk-when"><Clock3 size={15}/> {longText(pick,tz)}</p>
      <label>Your name<input value={f.name} onChange={e=>setF({...f,name:e.target.value})} required autoFocus autoComplete="name" maxLength={200}/></label>
      <label>Email<input type="email" value={f.email} onChange={e=>setF({...f,email:e.target.value})} required autoComplete="email"/></label>
      <label>Anything to share beforehand? (optional)<textarea rows={3} value={f.note} onChange={e=>setF({...f,note:e.target.value})} maxLength={1000}/></label>
      {err&&<p className="syncerr" role="alert">{err}</p>}
      <div className="actions"><button className="primary" disabled={busy||!f.name.trim()||!f.email.trim()}>{busy?'Booking…':'Confirm booking'}</button></div></form>}
  </div></div>;
}

/* ---------------- guest: cancel or reschedule with the private link ---------------- */
export function BookingManage({token,api}:{token:string;api:string}){
  const [b,setB]=useState<any>(null);const [err,setErr]=useState('');const [tz,setTz]=useState(myZone());const [mode,setMode]=useState<''|'resched'|'cancel'>('');const [msg,setMsg]=useState('');const [busy,setBusy]=useState(false);
  const load=useCallback(()=>call(api,`/public/booking/${token}`).then(setB).catch(e=>setErr(e.message)),[api,token]);useEffect(()=>{load()},[load]);
  if(err&&!b)return <div className="bk-page"><div className="bk-card narrow"><h1>Booking not found</h1><p className="muted">{err}</p></div></div>;
  if(!b)return <div className="bk-page"><div className="bk-card narrow"><p className="muted">Loading…</p></div></div>;
  const doCancel=async()=>{setBusy(true);setErr('');try{await call(api,`/public/booking/${token}/cancel`,{method:'POST',body:JSON.stringify({base_url:baseUrl()})});setMode('');setMsg('Your booking was cancelled.');load()}catch(x:any){setErr(x.message)}finally{setBusy(false)}};
  const resched=async(iso:string)=>{setBusy(true);setErr('');try{await call(api,`/public/booking/${token}/reschedule`,{method:'POST',body:JSON.stringify({start:iso,base_url:baseUrl()})});setMode('');setMsg('Your booking was moved. The same link still works.');load()}catch(x:any){setErr(x.message)}finally{setBusy(false)}};
  return <div className="bk-page"><div className={`bk-card${mode==='resched'?' two':' narrow'}`}>
    <aside className="bk-side"><small className="muted">{b.host}</small><h1>{b.title}</h1><p className="bk-dur"><Clock3 size={15}/> {b.duration_minutes} minutes</p>{b.status==='booked'&&<p className="bk-when">{longText(b.start_at,tz)}</p>}<ZonePick tz={tz} setTz={setTz}/>
      {b.status==='cancelled'&&<p className="badge red">Cancelled</p>}{msg&&<p className="syncok" role="status">{msg}</p>}{err&&<p className="syncerr" role="alert">{err}</p>}</aside>
    {mode==='resched'?<div><button type="button" className="linkbtn" onClick={()=>setMode('')}><ChevronLeft size={15}/> Back</button><Picker api={api} slug={b.slug} duration={b.duration_minutes} tz={tz} onPick={resched} skipNote={String(busy)}/></div>
    :<div className="bk-manage">{b.status==='booked'&&!b.past?<><p>Hello {b.guest_name}. Your meeting is booked.</p>
      <div className="actions"><a className="primary btn" href={b.join_url}><Video size={16}/> Join link</a><a className="secondary btn" href={`${api}/public/booking/${token}/ics`}>Add to calendar</a></div>
      <div className="actions"><button className="secondary" onClick={()=>{setMode('resched');setMsg('')}}>Reschedule</button>{mode==='cancel'?<><button className="danger" disabled={busy} onClick={doCancel}>Yes, cancel it</button><button className="secondary" onClick={()=>setMode('')}>Keep it</button></>:<button className="secondary" onClick={()=>{setMode('cancel');setMsg('')}}>Cancel booking</button>}</div></>
      :b.status==='cancelled'?<>{b.can_rebook&&<div className="actions"><a className="primary btn" href={`#/book/${b.slug}`}>Book a new time</a></div>}</>:<p className="muted">This meeting has already happened.</p>}<CloseWindow/></div>}
  </div></div>;
}

/* ---------------- the owner's Scheduling page ---------------- */
const emptyHours=()=>Object.fromEntries([0,1,2,3,4].map(d=>[String(d),[['09:00','17:00']]]));
function TypeEditor({init,request,onClose,onSaved}:{init:any;request:any;onClose:()=>void;onSaved:()=>void}){
  const [f,setF]=useState<any>(init?{...init}:{title:'',description:'',duration_minutes:30,buffer_minutes:0,min_notice_hours:4,days_ahead:30,timezone:myZone(),availability:emptyHours(),slug:''});
  const [err,setErr]=useState('');const [busy,setBusy]=useState(false);
  const [co,setCo]=useState<any>(null);const [me,setMe]=useState('');const [team,setTeam]=useState<string[]>(init?.team_members||[]);
  useEffect(()=>{request('/account').then((a:any)=>{setCo(a?.company||null);setMe((a?.user?.email||'').toLowerCase())}).catch(()=>setCo(null))},[request]);
  const av=f.availability||{};const setSpans=(d:number,spans:string[][])=>{const n={...av};if(spans.length)n[String(d)]=spans;else delete n[String(d)];setF({...f,availability:n})};
  const save=async(e:React.FormEvent)=>{e.preventDefault();setErr('');setBusy(true);try{const body={...(co&&co.plan==='business'?{team_members:team}:{}),title:f.title,description:f.description,duration_minutes:+f.duration_minutes,buffer_minutes:+f.buffer_minutes,min_notice_hours:+f.min_notice_hours,days_ahead:+f.days_ahead,timezone:f.timezone,availability:f.availability,...(f.slug?{slug:f.slug}:{})};
    if(init)await request(`/booking-types/${init.id}`,{method:'PATCH',body:JSON.stringify(body)});else await request('/booking-types',{method:'POST',body:JSON.stringify(body)});onSaved()}catch(x:any){setErr(x.message)}finally{setBusy(false)}};
  return <Modal title={init?'Edit booking page':'New booking page'} onClose={onClose} wide><form className="ws-form bk-edit" onSubmit={save}>
    <label>Title<input value={f.title} onChange={e=>setF({...f,title:e.target.value})} placeholder="30 minute meeting" required autoFocus maxLength={200}/></label>
    <label>Description (shown to guests)<textarea rows={2} value={f.description} onChange={e=>setF({...f,description:e.target.value})} maxLength={2000}/></label>
    <div className="bk-row"><label>Length<select value={f.duration_minutes} onChange={e=>setF({...f,duration_minutes:e.target.value})}>{[15,20,30,45,60,90,120].map(n=><option key={n} value={n}>{n} minutes</option>)}{![15,20,30,45,60,90,120].includes(+f.duration_minutes)&&<option value={f.duration_minutes}>{f.duration_minutes} minutes</option>}</select></label>
      <label>Gap between meetings<select value={f.buffer_minutes} onChange={e=>setF({...f,buffer_minutes:e.target.value})}>{[0,5,10,15,30,60].map(n=><option key={n} value={n}>{n?`${n} minutes`:'None'}</option>)}</select></label>
      <label>Minimum notice<select value={f.min_notice_hours} onChange={e=>setF({...f,min_notice_hours:e.target.value})}>{[[0,'None'],[1,'1 hour'],[4,'4 hours'],[24,'1 day'],[48,'2 days'],[168,'1 week']].map(([n,t])=><option key={n} value={n}>{t}</option>)}</select></label>
      <label>Bookable up to<select value={f.days_ahead} onChange={e=>setF({...f,days_ahead:e.target.value})}>{[7,14,30,60,90,180].map(n=><option key={n} value={n}>{n} days ahead</option>)}</select></label></div>
    <label>Your time zone for these hours<select value={f.timezone} onChange={e=>setF({...f,timezone:e.target.value})}>{(()=>{const l=zones();return (l.includes(f.timezone)?l:[f.timezone,...l]).map(z=><option key={z} value={z}>{z.replace(/_/g,' ')}</option>)})()}</select></label>
    <fieldset className="bk-hours"><legend>Weekly hours</legend><div className="bk-preset"><DayPreset label="Quick select days" days={Object.keys(av).filter(k=>(av[k]||[]).length).map(Number)} onChange={ds=>{const tpl=Object.values(av).find((x:any)=>x&&x.length) as string[][]|undefined;const n:any={};for(const d of ds)n[String(d)]=av[String(d)]?.length?av[String(d)]:(tpl||[['09:00','17:00']]);setF({...f,availability:n})}}/></div>{DAYS.map((name,d)=>{const spans:string[][]=av[String(d)]||[];return <div key={d} className="bk-hrow"><label className="bk-dayname"><input type="checkbox" checked={spans.length>0} onChange={e=>setSpans(d,e.target.checked?[['09:00','17:00']]:[])}/> {name}</label>
      <div className="bk-spans">{spans.length?spans.map((s,i)=><div key={i} className="bk-span"><input type="time" value={s[0]} aria-label={`${name} start`} onChange={e=>setSpans(d,spans.map((x,k)=>k===i?[e.target.value,x[1]]:x))}/><span>to</span><input type="time" value={s[1]} aria-label={`${name} end`} onChange={e=>setSpans(d,spans.map((x,k)=>k===i?[x[0],e.target.value]:x))}/><button type="button" className="iconbtn" aria-label={`Remove hours on ${name}`} onClick={()=>setSpans(d,spans.filter((_,k)=>k!==i))}><X size={14}/></button></div>):<small className="muted">Unavailable</small>}
        {spans.length>0&&spans.length<4&&<button type="button" className="linkbtn" onClick={()=>setSpans(d,[...spans,['13:00','17:00']])}><Plus size={13}/> Add hours</button>}</div></div>})}</fieldset>
    {co&&<fieldset className="bk-team"><legend>Share with my team</legend>{co.plan==='business'?<>
      <p className="muted small">Pick teammates and this one link offers every time that at least one of you is free. Each booking goes to the free person with the fewest upcoming bookings, and teammates see the link under Team booking pages.</p>
      {co.members.filter((m:any)=>m.email!==me).map((m:any)=><label key={m.email} className="chk"><input type="checkbox" checked={team.includes(m.email)} disabled={m.status==='invited'} onChange={e=>setTeam(e.target.checked?[...team,m.email]:team.filter(x=>x!==m.email))}/> {m.name||m.email} <small className="muted">{m.email}{m.status==='invited'?' (not signed in yet)':''}</small></label>)}
      <p className="muted small">You are always included. Leave everyone unticked for a personal page.</p></>:<p className="muted small">Shared booking pages are part of the Business plan. Your company account is on {co.plan_name}.</p>}</fieldset>}
    <label>Link name (optional)<input value={f.slug||''} onChange={e=>setF({...f,slug:e.target.value})} placeholder="intro-call" maxLength={60}/></label>
    <p className="muted small">Free times are your weekly hours minus everything already in your iSift calendar, including Outlook and Google meetings you have pulled in. Each booking creates a video room automatically.</p>
    {err&&<p className="syncerr" role="alert">{err}</p>}
    <div className="actions"><button className="primary" disabled={busy||!f.title.trim()}>{init?'Save changes':'Create booking page'}</button><button type="button" className="secondary" onClick={onClose}>Cancel</button></div></form></Modal>;
}

function ShareModal({types,first,sender,request,onClose,notify}:{types:any[];first:any;sender:string;request:any;onClose:()=>void;notify:(m:string)=>void}){
  const [tid,setTid]=useState(first.id);const t=types.find(x=>x.id===tid)||first;const link=bookLink(t.slug);
  const [to,setTo]=useState('');const [purpose,setPurpose]=useState('');const [tone,setTone]=useState('friendly');
  const [subject,setSubject]=useState('');const [msg,setMsg]=useState('');const [drafting,setDrafting]=useState(false);const [note,setNote]=useState('');const [ai,setAi]=useState(false);
  const [busy,setBusy]=useState(false);const [err,setErr]=useState('');const [done,setDone]=useState<any>(null);const [copied,setCopied]=useState(false);
  const write=async(id=tid)=>{setDrafting(true);setErr('');try{const r=await request(`/booking-types/${id}/share-draft`,{method:'POST',body:JSON.stringify({to,purpose,tone,base_url:baseUrl()})});setSubject(r.subject);setMsg(r.body);setNote(r.note||'');setAi(!!r.ai)}catch(x:any){setErr(x.message)}finally{setDrafting(false)}};
  useEffect(()=>{write(tid)},[tid]);    // the email is written as soon as the window opens, and again when another page is chosen
  const send=async(e:React.FormEvent)=>{e.preventDefault();setErr('');setBusy(true);try{const r=await request(`/booking-types/${t.id}/share`,{method:'POST',body:JSON.stringify({to,subject,message:msg,base_url:baseUrl()})});setDone(r);notify(`Link emailed to ${r.sent.length} ${r.sent.length===1?'person':'people'}.`)}catch(x:any){setErr(x.message)}finally{setBusy(false)}};
  const copy=async()=>{try{await navigator.clipboard.writeText(link);setCopied(true);setTimeout(()=>setCopied(false),2000)}catch{window.prompt('Copy this link:',link)}};
  const mailto=`mailto:${encodeURIComponent(to.replace(/\s+/g,''))}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(msg)}`;
  return <Modal title="Share booking link" onClose={onClose} wide>
    {done?<div className="ws-form"><p><b>Handed to the mail server for:</b> {done.sent.join(', ')}</p><p className="muted small"><b>If it does not arrive:</b> check the recipient's Spam or Junk folder, and the Sent folder{done.login?` of ${done.login}`:''}. A message that is in that Sent folder was accepted by the mail server, so the problem is on the delivery side. A bounce message from the mail server may also be in that inbox.</p>{done.failed.length>0&&<p className="syncerr" role="alert">Could not send to: {done.failed.join(', ')}</p>}<div className="actions"><button className="primary" onClick={onClose}>Done</button></div></div>
    :<form className="ws-form bk-share" onSubmit={send}>
      <p className="muted small bk-from"><b>From:</b> {sender||'the app email account'} <span>· replies go to you</span></p>
      {types.length>1&&<label>Booking page<select value={tid} onChange={e=>setTid(e.target.value)}>{types.map(x=><option key={x.id} value={x.id}>{x.title} ({x.duration_minutes} min)</option>)}</select></label>}
      <label>To <small>(one or more email addresses, separated by commas)</small><input value={to} onChange={e=>setTo(e.target.value)} placeholder="name@example.com, other@example.com" autoFocus required/></label>
      <div className="bk-ai"><label>What is the meeting about? <small>(optional, helps the AI write it)</small><input value={purpose} onChange={e=>setPurpose(e.target.value)} placeholder="for example: discuss the rollout plan" maxLength={300}/></label>
        <label>Tone<select value={tone} onChange={e=>setTone(e.target.value)}><option value="friendly">Friendly</option><option value="formal">Formal</option><option value="brief">Brief</option></select></label>
        <button type="button" className="secondary" disabled={drafting} onClick={()=>write()}><Sparkles size={14}/> {drafting?'Writing…':'Write again'}</button></div>
      {note&&<p className="muted small" role="status">{note}</p>}{ai&&!drafting&&<p className="muted small">Written by the Groq AI model. Read it and change anything before you send.</p>}
      <label>Subject<input value={subject} onChange={e=>setSubject(e.target.value)} maxLength={200} disabled={drafting} required/></label>
      <label>Email<textarea rows={9} value={drafting?'Writing your email…':msg} onChange={e=>setMsg(e.target.value)} disabled={drafting} required/></label>
      <label>Booking link<span className="bk-sharelink"><input readOnly value={link} onFocus={e=>e.target.select()}/><button type="button" className="secondary" onClick={copy}><Copy size={14}/> {copied?'Copied':'Copy'}</button></span></label>
      {err&&<p className="syncerr" role="alert">{err}</p>}
      <div className="actions"><button className="primary" disabled={busy||drafting||!to.trim()||!msg.trim()}><Send size={15}/> {busy?'Sending…':'Send email'}</button><a className="secondary btnlink2" href={mailto}><Mail size={14}/> Use my email app</a><button type="button" className="secondary" onClick={onClose}>Cancel</button></div>
    </form>}
  </Modal>}

const defaultPage=async(request:any)=>{const av:any={};for(const d of [0,1,2,3,4])av[String(d)]=[['09:00','17:00']];return request('/booking-types',{method:'POST',body:JSON.stringify({title:'30 minute meeting',description:'',duration_minutes:30,buffer_minutes:0,min_notice_hours:4,days_ahead:30,timezone:myZone(),availability:av})})};

/** The Share window on its own, for the dashboard: finds (or creates) a booking page, then opens the email window. */
export function ShareLauncher({request,notify,onClose}:{request:any;notify:(m:string)=>void;onClose:()=>void}){
  const [types,setTypes]=useState<any[]|null>(null);const [sender,setSender]=useState('');const [err,setErr]=useState('');
  const ran=React.useRef(false);
  useEffect(()=>{if(ran.current)return;ran.current=true;(async()=>{try{const all=await request('/booking-types');const s=await request('/booking-senders').catch(()=>null);setSender(s?.from||'');
    let act=all.filter((x:any)=>x.active);if(!all.length)act=[await defaultPage(request)];
    if(!act.length)setErr('All your booking pages are paused. Open Meetings, Booking and turn one on.');else setTypes(act)}catch(e:any){setErr(e.message)}})()},[request]);
  if(err)return <Modal title="Share booking link" onClose={onClose}><p className="syncerr" role="alert">{err}</p><div className="actions"><button className="secondary" onClick={onClose}>Close</button></div></Modal>;
  if(!types)return <Modal title="Share booking link" onClose={onClose}><p className="muted" role="status">Getting your booking page ready…</p></Modal>;
  return <ShareModal types={types} first={types[0]} sender={sender} request={request} notify={notify} onClose={onClose}/>}

export function SchedulingPage({request,notify,onShowCalendar}:{request:any;notify:(m:string)=>void;onShowCalendar?:(iso:string)=>void}){
  const [types,setTypes]=useState<any[]>([]);const [books,setBooks]=useState<any[]>([]);const [edit,setEdit]=useState<any>(null);const [err,setErr]=useState('');const [copied,setCopied]=useState('');const [snd,setSnd]=useState<any>(null);const [share,setShare]=useState<any>(null);const [quick,setQuick]=useState(false);const [tp,setTp]=useState<any[]>([]);
  useEffect(()=>{request('/booking-senders').then(setSnd).catch(()=>setSnd(null))},[request]);
  const load=useCallback(async()=>{try{setTypes(await request('/booking-types'));setBooks(await request('/bookings'))}catch(e:any){setErr(e.message)}try{setTp((await request('/team/booking-pages')).filter((x:any)=>!x.mine))}catch{setTp([])}},[request]);useEffect(()=>{load()},[load]);
  useEffect(()=>{const t=setInterval(()=>{if(document.visibilityState==='visible')load()},20000);const f=()=>{if(document.visibilityState==='visible')load()};window.addEventListener('focus',f);document.addEventListener('visibilitychange',f);return()=>{clearInterval(t);window.removeEventListener('focus',f);document.removeEventListener('visibilitychange',f)}},[load]);   // new bookings show up on their own
  const quickStart=async()=>{setQuick(true);setErr('');try{const av:any={};for(const d of [0,1,2,3,4])av[String(d)]=[['09:00','17:00']];const t=await request('/booking-types',{method:'POST',body:JSON.stringify({title:'30 minute meeting',description:'',duration_minutes:30,buffer_minutes:0,min_notice_hours:4,days_ahead:30,timezone:myZone(),availability:av})});await load();setShare(t)}catch(e:any){setErr(e.message)}finally{setQuick(false)}};
  const copy=async(slug:string)=>{const l=bookLink(slug);try{await navigator.clipboard.writeText(l);setCopied(slug);setTimeout(()=>setCopied(''),2000)}catch{window.prompt('Copy this link:',l)}};
  const toggle=async(t:any)=>{try{await request(`/booking-types/${t.id}`,{method:'PATCH',body:JSON.stringify({active:!t.active})});load()}catch(e:any){setErr(e.message)}};
  const del=async(t:any)=>{if(!window.confirm(`Delete the booking page "${t.title}"? Its link stops working. Existing meetings are kept.`))return;try{await request(`/booking-types/${t.id}`,{method:'DELETE'});load()}catch(e:any){setErr(e.message)}};
  const cancel=async(b:any)=>{if(!window.confirm(`Cancel the meeting with ${b.guest_name}? They will be told if your mailbox is connected.`))return;try{const r=await request(`/bookings/${b.id}/cancel`,{method:'POST',body:JSON.stringify({base_url:baseUrl()})});notify(r.email==='sent'?'Cancelled and the guest was emailed.':'Cancelled. No email was sent: connect a mailbox to notify guests automatically.');load()}catch(e:any){setErr(e.message)}};
  const upcoming=books.filter(b=>b.status==='booked'&&new Date(b.end_at)>new Date()),past=books.filter(b=>!upcoming.includes(b));
  const summary=(t:any)=>{const d=Object.keys(t.availability||{}).sort().map(k=>DAYS[+k].slice(0,3));return d.join(', ')};
  return <div className="bk-owner">
    {share&&<ShareModal types={types.filter(x=>x.active)} first={share} sender={snd?.from||''} request={request} notify={notify} onClose={()=>setShare(null)}/>}
    <div className="panel"><div className="panelhead"><h2><CalendarPlus size={18}/> Booking pages</h2><div className="bk-headacts"><button className="primary" onClick={()=>setEdit({})}><Plus size={15}/> New booking page</button></div></div>
      <p className="muted pad">Share a link and let people book time with you, like Calendly or Cal.com. They pick a free time, enter their name and email, and get a video link. No account needed.</p>
      {err&&<p className="syncerr pad" role="alert">{err}</p>}
      {snd&&<p className={`pad small ${snd.count?'muted':'syncerr'}`} role="status">{snd.count?`Confirmation emails (with the video link and a calendar invite) are sent from ${snd.from}${snd.app_account?', the app email account set by your administrator':''}. Guest replies go to you.`:'No email account is set up for sending, so guests will not get a confirmation email. Ask the administrator to fill in "Email sent by the app" in Admin settings, or add a mailbox in Commbox. The booking is still saved and the video link is shown to the guest on screen.'}</p>}
      {types.length?types.map(t=><div key={t.id} className={`bk-type${t.active?'':' off'}`}><div className="grow"><b>{t.title}</b> {!t.active&&<span className="badge gray">Paused</span>}{(t.team_members||[]).length>0&&<span className="badge blue" title={(t.team_members||[]).join(", ")}>Team · {(t.team_members||[]).length+1} people</span>} <small className="muted">{t.duration_minutes} min · {summary(t)} · {t.timezone}</small><a className="bk-url" href={bookLink(t.slug)} target="_blank" rel="noreferrer">{bookLink(t.slug)} <ExternalLink size={12}/></a></div>
        <div className="bk-acts"><button className="primary" onClick={()=>setShare(t)} disabled={!t.active} title="Email this link to people"><Send size={14}/> Share</button><a className="secondary btnlink2" href={bookLink(t.slug)} target="_blank" rel="noreferrer" title="Opens the page guests see, in a new tab"><ExternalLink size={14}/> Open to test</a><button className="secondary" onClick={()=>copy(t.slug)}><Copy size={14}/> {copied===t.slug?'Copied':'Copy link'}</button><button className="secondary" onClick={()=>setEdit(t)}><Pencil size={14}/> Edit</button><button className="secondary" onClick={()=>toggle(t)}>{t.active?'Pause':'Resume'}</button><button className="iconbtn" aria-label={`Delete ${t.title}`} onClick={()=>del(t)}><Trash2 size={16}/></button></div></div>)
      :<div className="bk-first pad"><p className="muted">No booking pages yet. A booking page is the link you share; each page has its own <b>Share</b> button.</p><div className="actions"><button className="primary" disabled={quick} onClick={quickStart}><Send size={15}/> {quick?'Creating…':'Create a 30 minute page and share it'}</button><button className="secondary" onClick={()=>setEdit({})}><Plus size={15}/> Set it up myself</button></div><p className="muted small">The quick page offers Monday to Friday, 9:00 to 17:00 in your time zone. You can change it any time with Edit.</p></div>}</div>
    {tp.length>0&&<div className="panel"><div className="panelhead"><h2><Globe size={18}/> Team booking pages</h2></div><p className="muted pad">Shared pages made by your teammates. Anyone can copy the link; the owner edits the page.</p>
      {tp.map(t=><div key={t.id} className="bk-type"><div className="grow"><b>{t.title}</b> <small className="muted">{t.duration_minutes} min · by {t.owner_name} · {t.team_members.length+1} people</small><a className="bk-url" href={bookLink(t.slug)} target="_blank" rel="noreferrer">{bookLink(t.slug)} <ExternalLink size={12}/></a></div><div className="bk-acts"><button className="secondary" onClick={()=>copy(t.slug)}><Copy size={14}/> {copied===t.slug?'Copied':'Copy link'}</button></div></div>)}</div>}
    <div className="panel"><div className="panelhead"><h2><Clock3 size={18}/> Bookings</h2></div>
      {upcoming.length?upcoming.map(b=><div key={b.id} className="bk-booking"><div className="grow"><b>{b.guest_name}</b> <small className="muted">{b.guest_email}</small><br/><small>{new Date(b.start_at).toLocaleString(undefined,{weekday:'short',day:'numeric',month:'short',hour:'numeric',minute:'2-digit'})} · {b.type_title}</small>{b.guest_note&&<small className="muted"><br/>“{b.guest_note}”</small>}</div>
        <div className="bk-acts"><a className="primary btn" href={`#/room/${b.room_code}`}><Video size={14}/> Join</a>{onShowCalendar&&<button className="secondary" onClick={()=>onShowCalendar(b.start_at)}><CalendarPlus size={14}/> Show in calendar</button>}<button className="secondary" onClick={()=>cancel(b)}>Cancel</button></div></div>):<p className="muted pad">No upcoming bookings.</p>}
      {past.length>0&&<details className="pad"><summary className="muted">Recent and cancelled ({past.length})</summary>{past.map(b=><div key={b.id} className="bk-booking dim"><div className="grow"><b>{b.guest_name}</b> <small className="muted">{new Date(b.start_at).toLocaleString(undefined,{day:'numeric',month:'short',hour:'numeric',minute:'2-digit'})}</small></div>{b.status==='cancelled'&&<span className="badge red">Cancelled</span>}</div>)}</details>}</div>
    {edit&&<TypeEditor init={edit.id?edit:null} request={request} onClose={()=>setEdit(null)} onSaved={()=>{setEdit(null);load()}}/>}
  </div>;
}
