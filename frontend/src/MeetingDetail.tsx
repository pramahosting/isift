import {DayPreset,DAY_NAMES} from './DayPreset';
import React,{useEffect,useState} from 'react';
import {ArrowLeft,Copy,Pencil,Trash2,Video,CalendarPlus} from 'lucide-react';
import {JoinButton} from './Connections';
import {Modal} from './Workspace';
const PLAT:Record<string,string>={zoom:'Zoom',teams:'Microsoft Teams',meet:'Google Meet'};
import {currentTz,tzLabel,allZones} from './timezone';

const pad=(n:number)=>String(n).padStart(2,'0');
/** An instant as 'YYYY-MM-DDTHH:mm' on the wall clock of the chosen time zone (what a datetime-local box wants). */
export const toLocalInput=(iso:string,tz=currentTz())=>{
  try{const p=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:tz,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(iso)).map(x=>[x.type,x.value]));return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`}catch{const d=new Date(iso);return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`}
};
const whenText=(iso:string,mins:number)=>{
  try{const tz=currentTz();const s=new Date(iso);const e=new Date(s.getTime()+mins*60000);
    const d=new Intl.DateTimeFormat(undefined,{timeZone:tz,weekday:'long',day:'numeric',month:'long',year:'numeric'}).format(s);
    const t=(x:Date)=>new Intl.DateTimeFormat(undefined,{timeZone:tz,hour:'numeric',minute:'2-digit'}).format(x);
    return `${d}, ${t(s)} – ${t(e)} (${tzLabel(tz).city}, ${tzLabel(tz).off})`}catch{return iso}
};

/** Confirm deleting a meeting; offers to delete the whole series for recurring meetings. */
export function DeleteMeeting({target,request,onClose,onDone}:{target:{id?:string;many?:string[];title:string;series:boolean;room:boolean;imported?:boolean};request:any;onClose:()=>void;onDone:(msg:string)=>void}){
  const [busy,setBusy]=useState(false);const [err,setErr]=useState('');
  const go=async(series:boolean)=>{setBusy(true);setErr('');try{if(target.many){let n=0,kept=0;for(const id of target.many){const x=await request(`/meetings/${id}`,{method:'DELETE'});n+=x.removed||0;if(!x.removed)kept++}onDone(`${n} meeting${n===1?'':'s'} deleted.${kept?` ${kept} kept as cancelled because transcripts or minutes exist.`:''}`);return}const r=await request(`/meetings/${target.id}${series?'?series=true':''}`,{method:'DELETE'});onDone(r.message)}catch(e:any){setErr(e.message);setBusy(false)}};
  return <Modal title="Delete meeting" onClose={onClose}><div className="ws-form">
    <p>Delete <b>{target.title}</b>? {target.room?'Anyone in the meeting is disconnected and the link stops working. ':''}{target.imported?'It comes from your calendar app, so it is only removed from iSift and may return when you sync again. ':''}This cannot be undone.</p>
    {err&&<p className="syncerr" role="alert">{err}</p>}
    <div className="actions"><button className="primary dangerfill" disabled={busy} onClick={()=>go(false)}><Trash2 size={15}/> {target.series?'Delete this meeting only':'Delete'}</button>{target.series&&<button className="primary dangerfill" disabled={busy} onClick={()=>go(true)}>Delete the whole series</button>}<button className="secondary" onClick={onClose}>Keep it</button></div></div></Modal>;
}

/** Shown when a platform has no account set up yet. Closes with the X (top right), Esc or a click outside. */
function PlatformSetup({platform,why,isAdmin,goSettings,onClose,onUseIsift}:{platform:string;why?:string;isAdmin:boolean;goSettings?:()=>void;onClose:()=>void;onUseIsift:()=>void}){
  const name=PLAT[platform]||platform;
  return <Modal title={`${name} is not set up`} onClose={onClose}><div className="ws-form">
    <p>{name} cannot book meetings yet because its account details have not been added in Settings.{why?` ${why}`:''}</p>
    {isAdmin?<p className="muted small">Open <b>Admin Console → Meeting platforms</b>, enter the details and press Save. Then come back and pick {name} again.</p>:<p className="muted small">Please ask your administrator to set up {name} under Admin Console → Meeting platforms.</p>}
    <div className="actions">{isAdmin&&goSettings&&<button type="button" className="primary" onClick={()=>{try{sessionStorage.setItem('isift.admintab','meetings')}catch{};onClose();goSettings()}}>Open Admin Console</button>}<button type="button" className="secondary" onClick={onUseIsift}>Use iSift instead</button></div></div></Modal>;
}

/** Zoom-style meeting form: used to schedule a new meeting and to edit one. */
export function MeetingForm({request,initial,onSaved,onCancel,isAdmin,goSettings,prefill}:{request:any;zoomReady?:boolean;initial?:any;prefill?:any;onSaved:(r:any)=>void;onCancel:()=>void;isAdmin?:boolean;goSettings?:()=>void}){
  const edit=!!initial;
  const d0=new Date(Date.now()+3600e3);d0.setMinutes(0,0,0);
  const [title,setTitle]=useState(initial?.title||prefill?.title||'');
  const [agenda,setAgenda]=useState(initial?.agenda||prefill?.agenda||'');
  const [when,setWhen]=useState(initial?toLocalInput(initial.start_at):prefill?.start_at?toLocalInput(prefill.start_at):`${d0.getFullYear()}-${pad(d0.getMonth()+1)}-${pad(d0.getDate())}T${pad(d0.getHours())}:00`);
  const [dur,setDur]=useState(initial?.duration_minutes||prefill?.duration_minutes||30);
  const [kind,setKind]=useState(initial?initial.kind:'room');
  const [plats,setPlats]=useState<any>(null);const [setup,setSetup]=useState('');
  useEffect(()=>{if(!initial)request('/meeting-platforms').then(setPlats).catch(()=>{})},[]);
  const pickKind=(v:string)=>{if(PLAT[v]&&plats&&!plats[v]?.ready){setSetup(v);return}setKind(v)};
  const [link,setLink]=useState('');
  const [needPc,setNeedPc]=useState(initial?initial.access==='passcode':true);
  const [signedIn,setSignedIn]=useState(initial?.access==='signed_in');
  const [pcode,setPcode]=useState(initial?.access==='passcode'?(initial.passcode||''):'');
  const [waiting,setWaiting]=useState(initial?!!initial.waiting_room:true);
  const [openRoom,setOpenRoom]=useState(!!initial?.options?.open_room);const [canOpen,setCanOpen]=useState(true);useEffect(()=>{request('/me/limits').then((l:any)=>setCanOpen(!!l.open_room)).catch(()=>{})},[]);
  const [mute,setMute]=useState(!!initial?.options?.mute_on_entry);
  const [vidOff,setVidOff]=useState(!!initial?.options?.video_off_on_entry);
  const [autoRec,setAutoRec]=useState(!!initial?.options?.auto_record);
  const [vroom,setVroom]=useState(initial?.options?.virtual_room===true);const [vrAccount,setVrAccount]=useState(true);
  useEffect(()=>{request('/account').then((a:any)=>setVrAccount(a?.profile?.virtual_room!==false)).catch(()=>{})},[]);
  const [invite,setInvite]=useState('');const [sendUpdate,setSendUpdate]=useState(true);
  const [hostOff,setHostOff]=useState(!!initial?.options?.host_video_off);
  const [canUnmute,setCanUnmute]=useState(initial?.options?.participants_can_unmute!==false);const [canVideo,setCanVideo]=useState(initial?.options?.participants_can_video!==false);
  const [tz,setTz]=useState(currentTz());const [idMode,setIdMode]=useState('auto');const [recur,setRecur]=useState('none');const [recCount,setRecCount]=useState(4);const [recEnd,setRecEnd]=useState<'count'|'date'>('count');const [recUntil,setRecUntil]=useState('');const [recDays,setRecDays]=useState<number[]>([]);const [pat,setPat]=useState('none');const wd=()=>{const d=new Date(when);return isNaN(+d)?0:(d.getDay()+6)%7};const pickPattern=(v:string)=>{setPat(v);setRecur(v==='none'||v==='day'||v==='month'?v:'week');setRecDays(v==='weekdays'?[0,1,2,3,4]:v==='weekends'?[5,6]:v==='week'?[wd()]:v==='custom'?(d=>d.length?d:[wd()])(recDays):[])};const [recWeeks,setRecWeeks]=useState(10);
  const [people,setPeople]=useState<any>({contacts:[],groups:[]});useEffect(()=>{request('/contacts').then(setPeople).catch(()=>{})},[]);
  const addEmails=(list:string[])=>{const have=new Set(invite.split(/[\s,;]+/).filter(Boolean).map(x=>x.toLowerCase()));const add=list.filter(e=>e&&!have.has(e.toLowerCase()));if(add.length)setInvite((invite.trim()?invite.trim().replace(/[,;]$/,'')+', ':'')+add.join(', '))};
  const [busy,setBusy]=useState(false);const [err,setErr]=useState('');
  const isRoom=kind==='room';const L=tzLabel(tz);const pmi=!edit&&isRoom&&idMode==='personal';const zones=[...new Set([tz,currentTz(),...allZones()])];
  const durations=[...new Set([15,30,45,60,90,120,180,dur])].sort((a,b)=>a-b);
  const submit=async(e:React.FormEvent)=>{e.preventDefault();setBusy(true);setErr('');
    try{
      const body:any={title,agenda,start_at:when,duration_minutes:dur,timezone:tz};
      if(isRoom){body.waiting_room=waiting;body.options={mute_on_entry:mute,video_off_on_entry:vidOff,auto_record:autoRec,host_video_off:hostOff,participants_can_unmute:canUnmute,participants_can_video:canVideo,virtual_room:vroom,open_room:openRoom};if(openRoom){body.waiting_room=false;body.access='open';delete body.passcode}if(pmi)body.meeting_id_mode='personal';body.access=needPc?'passcode':signedIn?'signed_in':'open';if(needPc&&pcode.trim())body.passcode=pcode.trim()}
      if(!edit&&PLAT[kind]&&plats&&!plats[kind]?.ready){setSetup(kind);setBusy(false);return}
      const ext=!edit&&!!PLAT[kind];const win=ext?window.open('','isift-platform','width=1000,height=760'):null;
      if(win)try{win.document.title=PLAT[kind];win.document.body.innerHTML=`<p style="font:16px system-ui;padding:24px">Booking your ${PLAT[kind]} meeting…</p>`}catch{}
      if(!edit&&recur!=='none'&&kind!=='zoom'&&kind!=='teams'&&kind!=='meet'){if(recEnd==='never'){body.recurrence={every:recur,forever:true,...(recur==='week'&&recDays.length?{days:recDays}:{})}}else if(recEnd==='date'){if(!recUntil){setErr('Pick the last day of the repeat.');setBusy(false);return}body.recurrence={every:recur,until:recUntil,...(recur==='week'&&recDays.length?{days:recDays}:{})}}else body.recurrence=recur==='week'&&recDays.length?{every:recur,days:recDays,weeks:recWeeks}:{every:recur,count:recCount}}
      let r:any;
      if(edit){if(isRoom){body.add_invitees=invite;body.send_update=sendUpdate}r=await request(`/meetings/${initial.id}`,{method:'PATCH',body:JSON.stringify(body)})}
      else{body.invite=invite;if(kind==='room'){body.provider='room';body.base_url=location.origin+location.pathname}else if(PLAT[kind])body.provider=kind;else if(kind==='link')body.join_url=link;try{r=await request('/meetings',{method:'POST',body:JSON.stringify(body)})}catch(x){try{win?.close()}catch{};throw x}
        if(win){try{win.location.href=r.join_url}catch{}}}
      onSaved(r);
    }catch(x:any){setErr(x.message)}finally{setBusy(false)}};
  return <form className="panel newmeeting conn-form" onSubmit={submit}>
    <div className="panelhead span2"><h2><CalendarPlus size={18}/> {edit?'Edit meeting':'Schedule a meeting'}</h2></div>
    <label className="span2">Topic<input value={title} onChange={e=>setTitle(e.target.value)} required maxLength={200} autoFocus placeholder="My meeting"/></label>
    <label className="span2">Description (optional)<textarea rows={3} value={agenda} onChange={e=>setAgenda(e.target.value)} maxLength={2000} placeholder="Agenda or notes for the invitation"/></label>
    <label>When<input type="datetime-local" value={when} onChange={e=>setWhen(e.target.value)} required/></label>
    <label>Duration<select value={dur} onChange={e=>setDur(Number(e.target.value))}>{durations.map(m=><option key={m} value={m}>{m>=60&&m%60===0?`${m/60} hour${m>60?'s':''}`:`${m} minutes`}</option>)}</select></label>
    <label className="span2">Time zone<select value={tz} onChange={e=>setTz(e.target.value)}>{zones.map(z=>{const l=tzLabel(z);return <option key={z} value={z}>{`(${l.off}) ${l.city}${l.region?`, ${l.region}`:''}`}</option>})}</select><small className="muted">Starts on your device’s time zone. Pick another to schedule in that zone.</small></label>
    {!edit&&!PLAT[kind]&&<fieldset className="span2 mf-set"><legend>Recurring meeting</legend><span className="mf-rec"><select value={pat} onChange={e=>pickPattern(e.target.value)} aria-label="Repeat"><option value="none">Does not repeat</option><option value="day">Daily</option><option value="weekdays">Every weekday (Monday to Friday)</option><option value="weekends">Weekends (Saturday and Sunday)</option><option value="week">Weekly</option><option value="custom">Weekly on chosen days…</option><option value="month">Monthly</option></select></span>
      {recur==='week'&&<div className="mf-days" role="group" aria-label="Repeat on these days"><span className="muted small">Repeat on</span>{DAY_NAMES.map((n,i)=><label key={n} className={`daychk${recDays.includes(i)?' on':''}`}><input type="checkbox" checked={recDays.includes(i)} onChange={e=>{setPat('custom');setRecDays(d=>e.target.checked?[...d,i].sort():d.filter(x=>x!==i))}}/>{n}</label>)}</div>}
      {recur!=='none'&&<>{recur==='week'&&recDays.length>0?<label className="check"><input type="radio" name="rend" checked={recEnd==='count'} onChange={()=>setRecEnd('count')}/> For the next <input type="number" min={1} max={52} value={recWeeks} onChange={e=>{setRecWeeks(Math.max(1,Math.min(52,Number(e.target.value)||1)));setRecEnd('count')}} aria-label="Number of weeks" className="mf-num"/> weeks</label>:<label className="check"><input type="radio" name="rend" checked={recEnd==='count'} onChange={()=>setRecEnd('count')}/> Ends after <input type="number" min={2} max={365} value={recCount} onChange={e=>{setRecCount(Math.max(2,Math.min(365,Number(e.target.value)||2)));setRecEnd('count')}} aria-label="Number of occurrences" className="mf-num"/> meetings</label>}
      <label className="check"><input type="radio" name="rend" checked={recEnd==='never'} onChange={()=>setRecEnd('never')}/> No end date <small className="muted">(a year of meetings is created: {recur==='month'?'24 months':'52 weeks'} max)</small></label>
      <label className="check"><input type="radio" name="rend" checked={recEnd==='date'} onChange={()=>setRecEnd('date')}/> Last day <input type="date" value={recUntil} min={when.slice(0,10)} onChange={e=>{setRecUntil(e.target.value);setRecEnd('date')}} aria-label="Last day of the repeat" className="mf-date"/></label></>}</fieldset>}{!edit&&!!PLAT[kind]&&<small className="muted span2">Repeating meetings are available for iSift video meetings and your own link, not for Zoom, Teams or Google Meet bookings.</small>}
    {initial?.series&&<p className="muted small span2">This meeting is part of a series. Time and title changes apply to this one; security and options apply to the whole series.</p>}
    {!edit&&<label className="span2">Platform<select value={kind} onChange={e=>pickKind(e.target.value)}><option value="room">iSift video meeting (built in)</option><option value="zoom">Zoom</option><option value="teams">Microsoft Teams</option><option value="meet">Google Meet</option><option value="link">I already have a meeting link</option><option value="none">No online link</option></select><small className="muted">Zoom, Teams and Google Meet book through that service using the account set up in Admin Console.</small></label>}
    {!edit&&isRoom&&<fieldset className="span2 mf-set"><legend>Meeting ID</legend><label className="check"><input type="radio" name="idm" checked={idMode==='auto'} onChange={()=>setIdMode('auto')}/> Generate automatically</label><label className="check"><input type="radio" name="idm" checked={idMode==='personal'} onChange={()=>setIdMode('personal')}/> Personal Meeting ID (same link every time)</label></fieldset>}
    {!edit&&kind==='link'&&<label className="span2">Meeting link<input value={link} onChange={e=>setLink(e.target.value)} placeholder="https://…" required/></label>}
    {pmi&&<p className="muted small span2">A Personal Meeting ID uses its own passcode and waiting room, shown on the meeting page after you save.</p>}
    {isRoom&&<fieldset className="span2 mf-set"><legend>Open room</legend><label className="check"><input type="checkbox" checked={openRoom} disabled={!canOpen&&!openRoom} onChange={e=>{setOpenRoom(e.target.checked);if(e.target.checked){setNeedPc(false);setSignedIn(false);setWaiting(false)}}}/> Open room: anyone with the link can start or join at any time. No passcode, nobody is admitted, and the room never closes for good{pmi?' (applies to your Personal Meeting ID)':''}.{!canOpen&&<small className="muted"> Only the administrator and paid plans can use an open room.</small>}</label></fieldset>}
    {isRoom&&!pmi&&!openRoom&&<fieldset className="span2 mf-set"><legend>Security</legend>
      <label className="check"><input type="checkbox" checked={needPc} onChange={e=>{setNeedPc(e.target.checked);if(e.target.checked)setSignedIn(false)}}/> Require a passcode {needPc&&<input className="mf-pc" value={pcode} onChange={e=>setPcode(e.target.value)} maxLength={12} placeholder="Leave blank to make one" aria-label="Passcode"/>}</label>
      <label className="check"><input type="checkbox" checked={signedIn} onChange={e=>{setSignedIn(e.target.checked);if(e.target.checked)setNeedPc(false)}}/> Only signed-in people can join</label>
      <label className="check"><input type="checkbox" checked={waiting} onChange={e=>setWaiting(e.target.checked)}/> Waiting room (you let people in)</label>
      {!needPc&&!signedIn&&<small className="muted">Anyone with the link can join.</small>}</fieldset>}
    {isRoom&&<fieldset className="span2 mf-set"><legend>Meeting options</legend>
      <label className="check"><input type="checkbox" checked={!hostOff} onChange={e=>setHostOff(!e.target.checked)}/> Host video on when starting</label>
      <label className="check"><input type="checkbox" checked={mute} onChange={e=>setMute(e.target.checked)}/> Mute participants when they join</label>
      <label className="check"><input type="checkbox" checked={vidOff} onChange={e=>setVidOff(e.target.checked)}/> Participants’ video is off when they join</label>
      <label className="check"><input type="checkbox" checked={canUnmute} onChange={e=>setCanUnmute(e.target.checked)}/> Participants can unmute themselves</label>
      <label className="check"><input type="checkbox" checked={canVideo} onChange={e=>setCanVideo(e.target.checked)}/> Participants can start their own video</label>
      <label className="check"><input type="checkbox" checked={vroom&&vrAccount} disabled={!vrAccount} onChange={e=>setVroom(e.target.checked)}/> Virtual room: show participants around a boardroom table (up to 10 people). The host can switch it on or off during the meeting.{!vrAccount&&<small className="muted"> — switched off for your account in My account</small>}</label>
      <label className="check"><input type="checkbox" checked={autoRec} onChange={e=>setAutoRec(e.target.checked)}/> Record the meeting automatically when I start it (everyone sees the recording banner)</label></fieldset>}
    {(people.contacts.length>0||people.groups.length>0)&&<label className="span2">Add from contacts<select value="" onChange={e=>{const v=e.target.value;if(v.startsWith('g:')){const g=people.groups.find((x:any)=>x.id===v.slice(2));addEmails((g?.contact_ids||[]).map((id:string)=>people.contacts.find((c:any)=>c.id===id)?.email))}else if(v){addEmails([people.contacts.find((c:any)=>c.id===v)?.email])}}}><option value="">Choose a contact or group…</option>{people.groups.map((g:any)=><option key={g.id} value={'g:'+g.id}>Group: {g.name}</option>)}{people.contacts.filter((c:any)=>c.email).map((c:any)=><option key={c.id} value={c.id}>{c.name} ({c.email})</option>)}</select></label>}
    <label className="span2">{edit?'Add invitees (optional)':'Invite people (optional)'}<input value={invite} onChange={e=>setInvite(e.target.value)} placeholder="name@example.com, other@example.com"/><small className="muted">They get a calendar invitation from your connected mail account (Connections page).{edit&&initial?.invitees?.length?` Already invited: ${initial.invitees.join(', ')}.`:''}</small></label>
    {edit&&isRoom&&<label className="check span2"><input type="checkbox" checked={sendUpdate} onChange={e=>setSendUpdate(e.target.checked)}/> Email the updated details to everyone invited</label>}
    {err&&<p className="syncerr span2" role="alert">{err}</p>}
    <div className="actions span2"><button className="primary" disabled={busy||!title.trim()}>{busy?'Saving…':edit?'Save':'Save meeting'}</button><button type="button" className="secondary" onClick={onCancel}>Cancel</button></div>
  {setup&&<PlatformSetup platform={setup} why={plats?.[setup]?.why} isAdmin={!!isAdmin} goSettings={goSettings} onClose={()=>setSetup('')} onUseIsift={()=>{setSetup('');setKind('room')}}/>}
  </form>;
}

/** The page for one meeting: link, ID, passcode, invitation text, with Start / Edit / Delete (like a Zoom meeting page). */
export function MeetingDetail({id,request,onBack,onChanged,notice,isAdmin,goSettings,startEdit,onCopy}:{onCopy?:(m:any)=>void;id:string;request:any;startEdit?:boolean;zoomReady?:boolean;onBack:()=>void;onChanged:()=>void;notice:(m:string)=>void;isAdmin?:boolean;goSettings?:()=>void}){
  const [m,setM]=useState<any>(null);const [edit,setEdit]=useState(false);const [err,setErr]=useState('');const [copied,setCopied]=useState('');
  const load=()=>request(`/meetings/${id}/details`).then((r:any)=>{setM(r);setErr('')}).catch((e:any)=>setErr(e.message));
  const [del,setDel]=useState(false);const [hostCode,setHostCode]=useState('');const [resending,setResending]=useState(false);const [snd,setSnd]=useState<any>(null);useEffect(()=>{request('/invite-sender').then(setSnd).catch(()=>{})},[]);
  useEffect(()=>{setEdit(!!startEdit);load()},[id]);
  useEffect(()=>{if(m?.kind==='room'&&m.meeting_id&&m.editable)request(`/rooms/${m.meeting_id}/host`).then((r:any)=>setHostCode(r.host_code||'')).catch(()=>{})},[m?.meeting_id,m?.kind,m?.editable]);
  if(err)return <section className="panel"><p className="syncerr" role="alert">{err}</p><button className="secondary" onClick={onBack}>Back to meetings</button></section>;
  if(!m)return <section className="panel muted">Loading meeting…</section>;
  const link:string=m.join_url||'';const room=m.kind==='room';
  const resend=async()=>{setResending(true);try{const r=await request(`/meetings/${id}/resend-invites`,{method:'POST',body:JSON.stringify({})});notice(r.message||'Sent.');load()}catch(e:any){notice(e.message)}finally{setResending(false)}};
  const copy=async(what:string,text:string)=>{try{await navigator.clipboard.writeText(text);setCopied(what);setTimeout(()=>setCopied(''),2000)}catch{window.prompt('Copy this:',text)}};
  const invitation=[`${m.title}`,'',`When: ${whenText(m.start_at,m.duration_minutes)}`,'',link&&`Join: ${link}`,m.meeting_id&&`Meeting ID: ${m.meeting_id}`,m.passcode&&`Passcode: ${m.passcode}`,m.access==='signed_in'?'Sign in with your account to join.':'',m.agenda&&`\n${m.agenda}`].filter(x=>x!==''&&x!==false&&x!==undefined).join('\n');
  if(edit)return <MeetingForm request={request} isAdmin={isAdmin} goSettings={goSettings} initial={m} onCancel={()=>setEdit(false)} onSaved={r=>{setM(r);setEdit(false);notice(r.message||'Meeting saved.');onChanged()}}/>;
  const row=(k:string,v:React.ReactNode)=><div className="md-row"><span>{k}</span><div>{v}</div></div>;
  const secText=!room?null:(m.access==='passcode'?'Passcode required':m.access==='signed_in'?'Only signed-in people can join':'Anyone with the link')+(m.waiting_room?' · Waiting room on':'');
  return <section className="panel md">
    <div className="panelhead"><button className="textbtn" onClick={onBack}><ArrowLeft size={15}/> All meetings</button></div>
    <h2 className="md-title">{m.title}</h2>
    {m.status==='cancelled'&&<p className="alert">This meeting was cancelled{room?' and its link no longer works':''}.</p>}
    {m.ended&&m.status!=='cancelled'&&<p className="alert">This meeting has ended.</p>}
    <div className="md-actions">
      {m.status!=='cancelled'&&!m.ended&&link&&(room?<a className="primary btnlike" href={link} onClick={e=>{e.preventDefault();location.hash=new URL(link).hash}}><Video size={16}/> Start</a>:<JoinButton url={link}/>)}
      <button className="secondary" onClick={()=>copy('all',invitation)}><Copy size={15}/> {copied==='all'?'Invitation copied':'Copy invitation'}</button>
      {m.editable&&<button className="secondary" onClick={()=>setEdit(true)}><Pencil size={15}/> Edit</button>}
      {!m.editable&&m.kind==='calendar'&&m.status!=='cancelled'&&onCopy&&<button className="secondary" title="This meeting comes from your calendar app, so it cannot be changed here" onClick={()=>onCopy(m)}><Pencil size={15}/> Create an editable iSift copy</button>}
      {m.kind!=='calendar'&&<button className="secondary danger" onClick={()=>setDel(true)}><Trash2 size={15}/> Delete</button>}
    </div>
    <div className="md-rows">
      {row('Time',whenText(m.start_at,m.duration_minutes))}
      {m.agenda&&row('Description',<span style={{whiteSpace:'pre-wrap'}}>{m.agenda}</span>)}
      {m.meeting_id&&row('Meeting ID',<><code>{m.meeting_id}</code> <button className="textbtn inline" onClick={()=>copy('id',m.meeting_id)}>{copied==='id'?'Copied':'Copy'}</button></>)}
      {room&&row('Passcode',m.passcode?<><code>{m.passcode}</code> <button className="textbtn inline" onClick={()=>copy('pc',m.passcode)}>{copied==='pc'?'Copied':'Copy'}</button></>:<span className="muted">None</span>)}
      {secText&&row('Security',secText)}
      {room&&hostCode&&row('Host code',<><code>{hostCode}</code> <button className="textbtn inline" onClick={()=>copy('hc',hostCode)}>{copied==='hc'?'Copied':'Copy'}</button> <span className="muted small">Private. Enter it on the join page to be recognised as the host from any browser. Do not share it with guests.</span></>)}
      {link?row('Invite link',<><a href={link} onClick={e=>{if(room){e.preventDefault();location.hash=new URL(link).hash}}} className="md-link">{link}</a> <button className="textbtn inline" onClick={()=>copy('link',link)}>{copied==='link'?'Copied':'Copy link'}</button></>):row('Invite link',<span className="muted">This meeting has no online link.</span>)}
      {room&&row('Options',[m.options.mute_on_entry&&'Participants muted on entry',m.options.video_off_on_entry&&'Participants’ video off on entry',m.options.host_video_off&&'Host video off on start',m.options.virtual_room===false&&'Virtual room off (gallery only)',m.options.open_room&&'Open room: anyone can start or join any time',m.options.auto_record&&'Records automatically'].filter(Boolean).join(' · ')||<span className="muted">None</span>)}
      {room&&row('Invited',m.invitees?.length?<>{m.invitees.join(', ')} <button className="textbtn inline" disabled={resending} onClick={resend}>{resending?'Sending…':'Send invitations again'}</button></>:<span className="muted">Nobody yet. Use Edit to invite people.</span>)}
      {room&&snd&&row('Invitations go from',snd.connected?<b>{snd.from}</b>:snd.via_app?<span><b>{snd.name||snd.login} via iSift</b> <span className="muted small">(replies go to {snd.login}; answers are recorded here and emailed to you. To send from {snd.login} itself, add it in Mail, Add account.)</span></span>:<span className="syncerr">No email can be sent yet. Connect {snd.login} in Mail (Add account), or ask the administrator to set up the app's email.</span>)}
      {m.series&&row('Repeats','Part of a recurring series with one link for every meeting.')}
      {(m.kind==='teams'||m.kind==='meet')&&row(PLAT[m.kind],<span className="muted">Booked in {PLAT[m.kind]}. Changes to the time here do not change the {PLAT[m.kind]} event; change it there too.</span>)}
      {m.kind==='zoom'&&row('Zoom',<span className="muted">The passcode is part of the Zoom link. Change the time or settings in Zoom as well as here.</span>)}
    </div>
    {m.kind!=='calendar'&&<Replies id={m.id} request={request} notice={notice} onChanged={onChanged} reload={load}/>}
    {del&&<DeleteMeeting target={{id:m.id,title:m.title,series:!!m.series,room:room}} request={request} onClose={()=>setDel(false)} onDone={msg=>{notice(msg);onChanged();onBack()}}/>}
    <div className="md-invite"><div className="md-invhead"><b>Invitation</b><button className="secondary" onClick={()=>copy('all2',invitation)}>{copied==='all2'?'Copied':'Copy invitation'}</button></div><pre>{invitation}</pre></div>
  </section>;
}


/** Who answered the invitation, and the times people suggested. The host can move the meeting to a suggested time in one click. */
function Replies({id,request,notice,onChanged,reload}:{id:string;request:any;notice:(m:string)=>void;onChanged:()=>void;reload:()=>void}){
  const [d,setD]=useState<any>(null);const [busy,setBusy]=useState('');
  const load=()=>request(`/meetings/${id}/responses`).then(setD).catch(()=>setD(null));
  useEffect(()=>{load()},[id]);
  if(!d||!d.responses.length)return null;
  const L:any={accepted:'Accepted',tentative:'Maybe',declined:'Declined',proposed:'Suggested another time',waiting:'No reply yet'};
  const when=(iso:string)=>new Date(iso).toLocaleString(undefined,{weekday:'short',day:'numeric',month:'short',hour:'numeric',minute:'2-digit'});
  const use=async(email:string)=>{setBusy(email);try{const r=await request(`/meetings/${id}/accept-proposal`,{method:'POST',body:JSON.stringify({email})});notice(r.message);onChanged();reload();load()}catch(e:any){notice(e.message)}finally{setBusy('')}};
  const c=d.counts;
  return <div className="md-invite"><div className="md-invhead"><b>Replies</b><span className="muted small">{c.accepted} accepted · {c.tentative} maybe · {c.declined} declined · {c.proposed} suggested a new time · {c.waiting} waiting</span></div>
    <ul className="md-replies" style={{listStyle:'none',padding:0,margin:0,display:'grid',gap:6}}>{d.responses.map((r:any)=><li key={r.email} style={{display:'flex',gap:8,flexWrap:'wrap',alignItems:'center'}}>
      <span style={{minWidth:200}}>{r.email}</span><b>{L[r.status]||r.status}</b>
      {r.status==='proposed'&&r.proposed_start&&<><span>{when(r.proposed_start)}</span><button className="primary" disabled={!!busy} onClick={()=>use(r.email)}>{busy===r.email?'Moving…':'Use this time'}</button></>}
      {r.note&&<span className="muted">“{r.note}”</span>}</li>)}</ul></div>;
}

/** Popup window for changing a scheduled meeting (opened from the Meetings list). */
export function EditMeetingModal({id,request,isAdmin,goSettings,onClose,onSaved,onCopy}:{id:string;request:any;isAdmin?:boolean;goSettings?:()=>void;onClose:()=>void;onSaved:(msg:string)=>void;onCopy?:(m:any)=>void}){
  const [m,setM]=useState<any>(null);const [err,setErr]=useState('');
  useEffect(()=>{request(`/meetings/${id}/details`).then(setM).catch((e:any)=>setErr(e.message))},[id]);
  return <Modal title="Modify meeting" wide onClose={onClose}>
    {err&&<><p className="syncerr" role="alert">{err}</p><div className="actions"><button className="secondary" onClick={onClose}>Close</button></div></>}
    {!m&&!err&&<p className="muted">Loading…</p>}
    {m&&!m.editable&&<><p className="alert">{m.status==='cancelled'?'This meeting was cancelled and cannot be changed.':'This meeting comes from your calendar. Change it in your calendar app.'}</p><div className="actions">{onCopy&&m.status!=='cancelled'&&<button className="primary" onClick={()=>{onClose();onCopy(m)}}>Create an editable iSift copy</button>}<button className="secondary" onClick={onClose}>Close</button></div></>}
    {m&&m.editable&&<MeetingForm request={request} isAdmin={isAdmin} goSettings={goSettings} initial={m} onCancel={onClose} onSaved={r=>onSaved(r.message||'Meeting saved.')}/>}
  </Modal>;
}
