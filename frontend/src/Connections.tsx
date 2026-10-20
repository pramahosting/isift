import React,{useEffect,useState} from 'react';
import {canLinkFile,linkCalendarFile} from './linkedCalendar';
import {downloadWindowsHelper} from './winHelper';
import {Modal} from './Workspace';
import {Link2,Trash2,RefreshCw,Video,CalendarPlus,CheckCircle2,AlertTriangle,Upload,Plus,Mail,LogIn,Download,Monitor,CalendarDays,ShieldCheck} from 'lucide-react';

export const PROVIDER_LABEL:Record<string,string>={room:'Meeting room',zoom:'Zoom',teams:'Teams',meet:'Google Meet',webex:'Webex',calcom:'Cal.com video'};
export function providerOf(url?:string|null){
  if(!url)return null;let h='';try{h=new URL(url).hostname.toLowerCase()}catch{return null}
  try{const u=new URL(url);if(u.hash.startsWith('#/room/'))return 'room'}catch{}
  const is=(s:string)=>h===s||h.endsWith('.'+s);
  try{if(is('cal.com')&&new URL(url).pathname.startsWith('/video/'))return 'calcom'}catch{}
  if(is('zoom.us')||is('zoomgov.com'))return 'zoom';if(is('teams.microsoft.com')||is('teams.live.com'))return 'teams';
  if(is('meet.google.com'))return 'meet';if(is('webex.com'))return 'webex';return null;
}
export function JoinButton({url,small}:{url?:string|null;small?:boolean}){
  const p=providerOf(url);if(!url||!p)return null;
  const same=p==='room'&&(()=>{try{return new URL(url).origin===location.origin}catch{return false}})();
  return <a className={`joinbtn${small?' small':''}`} href={url} target={same?undefined:'_blank'} rel="noopener noreferrer" title={`Join ${PROVIDER_LABEL[p]} meeting`} aria-label={`Join ${PROVIDER_LABEL[p]} meeting`} onClick={e=>{e.stopPropagation();if(same){e.preventDefault();location.hash=new URL(url).hash}}}><Video size={14}/> {small?'Join':`Join ${PROVIDER_LABEL[p]}`}</a>;
}

export function suggestFor(email:string):{choice:string;label:string}{
  const d=(email.split('@')[1]||'').toLowerCase();
  if(/^(gmail|googlemail)\.com$/.test(d))return {choice:'ics:google',label:'Google / Gmail'};
  if(/^(yahoo\.|ymail\.|rocketmail\.)/.test(d))return {choice:'caldav:yahoo',label:'Yahoo'};
  if(/^(outlook|hotmail|live|msn)\./.test(d))return {choice:'ics:outlook',label:'Outlook.com / Microsoft'};
  if(/^(icloud|me|mac)\.com$/.test(d))return {choice:'caldav:icloud',label:'Apple iCloud'};
  if(/fastmail\./.test(d))return {choice:'caldav:fastmail',label:'Fastmail'};
  if(d)return {choice:'ics:outlook',label:'Work / other (often Microsoft 365)'};
  return {choice:'ics:google',label:''};
}

function MailPanel({info,request,run,busy}:{info:any;request:any;run:(f:()=>Promise<any>)=>void;busy:boolean}){
  const [prov,setProv]=useState('gmail');const [addr,setAddr]=useState('');const [pw,setPw]=useState('');const [imp,setImp]=useState(true);
  const [sh,setSh]=useState('');const [sp,setSp]=useState('587');const [ih,setIh]=useState('');const [ip,setIp]=useState('993');
  const pre=info.mail_presets.find((p:any)=>p.id===prov);const m=info.mail;
  const guess=(a:string)=>{setAddr(a);const d=(a.split('@')[1]||'').toLowerCase();setProv(/^(gmail|googlemail)\./.test(d)?'gmail':/^yahoo\.|^ymail\./.test(d)?'yahoo':/^(outlook|hotmail|live|msn)\./.test(d)?'outlook':/^(icloud|me|mac)\.com$/.test(d)?'icloud':prov)};
  return <section className="panel">
    <div className="panelhead"><h2>Your mail account</h2><span className="muted">Send meeting invitations; pick up invitations from your inbox</span></div>
    {m?<div className="conn-row"><div>{m.ok===false?<AlertTriangle size={16} className="bad"/>:<CheckCircle2 size={16} className="good"/>}</div>
      <div className="grow"><b>{m.address}</b><small>{m.import_invites?'Sends invitations and reads calendar invitations from the inbox (mail is never stored)':'Sends invitations'}{m.error?` · ${m.error}`:''}</small></div>
      <button className="secondary" disabled={busy} onClick={()=>run(()=>request('/connections/mail/test',{method:'POST'}))}>Send test</button>
      <button className="iconbtn" title="Disconnect" disabled={busy} onClick={()=>window.confirm('Disconnect this mail account?')&&run(()=>request('/connections/mail',{method:'DELETE'}))}><Trash2 size={16}/></button></div>
    :<form className="conn-form" onSubmit={e=>{e.preventDefault();run(()=>request('/connections/mail',{method:'POST',body:JSON.stringify({provider:prov,address:addr,password:pw,import_invites:imp,smtp_host:sh||undefined,smtp_port:sp,imap_host:ih||undefined,imap_port:ip})}).then(r=>{setPw('');return r}))}}>
      <label>Email address<input type="email" value={addr} onChange={e=>guess(e.target.value)} placeholder="name@gmail.com" required autoComplete="off"/></label>
      <label>Provider<select value={prov} onChange={e=>setProv(e.target.value)}>{info.mail_presets.map((p:any)=><option key={p.id} value={p.id}>{p.label}</option>)}</select></label>
      <label className="span2">App password<input type="password" value={pw} onChange={e=>setPw(e.target.value)} autoComplete="new-password" required/></label>
      {prov==='other'&&<><label>Sending server (SMTP)<input value={sh} onChange={e=>setSh(e.target.value)} required/></label><label>Port<input value={sp} onChange={e=>setSp(e.target.value)}/></label><label>Reading server (IMAP)<input value={ih} onChange={e=>setIh(e.target.value)}/></label><label>Port<input value={ip} onChange={e=>setIp(e.target.value)}/></label></>}
      <label className="checklabel span2"><input type="checkbox" checked={imp} onChange={e=>setImp(e.target.checked)}/> Also add meeting invitations I receive in this inbox to my calendar (only the calendar data is read; mail is not stored or marked as read)</label>
      {pre?.how&&<p className="muted span2"><b>Where to get the app password:</b> {pre.how}</p>}
      <div className="actions span2"><button className="primary" disabled={busy||!addr||!pw}><Plus size={15}/> {busy?'Checking…':'Connect mail account'}</button></div>
    </form>}
  </section>;
}

export function ConnectionsPage({request,isAdmin,onChanged,goSettings,onUploadIcs,notify}:{request:any;isAdmin:boolean;onChanged:()=>void;goSettings:()=>void;onUploadIcs:(f:File)=>Promise<void>;notify:(m:string)=>void}){
  const [info,setInfo]=useState<any>(null);const [choice,setChoice]=useState('ics:google');const [email,setEmail]=useState('');const [url,setUrl]=useState('');const [label,setLabel]=useState('');
  const [user,setUser]=useState('');const [pw,setPw]=useState('');const [busy,setBusy]=useState(false);const [err,setErr]=useState('');
  const load=async()=>{try{setInfo(await request('/connections'))}catch(e:any){setErr(e.message)}};
  useEffect(()=>{load()},[]);
  const run=async(fn:()=>Promise<any>)=>{setBusy(true);setErr('');try{const r=await fn();if(r?.message)notify(r.message);await load();onChanged()}catch(e:any){setErr(e.message)}finally{setBusy(false)}};
  if(!info)return <section className="panel">{err||'Loading…'}</section>;
  const [mode,pid]=choice.split(':');const caldav=mode==='caldav';
  const preset=caldav?info.caldav_presets.find((p:any)=>p.id===pid):info.providers.find((p:any)=>p.id===pid);
  const pick=(em:string)=>{setEmail(em);const s=suggestFor(em);if(em.includes('@')){setChoice(s.choice);setUser(em)}};
  const comp=info.computer||{};
  const submit=(e:React.FormEvent)=>{e.preventDefault();run(async()=>{
    const r=caldav?await request('/connections/caldav',{method:'POST',body:JSON.stringify({provider:pid,label:label||email,url:pid==='other'?url:preset?.url,username:user,password:pw})})
      :await request('/connections/calendar-links',{method:'POST',body:JSON.stringify({provider:pid,label:label||email,url})});
    setUrl('');setPw('');setLabel('');setEmail('');return r})};
  return <div className="conn">
    <section className="cal-connect">
      <div className="cc-head"><span className="cc-ico"><CalendarDays size={22}/></span><div><b>Connect your calendar</b><p>Your meetings for today will appear on the dashboard. Pick the way that suits you.</p></div></div>
      <div className="cc-opts">
        <div className="cc-opt best"><span className="cc-tag">Recommended</span><span className="cc-oi"><Link2 size={20}/></span><b>Calendar link</b><small>Paste your private Google, Outlook or iCloud link once. It then stays up to date by itself.</small>
          <button type="button" className="primary" onClick={()=>{const f=document.querySelector('.conn-form') as HTMLElement|null;f?.scrollIntoView({behavior:'smooth',block:'center'});(f?.querySelector('input') as HTMLInputElement|null)?.focus()}}>Add a link</button></div>
        <div className="cc-opt"><span className="cc-oi"><Upload size={20}/></span><b>Calendar file</b><small>Choose an .ics file exported from Outlook, Google or Apple Calendar. Refresh by exporting again.</small>
          <div className="cc-btns"><label className="secondary cal-up">{busy?'Reading…':'Choose .ics file'}<input type="file" accept=".ics,.ical,text/calendar" hidden disabled={busy} onChange={e=>{const f=e.target.files?.[0];e.target.value='';if(f)run(async()=>{await onUploadIcs(f)})}}/></label>
            {canLinkFile()&&<button type="button" className="textbtn" disabled={busy} title="Chrome and Edge remember the file and re-read it each time you open iSift" onClick={()=>run(async()=>{const f=await linkCalendarFile();if(f)await onUploadIcs(f)})}>Keep it linked</button>}
            {/windows/i.test(navigator.userAgent)&&<button type="button" className="textbtn" title="Finds .ics files on this laptop and, only if you agree, adds them to your calendar" onClick={()=>downloadWindowsHelper(window.location.origin)}>Windows helper</button>}</div></div>
      </div>
      <small className="cc-note"><ShieldCheck size={13}/> Private to your account. A website can’t read the calendar on your computer by itself, so iSift never searches your files.</small>
    </section>
    <OutlookCard o={info.outlook||{}} request={request} isAdmin={isAdmin} goSettings={goSettings} notify={notify} busy={busy} run={run}/>
    {(comp.note||comp.outlook_accounts?.length>0||comp.in_use)&&<section className="panel">
      <div className="panelhead"><h2>Outlook on this computer</h2></div>
      {comp.in_use&&<p className="muted"><CheckCircle2 size={14} className="good"/> Reading {comp.source}.{comp.outlook_accounts?.length>0&&<> Accounts: {comp.outlook_accounts.join(', ')}.</>}</p>}
      {comp.note&&<p className="note-box">{comp.note}</p>}
    </section>}
    <section className="panel">
      <div className="panelhead"><h2>Add a calendar account</h2><span className="muted">Gmail, Yahoo, Outlook.com, iCloud, work accounts</span></div>
      <p className="muted">Type the email address of an account you use in Outlook and this page picks the right method. Meetings for the next 7 days are added and refreshed automatically; Zoom, Teams, Meet and Webex links become Join buttons.</p>
      {info.links.length>0&&<div className="conn-list">{info.links.map((l:any)=><div className="conn-row" key={l.id}>
        <div>{l.ok===false?<AlertTriangle size={16} className="bad"/>:<CheckCircle2 size={16} className="good"/>}</div>
        <div className="grow"><b>{l.label}</b><small>{l.kind==='caldav'?'CalDAV · ':''}{l.host}{l.error?` · ${l.error}`:l.at?` · checked ${new Date(l.at).toLocaleString()}`:''}</small></div>
        <button className="iconbtn" title="Remove this calendar" disabled={busy} onClick={()=>window.confirm('Remove this calendar? Meetings already added stay.')&&run(()=>request(`/connections/calendar-links/${l.id}`,{method:'DELETE'}))}><Trash2 size={16}/></button></div>)}
        <button className="secondary" disabled={busy} onClick={()=>run(()=>request('/connections/sync',{method:'POST'}))}><RefreshCw size={15}/> Refresh now</button></div>}
      <form className="conn-form" onSubmit={submit}>
        <label className="span2">Email address of the account<input type="email" value={email} onChange={e=>pick(e.target.value)} placeholder="name@gmail.com" autoComplete="off"/>{email.includes('@')&&<small className="muted">Suggested method: {suggestFor(email).label}</small>}</label>
        <label>Method<select value={choice} onChange={e=>setChoice(e.target.value)}>
          <optgroup label="Private calendar link">{info.providers.map((p:any)=><option key={p.id} value={`ics:${p.id}`}>{p.label}</option>)}</optgroup>
          <optgroup label="Sign in with an app password (CalDAV)">{info.caldav_presets.map((p:any)=><option key={p.id} value={`caldav:${p.id}`}>{p.label}</option>)}</optgroup></select></label>
        <label>Name (optional)<input value={label} onChange={e=>setLabel(e.target.value)} placeholder="e.g. Work Gmail" maxLength={80}/></label>
        {caldav?<>
          {pid==='other'&&<label className="span2">CalDAV server address<input value={url} onChange={e=>setUrl(e.target.value)} placeholder="https://…" required/></label>}
          <label>Username<input value={user} onChange={e=>setUser(e.target.value)} autoComplete="off" required/></label>
          <label>App password<input type="password" value={pw} onChange={e=>setPw(e.target.value)} autoComplete="new-password" required/></label>
        </>:<label className="span2">Calendar link<input value={url} onChange={e=>setUrl(e.target.value)} placeholder="https://… or webcal://…" inputMode="url" autoComplete="off" required/></label>}
        {preset?.how&&<p className="muted span2"><b>Where to find it:</b> {preset.how}</p>}
        <div className="actions span2"><button className="primary" disabled={busy||(caldav?!(user&&pw):!url.trim())}><Plus size={15}/> {busy?'Checking…':'Add calendar'}</button>
          </div>
        <p className="muted span2 small">Links and passwords work like keys: they are stored encrypted, never shown again, and only used to read your calendar. Remove them any time. Use an app password, never your main account password.</p>
      </form>
      {err&&<p className="syncerr" role="alert">{err}</p>}
      {info.uploaded&&<p className="muted">An uploaded calendar file is also in use.</p>}
    </section>
    <MailPanel info={info} request={request} run={run} busy={busy}/>
    <section className="panel">
      <div className="panelhead"><h2>Meeting apps</h2></div>
      <div className="conn-row"><div><Video size={18}/></div><div className="grow"><b>Zoom</b><small>{info.zoom.configured?'Connected: new Zoom meetings can be created here and official transcripts fetched after a meeting (Zoom cloud recording with audio transcript must be on).':'Not set up yet. Zoom links in your calendar still show a Join button.'}</small></div>
        {isAdmin?<>{info.zoom.configured&&<button className="secondary" disabled={busy} onClick={()=>run(()=>request('/connections/zoom/test',{method:'POST'}))}>Test</button>}<button className="secondary" onClick={goSettings}>{info.zoom.configured?'Edit':'Set up'}</button></>:!info.zoom.configured&&<small className="muted">Ask an administrator.</small>}</div>
      <div className="conn-row"><div><Video size={18}/></div><div className="grow"><b>Meeting rooms in this app</b><small>Start a video meeting from the Meetings page. Share the link; guests join in any browser, with chat, screen sharing and optional recording.</small></div></div>
      <div className="conn-row"><div><Video size={18}/></div><div className="grow"><b>Microsoft Teams / Microsoft 365</b><small>{info.microsoft.configured?'Connected through Microsoft 365 (calendar and official transcripts).':'Not set up. An administrator can add it in Admin Console > Microsoft Entra and Graph.'}</small></div></div>
      <div className="conn-row"><div><Video size={18}/></div><div className="grow"><b>Google Meet and Webex</b><small>Join links in your calendar events are recognised.</small></div></div>
    </section>
  </div>;
}

export function JoinById({className=''}:{className?:string}){
  const [v,setV]=useState('');const [bad,setBad]=useState(false);
  const go=(e:React.FormEvent)=>{e.preventDefault();const m=v.match(/#\/room\/([A-Za-z0-9]{6,40})/)||v.trim().match(/^([A-Za-z0-9]{6,40})$/);if(!m){setBad(true);return}setBad(false);location.hash='#/room/'+m[1]};
  return <form className={`joinbyid ${className}`} onSubmit={go} aria-label="Join a meeting"><input value={v} onChange={e=>{setV(e.target.value);setBad(false)}} placeholder="Meeting ID or link" aria-label="Meeting ID or link" aria-invalid={bad}/><button className="secondary">Join</button>{bad&&<small className="syncerr" role="alert">Enter the meeting ID or the full link.</small>}</form>;
}

const RECENT_KEY='isift.recentRooms';
const roomCode=(v:string)=>{const m=v.match(/#\/room\/([A-Za-z0-9]{6,40})/)||v.trim().match(/^([A-Za-z0-9]{6,40})$/);return m?m[1]:''};
export function rememberRoom(code:string,title:string){try{const l=JSON.parse(localStorage.getItem(RECENT_KEY)||'[]').filter((x:any)=>x.code!==code);l.unshift({code,title,at:new Date().toISOString()});localStorage.setItem(RECENT_KEY,JSON.stringify(l.slice(0,20)))}catch{}}

/** Like Zoom's "Join meeting" window: a meeting ID box with a drop-down of your past meetings, your name, and options for audio and video. */
export function JoinDialog({request,name:initialName,onClose}:{request?:any;name?:string;onClose:()=>void}){
  const [v,setV]=useState('');const [open,setOpen]=useState(false);const [bad,setBad]=useState(false);
  const [name,setName]=useState(()=>{try{return localStorage.getItem('isift.joinName')||initialName||''}catch{return initialName||''}});
  const [noAudio,setNoAudio]=useState(()=>{try{return localStorage.getItem('isift.joinNoAudio')==='1'}catch{return false}});
  const [noVideo,setNoVideo]=useState(()=>{try{return localStorage.getItem('isift.joinNoVideo')==='1'}catch{return false}});
  const [recent,setRecent]=useState<{code:string;title:string;at?:string}[]>(()=>{try{return JSON.parse(localStorage.getItem(RECENT_KEY)||'[]')}catch{return []}});
  useEffect(()=>{if(!name&&initialName)setName(initialName)},[initialName]);
  useEffect(()=>{if(!request)return;request('/rooms-recent').then((d:any)=>setRecent(r=>{const seen=new Set<string>(),all=[...(d.rooms||[]),...r].filter(x=>!seen.has(x.code)&&seen.add(x.code));return all.sort((a:any,b:any)=>String(b.at||'').localeCompare(String(a.at||''))).slice(0,15)})).catch(()=>{})},[]);
  const code=roomCode(v);
  const when=(t?:string)=>{try{return t?new Date(t).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric'}):''}catch{return ''}};
  const matches=recent.filter(r=>!v.trim()||r.code.toLowerCase().includes(v.trim().toLowerCase())||(r.title||'').toLowerCase().includes(v.trim().toLowerCase()));
  const join=(e?:React.FormEvent)=>{e?.preventDefault();if(!code){setBad(true);return}
    try{localStorage.setItem('isift.joinName',name.trim());localStorage.setItem('isift.joinNoAudio',noAudio?'1':'0');localStorage.setItem('isift.joinNoVideo',noVideo?'1':'0');sessionStorage.setItem('isift.join',JSON.stringify({name:name.trim(),audio:!noAudio,video:!noVideo}))}catch{}
    onClose();location.hash='#/room/'+code};
  return <Modal title="Join meeting" onClose={onClose}><form className="joindlg" onSubmit={join}>
    <div className="jd-combo"><input value={v} onChange={e=>{setV(e.target.value);setBad(false);setOpen(true)}} placeholder="Meeting ID, link or a past meeting" aria-label="Meeting ID or link" aria-invalid={bad} aria-expanded={open} autoFocus autoComplete="off"/>
      <button type="button" className="jd-arrow" aria-label="Show my past meetings" title="My past meetings" onClick={()=>setOpen(o=>!o)}>▾</button>
      {open&&<ul className="jd-list" role="listbox" aria-label="My past meetings">{matches.length?matches.map(r=><li key={r.code}><button type="button" role="option" onClick={()=>{setV(r.code);setOpen(false);setBad(false)}}><b>{r.title||'Meeting'}</b><small>{r.code}{r.at?` · ${when(r.at)}`:''}</small></button></li>):<li className="muted small jd-none">{recent.length?'No past meeting matches.':'Your past meetings will appear here.'}</li>}</ul>}</div>
    {bad&&<small className="syncerr" role="alert">Enter the meeting ID or the full link.</small>}
    <input value={name} onChange={e=>setName(e.target.value)} placeholder="Your name" aria-label="Your name" maxLength={60}/>
    <label className="check"><input type="checkbox" checked={noAudio} onChange={e=>setNoAudio(e.target.checked)}/> Don’t connect to audio</label>
    <label className="check"><input type="checkbox" checked={noVideo} onChange={e=>setNoVideo(e.target.checked)}/> Turn off my video</label>
    <div className="jd-actions"><button type="submit" className="primary" disabled={!code}>Join</button><button type="button" className="secondary" onClick={onClose}>Cancel</button></div>
  </form></Modal>;
}

/** The Dashboard tile and Meetings button that open the Join window. */
export function JoinWindowButton({request,name,tile}:{request?:any;name?:string;tile?:boolean}){
  const [open,setOpen]=useState(false);
  return <>{tile?<button className="tile cobalt" onClick={()=>setOpen(true)}><span className="ticon"><Plus size={24}/></span><b>Join</b><small>With a meeting ID or link</small></button>:<button className="secondary" onClick={()=>setOpen(true)}><LogIn size={16}/> Join with an ID</button>}{open&&<JoinDialog request={request} name={name} onClose={()=>setOpen(false)}/>}</>;
}

/** The Recordings tab: a table of the person's own meeting recordings kept in the cloud, each with Download and Delete. */
export function RecordingsTable({request,download}:{request:any;download:(p:string,n:string)=>void}){
  const [rows,setRows]=useState<any[]|null>(null);const [err,setErr]=useState('');const [busy,setBusy]=useState('');
  const load=()=>request('/recordings').then((r:any)=>{setRows(r);setErr('')}).catch((e:any)=>setErr(e.message||'Recordings could not be loaded.'));
  useEffect(()=>{load()},[]);
  const mb=(n:number)=>n>=1048576?`${(n/1048576).toFixed(1)} MB`:`${Math.max(1,Math.round(n/1024))} KB`;
  const del=async(r:any)=>{if(!window.confirm(`Delete the recording of "${r.title||'this meeting'}" permanently? This cannot be undone.`))return;setBusy(r.id);try{await request(`/recordings/${r.id}`,{method:'DELETE'});await load()}catch(e:any){setErr(e.message||'Could not delete.')}finally{setBusy('')}};
  return <section className="panel"><div className="panelhead"><h2>Meeting recordings</h2><span className="muted">Only you, the host, can see these</span></div>
    {err&&<p className="syncerr" role="alert">{err}</p>}
    {rows===null&&!err&&<p className="muted">Loading…</p>}
    {rows&&!rows.length&&<div className="empty">No recordings stored in iSift yet. Recordings are always saved to your own computer when you stop recording; tick Also store in cloud during a meeting to keep a copy here as well.</div>}
    {rows&&rows.length>0&&<div className="tablewrap"><table className="modtable rec-table"><thead><tr><th>Meeting</th><th>Recorded</th><th>Type</th><th>Size</th><th>Kept until</th><th aria-label="Actions"/></tr></thead><tbody>
      {rows.map(r=><tr key={r.id}><td data-label="Meeting"><b>{r.title||'Meeting'}</b></td><td data-label="Recorded">{new Date(r.created_at).toLocaleString()}</td><td data-label="Type">{r.has_video?'Video':'Audio'}</td><td data-label="Size">{mb(r.size_bytes)}</td><td data-label="Kept until">{r.expires_at?new Date(r.expires_at).toLocaleDateString():'Until deleted'}</td>
        <td className="rec-act"><button className="secondary" disabled={r.available===false||busy===r.id} title={r.available===false?'The recording file is no longer available.':'Save a copy to this computer'} onClick={()=>download(`/recordings/${r.id}/file`,`${r.title||'meeting'}.${r.storage==='r2'&&r.has_video?'mp4':'webm'}`)}><Download size={14}/> Download</button>
          <button className="secondary danger" disabled={busy===r.id} onClick={()=>del(r)}><Trash2 size={14}/> Delete</button></td></tr>)}</tbody></table></div>}
  </section>;
}


const OUTLOOK_SCOPES=['User.Read','Calendars.Read','Mail.Read','Contacts.Read'];
/** Opens the Microsoft sign-in popup and pulls calendar and email. Used by the Connections, Calendar and Email pages. */
export async function outlookSignIn(o:any,request:any){
  const {PublicClientApplication}=await import('@azure/msal-browser');
  const pca=new PublicClientApplication({auth:{clientId:o.client_id,authority:o.authority,redirectUri:location.origin},cache:{cacheLocation:'sessionStorage'}});
  await pca.initialize();
  let tok:string|undefined;const acct=pca.getAllAccounts()[0];
  if(acct){try{tok=(await pca.acquireTokenSilent({scopes:OUTLOOK_SCOPES,account:acct})).accessToken}catch{}}
  if(!tok){const res=await pca.loginPopup({scopes:OUTLOOK_SCOPES,prompt:'select_account'});tok=res.accessToken}
  return await request('/connections/microsoft/pull',{method:'POST',body:JSON.stringify({access_token:tok})});
}
export function outlookError(e:any){const m=String(e?.errorCode||e?.message||e);return /user_cancelled|popup_window_error|empty_window/.test(m)?'The sign-in window was closed or blocked. Allow pop-ups for this page and try again.':(e?.message||'Sign-in failed.')}
/** Sign in to Outlook / Microsoft 365 in a popup, then pull the person's calendar and recent email into iSift. */
function OutlookCard({o,request,isAdmin,goSettings,notify,busy,run}:{o:any;request:any;isAdmin:boolean;goSettings:()=>void;notify:(m:string)=>void;busy:boolean;run:(fn:()=>Promise<any>)=>void}){
  const [setup,setSetup]=useState(false);const [working,setWorking]=useState(false);const [err,setErr]=useState('');
  const connect=()=>{
    if(!o.ready){setSetup(true);return}
    setErr('');setWorking(true);
    run(async()=>{try{
      const {PublicClientApplication}=await import('@azure/msal-browser');
      const pca=new PublicClientApplication({auth:{clientId:o.client_id,authority:o.authority,redirectUri:location.origin},cache:{cacheLocation:'sessionStorage'}});
      await pca.initialize();
      let tok:string|undefined;const acct=pca.getAllAccounts()[0];
      if(acct){try{tok=(await pca.acquireTokenSilent({scopes:OUTLOOK_SCOPES,account:acct})).accessToken}catch{}}
      if(!tok){const res=await pca.loginPopup({scopes:OUTLOOK_SCOPES,prompt:'select_account'});tok=res.accessToken}
      return await request('/connections/microsoft/pull',{method:'POST',body:JSON.stringify({access_token:tok})});
    }catch(e:any){const m=String(e?.errorCode||e?.message||e);setErr(/user_cancelled|popup_window_error|empty_window/.test(m)?'The sign-in window was closed or blocked. Allow pop-ups for this page and try again.':(e?.message||'Sign-in failed.'));return null}finally{setWorking(false)}})};
  const forget=()=>{if(window.confirm('Remove the stored email summaries? Meetings already added stay.'))run(()=>request('/connections/microsoft/outlook',{method:'DELETE'}))};
  return <section className="panel outlook-card">
    <div className="panelhead"><h2><Mail size={18}/> Outlook / Microsoft 365</h2>{o.connected&&<span className="muted"><CheckCircle2 size={14} className="good"/> {o.account||'Signed in'}</span>}</div>
    <p className="muted">Sign in to your Outlook or Microsoft 365 account in a popup window. iSift then pulls your calendar (next 30 days), your recent email and your contacts. Your password is typed only into Microsoft’s window, never into iSift.</p>
    <div className="actions"><button className="primary" disabled={busy||working} onClick={connect}><LogIn size={15}/> {working?'Waiting for sign-in…':o.connected?'Sign in again and refresh':'Sign in with Microsoft'}</button>{o.connected&&<button className="secondary" onClick={forget}>Remove email summaries</button>}</div>
    {err&&<p className="syncerr" role="alert">{err}</p>}
    {o.connected&&<div className="ol-sum"><small className="muted">Last pulled {o.at?new Date(o.at).toLocaleString():''} · {o.meetings} meetings · {o.mail_count} emails</small>
      {o.mail?.length>0&&<div className="ol-mail" aria-label="Recent email">{o.mail.map((m:any,i:number)=><div key={i} className={m.read?'':'unread'}><b>{m.from||'Unknown'}</b><span>{m.subject}</span></div>)}</div>}</div>}
    <small className="muted">Prefer not to sign in? If Outlook is installed on this Windows computer, tick “allow the calendar on this computer” under Outlook on this computer below (administrator setting), or add a calendar link.</small>
    {setup&&<Modal title="Microsoft sign-in is not set up" onClose={()=>setSetup(false)}><div className="ws-form"><p>The Microsoft sign-in popup needs an application (client) ID that has not been added in Settings yet.</p>{isAdmin?<p className="muted small">Open <b>Admin Console → Meeting platforms → Microsoft Teams and Microsoft 365</b>, enter the <b>Microsoft sign-in popup application ID</b> and press Save. The box explains how to create it in Microsoft Entra.</p>:<p className="muted small">Please ask your administrator to set up Microsoft sign-in under Admin Console → Meeting platforms.</p>}<div className="actions">{isAdmin&&<button className="primary" onClick={()=>{try{sessionStorage.setItem('isift.admintab','meetings')}catch{};setSetup(false);goSettings()}}>Open Admin Console</button>}<button className="secondary" onClick={()=>setSetup(false)}>Close</button></div></div></Modal>}
  </section>;
}
