import React,{useCallback,useEffect,useState} from 'react';
import {Presentation,Plus,Copy,Check,Download,Trash2,Radio,Users,BarChart3,FileText,Mail} from 'lucide-react';
import {Modal} from './Workspace';

/* Webinars (Meetings > Webinars): schedule, invite panelists, take registrations, prepare polls, run the webinar in the meeting room, and report afterwards. */

const TZ=(()=>{try{return Intl.DateTimeFormat().resolvedOptions().timeZone||'Australia/Sydney'}catch{return 'Australia/Sydney'}})();
const fmt=(iso:string)=>{try{return new Date(iso).toLocaleString(undefined,{weekday:'short',day:'numeric',month:'short',year:'numeric',hour:'numeric',minute:'2-digit'})}catch{return iso}};
const pad=(n:number)=>String(n).padStart(2,'0');
const dateOf=(iso:string)=>{const d=new Date(iso);return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`};
const timeOf=(iso:string)=>{const d=new Date(iso);return `${pad(d.getHours())}:${pad(d.getMinutes())}`};
export function saveText(filename:string,content:string,type='text/csv'){const u=URL.createObjectURL(new Blob([content],{type:type+';charset=utf-8'}));const a=document.createElement('a');a.href=u;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),2000)}

function Copy1({value,label}:{value:string;label:string}){const [ok,setOk]=useState(false);
  return <div className="wbh-copy"><small className="muted">{label}</small><code>{value}</code><button type="button" className="secondary" aria-label={`Copy ${label}`} onClick={()=>{navigator.clipboard?.writeText(value).then(()=>{setOk(true);setTimeout(()=>setOk(false),1500)}).catch(()=>{})}}>{ok?<Check size={14}/>:<Copy size={14}/>}</button></div>}

const badge=(w:any)=>w.status==='cancelled'?['Cancelled','off']:w.status==='ended'?['Ended','off']:w.on_air?['Live','live']:w.live?['Practice','wait']:['Scheduled','ok'];

/* ---------------------------------------------------------------- the form */
function WebinarForm({w,request,onClose,onSaved}:{w?:any;request:any;onClose:()=>void;onSaved:(w:any)=>void}){
  const s=w?.settings||{};
  const [f,setF]=useState<any>(()=>({title:w?.title||'',description:w?.description||'',date:w?dateOf(w.start_at):dateOf(new Date(Date.now()+7*864e5).toISOString()),time:w?timeOf(w.start_at):'10:00',minutes:w?.minutes||60,
    registration:s.registration!==false,approval:s.approval||'auto',capacity:s.capacity||0,qa:s.qa!==false,qa_view:s.qa_view||'all',qa_anonymous:s.qa_anonymous!==false,chat:s.chat||'host',hand:s.hand!==false,practice:s.practice!==false,
    day:s.reminders?.day!==false,hour:s.reminders?.hour!==false,auto_followup:!!s.auto_followup,recording_url:s.recording_url||'',welcome:s.welcome||'',questions:(s.questions||[]).map((q:any)=>({label:q.label,required:q.required,type:q.type,options:(q.options||[]).join(', ')})),
    panelists:(w?.panelists||[]).map((p:any)=>({name:p.name,email:p.email}))}));
  const [busy,setBusy]=useState(false);const [err,setErr]=useState('');const set=(k:string,v:any)=>setF((o:any)=>({...o,[k]:v}));
  const save=async(e:React.FormEvent)=>{e.preventDefault();setErr('');setBusy(true);try{
    const body={title:f.title,description:f.description,start_at:new Date(`${f.date}T${f.time}`).toISOString(),minutes:Number(f.minutes)||60,tz:TZ,base_url:location.origin+location.pathname,
      settings:{registration:f.registration,approval:f.approval,capacity:Number(f.capacity)||0,qa:f.qa,qa_view:f.qa_view,qa_anonymous:f.qa_anonymous,chat:f.chat,hand:f.hand,practice:f.practice,reminders:{day:f.day,hour:f.hour},auto_followup:f.auto_followup,recording_url:f.recording_url,welcome:f.welcome,
        questions:f.questions.filter((q:any)=>q.label.trim()).map((q:any)=>({label:q.label,required:!!q.required,type:q.type==='choice'?'choice':'text',options:String(q.options||'').split(',').map((x:string)=>x.trim()).filter(Boolean)}))},
      panelists:f.panelists.filter((p:any)=>p.email.trim())};
    onSaved(await request(w?`/webinars/${w.id}`:'/webinars',{method:w?'PATCH':'POST',body:JSON.stringify(body)}))}catch(x:any){setErr(x.message)}finally{setBusy(false)}};
  return <Modal title={w?'Edit webinar':'Schedule a webinar'} onClose={onClose} wide><form className="ws-form wbh-form" onSubmit={save}>
    <label>Title<input value={f.title} onChange={e=>set('title',e.target.value)} maxLength={200} autoFocus required/></label>
    <label>Description (shown on the registration page)<textarea rows={3} value={f.description} onChange={e=>set('description',e.target.value)} maxLength={4000}/></label>
    <div className="wbh-row"><label>Date<input type="date" value={f.date} onChange={e=>set('date',e.target.value)} required/></label><label>Time<input type="time" value={f.time} onChange={e=>set('time',e.target.value)} required/></label><label>Length (minutes)<input type="number" min={10} max={600} value={f.minutes} onChange={e=>set('minutes',e.target.value)}/></label></div>
    <p className="muted small">Times are in your time zone ({TZ}). Registered people see the time in their own.</p>
    <h4>Panelists</h4><p className="muted small">Panelists speak and share like you. Each gets an email with a personal link.</p>
    {f.panelists.map((p:any,i:number)=><div key={i} className="wbh-row"><input placeholder="Name" value={p.name} onChange={e=>set('panelists',f.panelists.map((x:any,j:number)=>j===i?{...x,name:e.target.value}:x))} aria-label="Panelist name"/><input type="email" placeholder="Email" value={p.email} onChange={e=>set('panelists',f.panelists.map((x:any,j:number)=>j===i?{...x,email:e.target.value}:x))} aria-label="Panelist email"/><button type="button" className="secondary" onClick={()=>set('panelists',f.panelists.filter((_:any,j:number)=>j!==i))} aria-label="Remove panelist"><Trash2 size={14}/></button></div>)}
    <button type="button" className="secondary" onClick={()=>set('panelists',[...f.panelists,{name:'',email:''}])}><Plus size={14}/> Add a panelist</button>
    <h4>Registration</h4>
    <label className="checklabel"><input type="checkbox" checked={f.registration} onChange={e=>set('registration',e.target.checked)}/> People must register first (each gets a personal link)</label>
    {f.registration&&<><div className="wbh-row"><label>Approval<select value={f.approval} onChange={e=>set('approval',e.target.value)}><option value="auto">Approve everyone automatically</option><option value="manual">I approve each person</option></select></label>
      <label>Most people (0 = the most the service allows)<input type="number" min={0} value={f.capacity} onChange={e=>set('capacity',e.target.value)}/></label></div>
      <p className="muted small">Extra questions on the registration form:</p>
      {f.questions.map((q:any,i:number)=><div key={i} className="wbh-row"><input placeholder="Question, for example Company" value={q.label} onChange={e=>set('questions',f.questions.map((x:any,j:number)=>j===i?{...x,label:e.target.value}:x))} aria-label="Question"/>
        <select value={q.type==='choice'?'choice':'text'} onChange={e=>set('questions',f.questions.map((x:any,j:number)=>j===i?{...x,type:e.target.value}:x))} aria-label="Answer type"><option value="text">Free text</option><option value="choice">Choose one</option></select>
        {q.type==='choice'&&<input placeholder="Choices, separated by commas" value={q.options} onChange={e=>set('questions',f.questions.map((x:any,j:number)=>j===i?{...x,options:e.target.value}:x))} aria-label="Choices"/>}
        <label className="checklabel"><input type="checkbox" checked={!!q.required} onChange={e=>set('questions',f.questions.map((x:any,j:number)=>j===i?{...x,required:e.target.checked}:x))}/> Required</label>
        <button type="button" className="secondary" onClick={()=>set('questions',f.questions.filter((_:any,j:number)=>j!==i))} aria-label="Remove question"><Trash2 size={14}/></button></div>)}
      {f.questions.length<8&&<button type="button" className="secondary" onClick={()=>set('questions',[...f.questions,{label:'',required:false,type:'text',options:''}])}><Plus size={14}/> Add a question</button>}</>}
    <h4>During the webinar</h4>
    <label className="checklabel"><input type="checkbox" checked={f.practice} onChange={e=>set('practice',e.target.checked)}/> Practice session first: attendees wait until I press <b>Go live</b></label>
    <label>Chat from attendees<select value={f.chat} onChange={e=>set('chat',e.target.value)}><option value="host">Goes to me only (private)</option><option value="panelists">Goes to me and the panelists</option><option value="everyone">Open to everyone</option><option value="off">Switched off</option></select></label>
    <label className="checklabel"><input type="checkbox" checked={f.qa} onChange={e=>set('qa',e.target.checked)}/> Q&amp;A: attendees ask questions and upvote them</label>
    {f.qa&&<div className="wbh-row"><label>Attendees see<select value={f.qa_view} onChange={e=>set('qa_view',e.target.value)}><option value="all">All questions</option><option value="answered">Only answered questions</option></select></label><label className="checklabel"><input type="checkbox" checked={f.qa_anonymous} onChange={e=>set('qa_anonymous',e.target.checked)}/> Allow anonymous questions</label></div>}
    <label className="checklabel"><input type="checkbox" checked={f.hand} onChange={e=>set('hand',e.target.checked)}/> Attendees can raise a hand</label>
    <h4>Emails</h4>
    <label className="checklabel"><input type="checkbox" checked={f.day} onChange={e=>set('day',e.target.checked)}/> Remind registered people the day before</label>
    <label className="checklabel"><input type="checkbox" checked={f.hour} onChange={e=>set('hour',e.target.checked)}/> Remind registered people an hour before</label>
    <label className="checklabel"><input type="checkbox" checked={f.auto_followup} onChange={e=>set('auto_followup',e.target.checked)}/> After the webinar, thank those who came and tell the others they were missed</label>
    <label>Recording link for follow-up emails (optional)<input type="url" value={f.recording_url} onChange={e=>set('recording_url',e.target.value)} placeholder="https://"/></label>
    <label>Note added to the confirmation email (optional)<textarea rows={2} value={f.welcome} onChange={e=>set('welcome',e.target.value)} maxLength={1000}/></label>
    {err&&<p className="syncerr" role="alert">{err}</p>}
    <div className="actions"><button className="primary" disabled={busy||f.title.trim().length<3}>{busy?'Saving…':w?'Save changes':'Schedule webinar'}</button><button type="button" className="secondary" onClick={onClose}>Cancel</button></div>
  </form></Modal>;
}

/* ---------------------------------------------------------------- one webinar */
function Detail({id,request,onBack,notify}:{id:string;request:any;onBack:()=>void;notify:(m:string)=>void}){
  const [w,setW]=useState<any>(null);const [tab,setTab]=useState<'overview'|'registrants'|'polls'|'reports'>('overview');const [edit,setEdit]=useState(false);const [err,setErr]=useState('');
  const load=useCallback(()=>request(`/webinars/${id}`).then(setW).catch((e:any)=>setErr(e.message)),[id,request]);
  useEffect(()=>{load();const t=setInterval(()=>{if(document.visibilityState==='visible')load()},15000);return()=>clearInterval(t)},[load]);
  if(err)return <section className="panel"><p className="syncerr">{err}</p><button className="secondary" onClick={onBack}>Back</button></section>;
  if(!w)return <section className="panel"><p className="muted">Loading…</p></section>;
  const [bt,bc]=badge(w);const open=()=>{try{sessionStorage.removeItem('isift.wb.'+w.room_code)}catch{};location.hash='#/room/'+w.room_code};
  const cancel=async()=>{if(!window.confirm('Cancel this webinar? Everyone registered gets an email.'))return;try{const r=await request(`/webinars/${id}`,{method:'DELETE'});notify(r.message);load()}catch(e:any){setErr(e.message)}};
  return <section className="panel wbh-detail">
    <div className="panelhead"><h2>{w.title}</h2><span className={`ism-badge ${bc==='ok'?'ok':'wait'}`}>{bt}</span></div>
    <p className="muted">{fmt(w.start_at)} · {w.minutes} minutes{w.live?` · ${w.watching} watching now`:''}</p>
    <div className="actions">{w.status==='scheduled'&&<button className="primary" onClick={open}><Radio size={15}/> {w.live?'Return to the webinar':'Open the webinar room'}</button>}
      {w.status==='scheduled'&&<button className="secondary" onClick={()=>setEdit(true)}>Edit</button>}{w.status==='scheduled'&&<button className="secondary" onClick={cancel}>Cancel webinar</button>}<button className="secondary" onClick={onBack}>All webinars</button></div>
    <div className="tabs subtabs" role="tablist">{([['overview','Overview'],['registrants',`Registrants (${w.registered})`],['polls','Polls'],['reports','Reports']] as const).map(([k,l])=><button key={k} role="tab" aria-selected={tab===k} className={tab===k?'on':''} onClick={()=>setTab(k)}>{l}{k==='registrants'&&w.pending>0&&<i className="dot" title="Waiting for your approval"/>}</button>)}</div>
    {tab==='overview'&&<><p className="hint">Share the registration page. People register, get a personal link by email, and join from it. Open the room a little early to practise; attendees wait until you press <b>Go live</b>.</p>
      <Copy1 label="Registration page" value={w.page}/>
      {w.panelists.length>0&&<><h4>Panelists</h4>{w.panelists.map((p:any)=><Copy1 key={p.email} label={`${p.name||p.email}'s link`} value={p.link}/>)}</>}
      <div className="wbh-kpis"><div><b>{w.report.registered}</b><span>registered</span></div><div><b>{w.report.pending}</b><span>to approve</span></div><div><b>{w.report.attended}</b><span>attended</span></div><div><b>{w.report.questions}</b><span>questions</span></div></div></>}
    {tab==='registrants'&&<Registrants id={id} request={request} notify={notify} onChanged={load}/>}
    {tab==='polls'&&<Polls id={id} request={request}/>}
    {tab==='reports'&&<Reports w={w} request={request} notify={notify} reload={load}/>}
    {edit&&<WebinarForm w={w} request={request} onClose={()=>setEdit(false)} onSaved={r=>{setEdit(false);notify(r.message||'Saved.');load()}}/>}
  </section>;
}

function Registrants({id,request,notify,onChanged}:{id:string;request:any;notify:(m:string)=>void;onChanged:()=>void}){
  const [rows,setRows]=useState<any[]|null>(null);const [defs,setDefs]=useState<any[]>([]);const [add,setAdd]=useState('');const [err,setErr]=useState('');const [q,setQ]=useState('');
  const load=useCallback(()=>request(`/webinars/${id}/registrants`).then((r:any)=>{setRows(r.registrants);setDefs(r.questions||[])}).catch((e:any)=>setErr(e.message)),[id,request]);
  useEffect(()=>{load()},[load]);
  const act=async(fn:()=>Promise<any>)=>{setErr('');try{const r=await fn();if(r?.message)notify(r.message);load();onChanged()}catch(e:any){setErr(e.message)}};
  const decide=(r:any,status:string)=>act(()=>request(`/webinars/${id}/registrants/${r.id}`,{method:'PATCH',body:JSON.stringify({status})}));
  const people=()=>add.split('\n').map(l=>l.trim()).filter(Boolean).map(l=>{const m=l.match(/^(.*?)[,\t ]*<?([^\s,<>]+@[^\s,<>]+)>?$/);return m?{name:m[1].replace(/["]/g,'').trim(),email:m[2]}:{name:'',email:l}});
  if(rows===null)return <p className="muted">Loading…</p>;
  const shown=rows.filter(r=>!q.trim()||(r.name+r.email).toLowerCase().includes(q.trim().toLowerCase()));
  return <div>
    {err&&<p className="syncerr" role="alert">{err}</p>}
    <div className="actions"><input placeholder="Search" value={q} onChange={e=>setQ(e.target.value)} aria-label="Search registrants"/>{rows.some(r=>r.status==='pending')&&<button className="primary" onClick={()=>act(()=>request(`/webinars/${id}/registrants/approve-all`,{method:'POST'}))}>Approve everyone waiting</button>}
      <button className="secondary" onClick={()=>act(async()=>{const r=await request(`/webinars/${id}/export/registrants`);saveText(r.filename,r.content)})}><Download size={14}/> Download CSV</button></div>
    <div className="plantable-wrap"><table className="modtable"><thead><tr><th>Name</th><th>Email</th>{defs.map(d=><th key={d.id}>{d.label}</th>)}<th>Status</th><th/></tr></thead><tbody>
      {shown.map(r=><tr key={r.id}><td><b>{r.name}</b></td><td>{r.email}</td>{defs.map(d=><td key={d.id}>{r.answers[d.id]||''}</td>)}<td>{r.status}{r.attended?' · attended':''}</td>
        <td className="wbh-act">{r.status==='pending'&&<><button className="primary" onClick={()=>decide(r,'approved')}>Approve</button><button className="secondary" onClick={()=>decide(r,'denied')}>Decline</button></>}
          {r.status==='approved'&&<><button className="secondary" onClick={()=>act(()=>request(`/webinars/${id}/registrants/${r.id}`,{method:'PATCH',body:JSON.stringify({status:'resend'})}))} title="Send the link again"><Mail size={13}/></button><button className="secondary" onClick={()=>decide(r,'cancelled')}>Cancel</button></>}</td></tr>)}
      {!shown.length&&<tr><td colSpan={4+defs.length}><span className="muted">{rows.length?'Nobody matches.':'Nobody has registered yet.'}</span></td></tr>}</tbody></table></div>
    <h4>Add people yourself</h4><p className="muted small">One per line: <code>Name, email</code>. They are approved and emailed their personal link.</p>
    <textarea rows={4} value={add} onChange={e=>setAdd(e.target.value)} placeholder={'Ann Lee, ann@example.com\nbo@example.com'} aria-label="People to add"/>
    <div className="actions"><button className="primary" disabled={!add.trim()} onClick={()=>act(async()=>{const r=await request(`/webinars/${id}/registrants`,{method:'POST',body:JSON.stringify({people:people()})});setAdd('');return r})}>Add and email</button></div>
  </div>;
}

function Polls({id,request}:{id:string;request:any}){
  const [polls,setPolls]=useState<any[]|null>(null);const [form,setForm]=useState<any>(null);const [err,setErr]=useState('');
  const load=useCallback(()=>request(`/webinars/${id}/polls`).then((r:any)=>setPolls(r.polls)).catch((e:any)=>setErr(e.message)),[id,request]);
  useEffect(()=>{load()},[load]);
  const save=async(e:React.FormEvent)=>{e.preventDefault();setErr('');try{const body={question:form.question,options:form.options.split('\n'),multi:form.multi};await request(form.id?`/webinars/${id}/polls/${form.id}`:`/webinars/${id}/polls`,{method:form.id?'PATCH':'POST',body:JSON.stringify(body)});setForm(null);load()}catch(x:any){setErr(x.message)}};
  const del=async(p:any)=>{if(!window.confirm('Delete this poll?'))return;try{await request(`/webinars/${id}/polls/${p.id}`,{method:'DELETE'});load()}catch(x:any){setErr(x.message)}};
  return <div><p className="hint">Prepare polls here. During the webinar you launch each one from the Q&amp;A panel, attendees vote, and you choose whether to share the results.</p>
    {err&&<p className="syncerr" role="alert">{err}</p>}
    {polls?.map(p=><div key={p.id} className="wbh-poll"><div><b>{p.question}</b><div className="muted small">{p.options.join(' · ')}{p.multi?' (choose several)':''} · {p.status==='draft'?'not launched':p.status}{p.total?` · ${p.total} votes`:''}</div></div>
      {p.status==='draft'&&<button className="secondary" onClick={()=>setForm({id:p.id,question:p.question,options:p.options.join('\n'),multi:p.multi})}>Edit</button>}<button className="secondary" onClick={()=>del(p)} aria-label="Delete poll"><Trash2 size={14}/></button></div>)}
    {polls&&!polls.length&&!form&&<p className="muted small">No polls yet.</p>}
    {form?<form onSubmit={save} className="wbh-form"><label>Question<input value={form.question} onChange={e=>setForm({...form,question:e.target.value})} maxLength={300} autoFocus/></label>
      <label>Answers (one per line, up to 10)<textarea rows={4} value={form.options} onChange={e=>setForm({...form,options:e.target.value})}/></label>
      <label className="checklabel"><input type="checkbox" checked={form.multi} onChange={e=>setForm({...form,multi:e.target.checked})}/> People may choose more than one answer</label>
      <div className="actions"><button className="primary">Save poll</button><button type="button" className="secondary" onClick={()=>setForm(null)}>Cancel</button></div></form>
      :<div className="actions"><button className="secondary" onClick={()=>setForm({question:'',options:'',multi:false})}><Plus size={14}/> Add a poll</button></div>}
  </div>;
}

function Reports({w,request,notify,reload}:{w:any;request:any;notify:(m:string)=>void;reload:()=>void}){
  const r=w.report;const [qs,setQs]=useState<any[]>([]);const [msg,setMsg]=useState('');const [busy,setBusy]=useState('');
  useEffect(()=>{request(`/webinars/${w.id}/questions`).then((x:any)=>setQs(x.questions)).catch(()=>{})},[w.id,request]);
  const dl=async(k:string)=>{try{const x=await request(`/webinars/${w.id}/export/${k}`);saveText(x.filename,x.content)}catch(e:any){setMsg(e.message)}};
  const follow=async(kind:string)=>{setBusy(kind);setMsg('');try{const x=await request(`/webinars/${w.id}/followup`,{method:'POST',body:JSON.stringify({kind})});setMsg(x.message);notify(x.message)}catch(e:any){setMsg(e.message)}finally{setBusy('')}};
  return <div>
    <div className="wbh-kpis"><div><b>{r.registered}</b><span>registered</span></div><div><b>{r.attended}</b><span>attended ({r.attend_rate}%)</span></div><div><b>{r.avg_minutes}</b><span>average minutes watched</span></div><div><b>{r.answered}/{r.questions}</b><span>questions answered</span></div><div><b>{r.votes}</b><span>poll votes</span></div></div>
    <div className="actions">{[['registrants','Registrants'],['attendance','Attendance'],['questions','Questions'],['polls','Poll results']].map(([k,l])=><button key={k} className="secondary" onClick={()=>dl(k)}><Download size={14}/> {l} (CSV)</button>)}</div>
    <h4>Follow up</h4>{w.status==='ended'?<><p className="muted small">Each person gets each email once. {w.settings.recording_url?'The recording link is added.':'Add a recording link under Edit to include it.'}</p>
      <div className="actions"><button className="primary" disabled={!!busy} onClick={()=>follow('attended')}>Thank those who came</button><button className="secondary" disabled={!!busy} onClick={()=>follow('missed')}>Email those who missed it</button></div></>:<p className="muted small">Available once the webinar has ended.</p>}
    {msg&&<p className="muted" role="status">{msg}</p>}
    <h4>Questions</h4>{!qs.length&&<p className="muted small">No questions were asked.</p>}
    {qs.map(q=><div key={q.id} className="wbh-poll"><div><b>{q.text}</b><div className="muted small">{q.name} · {q.up} upvote{q.up===1?'':'s'} · {q.status}{q.answer?` · “${q.answer}”`:''}</div></div></div>)}
  </div>;
}

/* ---------------------------------------------------------------- the list */
export function WebinarsPage({request,notify}:{request:any;notify:(m:string)=>void}){
  const [list,setList]=useState<any[]|null>(null);const [err,setErr]=useState('');const [form,setForm]=useState(false);const [open,setOpen]=useState('');
  const load=useCallback(()=>request('/webinars').then((r:any)=>setList(r.webinars)).catch((e:any)=>setErr(e.message)),[request]);
  useEffect(()=>{load();const t=setInterval(()=>{if(document.visibilityState==='visible'&&!open)load()},20000);return()=>clearInterval(t)},[load,open]);
  if(open)return <Detail id={open} request={request} notify={notify} onBack={()=>{setOpen('');load()}}/>;
  const up=(list||[]).filter(w=>w.status==='scheduled'),past=(list||[]).filter(w=>w.status!=='scheduled');
  const row=(w:any)=>{const [t,c]=badge(w);return <button key={w.id} type="button" className="wbh-row-item" onClick={()=>setOpen(w.id)}><div><b>{w.title}</b><div className="muted small">{fmt(w.start_at)} · {w.minutes} min</div></div>
    <div className="wbh-nums"><span title="Registered"><Users size={13}/> {w.registered}</span>{w.pending>0&&<span className="wbh-pend" title="Waiting for approval">{w.pending} to approve</span>}{w.status==='ended'&&<span title="Attended"><BarChart3 size={13}/> {w.attended}</span>}<span className={`ism-badge ${c==='ok'?'ok':'wait'}`}>{t}</span></div></button>};
  return <section className="panel"><div className="panelhead"><h2>Webinars</h2><Presentation size={18}/></div>
    <p className="hint">Run a webinar like Zoom or Webex: people register and get a personal link, panelists speak, attendees watch, ask questions in Q&amp;A, vote in polls and raise a hand. You decide who speaks.</p>
    {err&&<p className="syncerr" role="alert">{err}</p>}
    <div className="actions"><button className="primary" onClick={()=>setForm(true)}><Plus size={15}/> Schedule a webinar</button></div>
    {list===null&&!err&&<p className="muted">Loading…</p>}
    {list&&!list.length&&<p className="muted small">No webinars yet. Schedule one to get a registration page you can share.</p>}
    {up.length>0&&<><h4>Upcoming</h4><div className="wbh-list">{up.map(row)}</div></>}
    {past.length>0&&<><h4>Past and cancelled</h4><div className="wbh-list">{past.map(row)}</div></>}
    {form&&<WebinarForm request={request} onClose={()=>setForm(false)} onSaved={r=>{setForm(false);notify(r.message||'Webinar created.');load();setOpen(r.id)}}/>}
  </section>;
}
export {FileText};
