import React,{useEffect,useState} from 'react';
import {Check,X,HelpCircle,CalendarClock,CalendarPlus,Video} from 'lucide-react';

/** Where an invitation's Accept / Maybe / Decline / Suggest-another-time links land. No account needed: the link itself says who is answering. */
export function RsvpPage({token,api,first}:{token:string;api:string;first:string}){
  const [info,setInfo]=useState<any>(null);const [err,setErr]=useState('');const [pick,setPick]=useState(first);const [when,setWhen]=useState('');const [note,setNote]=useState('');
  const [busy,setBusy]=useState(false);const [done,setDone]=useState('');
  useEffect(()=>{fetch(`${api}/rsvp/${token}`).then(async r=>{const j=await r.json().catch(()=>({}));if(!r.ok)setErr(j.detail||'This reply link is not valid.');else setInfo(j)}).catch(()=>setErr('Could not reach the server.'))},[token,api]);
  const send=async(status:string)=>{setBusy(true);setErr('');try{
    const body:any={status,note};if(status==='proposed'){if(!when){setErr('Choose the day and time you suggest.');setBusy(false);return}body.proposed_start=new Date(when).toISOString()}
    const r=await fetch(`${api}/rsvp/${token}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json().catch(()=>({}));
    if(!r.ok)setErr(typeof j.detail==='string'?j.detail:'Your reply could not be sent.');else{setDone(j.message);setInfo((i:any)=>({...i,answer:{status}}))}
  }catch{setErr('Could not reach the server.')}finally{setBusy(false)}};
  const fmt=(d:string)=>new Date(d).toLocaleString(undefined,{weekday:'long',day:'numeric',month:'long',year:'numeric',hour:'numeric',minute:'2-digit'});
  if(err&&!info)return <div className="rm-center"><div className="rm-card"><h1>Invitation</h1><p>{err}</p></div></div>;
  if(!info)return <div className="rm-center"><div className="rm-card"><p>Loading…</p></div></div>;
  const cal=info.calendar||{};
  return <div className="rm-center"><div className="rm-card rsvp">
    <h1>{info.title}</h1>
    <p><b>{fmt(info.start_at)}</b><br/><span className="muted">Invited by {info.host||'the host'} · replying as {info.email}</span></p>
    {info.agenda&&<p className="muted" style={{whiteSpace:'pre-wrap'}}>{info.agenda}</p>}
    {done?<p className="ism-ok" role="status">{done}</p>:info.answer&&<p className="muted">Your last reply: <b>{({accepted:'Accepted',tentative:'Maybe',declined:'Declined',proposed:'Suggested another time'} as any)[info.answer.status]||info.answer.status}</b>. You can change it.</p>}
    <div className="actions" style={{flexWrap:'wrap'}}>
      <button className="primary" disabled={busy} onClick={()=>send('accepted')}><Check size={15}/> Accept</button>
      <button className="secondary" disabled={busy} onClick={()=>send('tentative')}><HelpCircle size={15}/> Maybe</button>
      <button className="secondary" disabled={busy} onClick={()=>send('declined')}><X size={15}/> Decline</button>
      <button className={pick==='proposed'?'primary':'secondary'} disabled={busy} onClick={()=>setPick(p=>p==='proposed'?'':'proposed')}><CalendarClock size={15}/> Suggest another time</button>
    </div>
    {pick==='proposed'&&<div className="ws-form"><label>Day and time that suits you<input type="datetime-local" value={when} onChange={e=>setWhen(e.target.value)}/></label>
      <label>Note to the host (optional)<input value={note} maxLength={500} onChange={e=>setNote(e.target.value)}/></label>
      <div className="actions"><button className="primary" disabled={busy||!when} onClick={()=>send('proposed')}>Send my suggestion</button></div></div>}
    {err&&<p className="syncerr" role="alert">{err}</p>}
    <hr/><p className="muted small"><CalendarPlus size={14}/> Add it to your calendar</p>
    <div className="actions" style={{flexWrap:'wrap'}}>
      {cal.google&&<a className="secondary btnlink" href={cal.google} target="_blank" rel="noreferrer">Google</a>}
      {cal.outlook&&<a className="secondary btnlink" href={cal.outlook} target="_blank" rel="noreferrer">Outlook.com</a>}
      {cal.office365&&<a className="secondary btnlink" href={cal.office365} target="_blank" rel="noreferrer">Microsoft 365</a>}
      {cal.yahoo&&<a className="secondary btnlink" href={cal.yahoo} target="_blank" rel="noreferrer">Yahoo</a>}
    </div>
    {info.join_url&&<><hr/><a className="primary btnlink" href={info.join_url}><Video size={15}/> Join the meeting</a></>}
  </div></div>;
}
