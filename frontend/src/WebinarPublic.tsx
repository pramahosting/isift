import React,{useEffect,useState} from 'react';
import {Presentation,CalendarPlus,Radio} from 'lucide-react';

/* Public webinar page (#/webinar/<id>): registration, and the personal-link entry that opens the room. No sign-in. */
const fmt=(iso:string)=>{try{return new Date(iso).toLocaleString(undefined,{weekday:'long',day:'numeric',month:'long',year:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'})}catch{return iso}};

export default function WebinarPublic({id,api,k,p}:{id:string;api:string;k:string;p:string}){
  const [info,setInfo]=useState<any>(null);const [err,setErr]=useState('');const [me,setMe]=useState<any>(null);
  const [name,setName]=useState('');const [email,setEmail]=useState('');const [ans,setAns]=useState<Record<string,string>>({});
  const [busy,setBusy]=useState(false);const [done,setDone]=useState<any>(null);const [gone,setGone]=useState('');
  const call=async(path:string,init?:RequestInit)=>{const r=await fetch(`${api}/webinar-public/${id}${path}`,{...init,headers:{'Content-Type':'application/json'}});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.detail||j.message||'Something went wrong.');return j};
  useEffect(()=>{call('').then(setInfo).catch(e=>setErr(e.message));if(k||p)call(`/me?${p?'p='+encodeURIComponent(p):'k='+encodeURIComponent(k)}`).then(setMe).catch(e=>setErr(e.message))},[id,k,p]);
  const enter=()=>{if(!me?.room_code)return;try{sessionStorage.setItem('isift.wb.'+me.room_code,JSON.stringify(p?{panel:p}:{reg:k}))}catch{}location.hash='#/room/'+me.room_code};
  const register=async(e:React.FormEvent)=>{e.preventDefault();setErr('');setBusy(true);try{setDone(await call('/register',{method:'POST',body:JSON.stringify({name,email,answers:ans})}))}catch(x:any){setErr(x.message)}finally{setBusy(false)}};
  const cancel=async()=>{if(!window.confirm('Cancel your registration?'))return;try{const r=await call('/cancel',{method:'POST',body:JSON.stringify({k})});setGone(r.message)}catch(x:any){setErr(x.message)}};
  const ended=info?.status!=='scheduled';
  return <div className="rm-center"><div className="rm-card wbp-card">
    <div className="wbp-brand"><Presentation size={20}/> Webinar</div>
    {!info&&!err&&<p className="muted">Loading…</p>}
    {err&&<p className="syncerr" role="alert">{err}</p>}
    {info&&<>
      <h1>{info.title}</h1>
      <p className="muted">{fmt(info.start_at)} · {info.minutes} minutes{info.host?` · hosted by ${info.host}`:''}</p>
      {info.description&&<p className="wbp-desc">{info.description}</p>}
      {info.panelists?.length>0&&<p className="small"><b>Speakers:</b> {info.panelists.join(', ')}</p>}
      {gone?<p role="status">{gone}</p>
      :info.status==='cancelled'?<p>This webinar was cancelled.</p>
      :info.status==='ended'?<p>This webinar has ended.</p>
      :(k||p)?(me?(me.status==='pending'?<p role="status">Hello {me.name}. The host has not approved your registration yet. We will email you when they do.</p>
        :me.status!=='approved'?<p>This registration is {me.status}.</p>
        :<><p>Hello {me.name}. {p?'You are a panelist: you can speak and share.':'You are registered.'}</p>
          <div className="actions"><button className="primary" onClick={enter}><Radio size={15}/> {p?'Join as panelist':'Join the webinar'}</button>
          {!p&&<a className="secondary btn" href={`${api}/webinar-public/${id}/calendar.ics?k=${encodeURIComponent(k)}`}><CalendarPlus size={14}/> Add to calendar</a>}</div>
          <p className="muted small">If the host has not started yet, you will wait in a holding screen and be let in when they go live.</p>
          {!p&&<p><button type="button" className="linkbtn" onClick={cancel}>Cancel my registration</button></p>}</>):null)
      :done?<div role="status"><p><b>{done.message}</b></p>{done.token&&<div className="actions"><button className="primary" onClick={()=>{location.hash=`#/webinar/${id}?k=${done.token}`}}>Open my personal link</button></div>}</div>
      :!info.registration?<div className="actions"><button className="primary" onClick={()=>{location.hash='#/room/'+info.room_code}}>Join the webinar</button></div>
      :info.full?<p>This webinar is full.</p>
      :<form onSubmit={register} className="ws-form">
        <label>Your name<input value={name} onChange={e=>setName(e.target.value)} required minLength={2} maxLength={200} autoComplete="name"/></label>
        <label>Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} required autoComplete="email"/></label>
        {(info.questions||[]).map((q:any)=><label key={q.id}>{q.label}{q.required?' *':''}
          {q.type==='choice'?<select value={ans[q.id]||''} onChange={e=>setAns({...ans,[q.id]:e.target.value})} required={q.required}><option value="">Choose…</option>{q.options.map((o:string)=><option key={o}>{o}</option>)}</select>
          :<input value={ans[q.id]||''} onChange={e=>setAns({...ans,[q.id]:e.target.value})} required={q.required} maxLength={300}/>}</label>)}
        <div className="actions"><button className="primary" disabled={busy}>{busy?'Registering…':'Register'}</button></div>
        <p className="muted small">{info.approval==='manual'?'The host reviews each registration. ':''}You will get a personal link by email. Your details go to the host only.</p></form>}
    </>}
  </div></div>;
}
