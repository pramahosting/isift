import React,{useCallback,useEffect,useRef,useState} from 'react';
import {Board,ShapeShelf} from './Whiteboard';
import {Mail,LogIn,Upload,Video,MessageSquare,Users,Plus,Trash2,Send,Copy,Mic,MonitorUp,X,UserPlus,FileText,PenLine,Undo2,Eraser,Check,Share2,Table2,Presentation,ChevronsLeft,ChevronsRight} from 'lucide-react';

const baseUrl=()=>location.origin+location.pathname;
export const roomLink=(code:string)=>`${baseUrl()}#/room/${code}`;
const copyText=async(t:string)=>{try{await navigator.clipboard.writeText(t)}catch{window.prompt('Copy this:',t)}};

export {Modal} from './Modal';
import {Modal} from './Modal';
import {ShareDialog,SharedBanner,CommentsPanel} from './Sharing';
import {WordEditor,SheetEditor,DeckEditor} from './DocsEditors';

/** Zoom-style "Host": choose video on/off, share-screen-only, or the personal meeting ID, then start. */
export function HostDialog({request,onClose}:{request:any;onClose:()=>void}){
  const [video,setVideo]=useState(true);const [screen,setScreen]=useState(false);const [pmi,setPmi]=useState(false);const [err,setErr]=useState('');const [busy,setBusy]=useState(false);
  const start=async()=>{setBusy(true);setErr('');try{
    const code=pmi?(await request('/me/pmi')).code:(await request('/rooms',{method:'POST',body:JSON.stringify({base_url:baseUrl()})})).code;
    try{sessionStorage.setItem('isift.start',JSON.stringify({video:video&&!screen,screen}))}catch{}
    onClose();location.hash='#/room/'+code;
  }catch(e:any){setErr(e.message);setBusy(false)}};
  return <Modal title="Host a meeting" onClose={onClose}>
    <div className="ws-form">
      <label className="check"><input type="checkbox" checked={video&&!screen} disabled={screen} onChange={e=>setVideo(e.target.checked)}/> Start with my video on</label>
      <label className="check"><input type="checkbox" checked={screen} onChange={e=>setScreen(e.target.checked)}/> <MonitorUp size={15}/> Screen share only (start sharing your screen, camera off)</label>
      <label className="check"><input type="checkbox" checked={pmi} onChange={e=>setPmi(e.target.checked)}/> Use my Personal Meeting ID</label>
      {err&&<p className="syncerr" role="alert">{err}</p>}
      <div className="actions"><button className="primary" disabled={busy} onClick={start}><Video size={16}/> {busy?'Starting…':'Start meeting'}</button><button className="secondary" onClick={onClose}>Cancel</button></div>
    </div></Modal>;
}

/** Zoom-style "Test audio and video": camera preview and a live microphone level. */
export function TestAV({onClose}:{onClose:()=>void}){
  const vid=useRef<HTMLVideoElement>(null);const [level,setLevel]=useState(0);const [msg,setMsg]=useState('Allow the camera and microphone when your browser asks.');
  useEffect(()=>{let stop=false,raf=0,stream:MediaStream|null=null,ctx:AudioContext|null=null;
    (async()=>{try{stream=await navigator.mediaDevices.getUserMedia({audio:true,video:true});if(stop){stream.getTracks().forEach(t=>t.stop());return}
      if(vid.current)vid.current.srcObject=stream;setMsg('Say something: the bar should move.');
      ctx=new AudioContext();const an=ctx.createAnalyser();an.fftSize=256;ctx.createMediaStreamSource(stream).connect(an);const buf=new Uint8Array(an.frequencyBinCount);
      const tick=()=>{an.getByteFrequencyData(buf);setLevel(Math.min(100,Math.max(...buf)/2.2));raf=requestAnimationFrame(tick)};tick();
    }catch{try{stream=await navigator.mediaDevices.getUserMedia({audio:true});setMsg('No camera found or allowed, but the microphone works.')}catch{setMsg('The camera and microphone are blocked or missing. Check the browser permission icon, and that this page is https:// or localhost.')}}})();
    return()=>{stop=true;cancelAnimationFrame(raf);stream?.getTracks().forEach(t=>t.stop());ctx?.close().catch(()=>{})}},[]);
  return <Modal title="Test audio and video" onClose={onClose}><div className="ws-form"><video ref={vid} className="ws-preview" autoPlay playsInline muted/><div className="ws-meter" aria-label="Microphone level"><Mic size={15}/><span><i style={{width:level+'%'}}/></span></div><p className="muted small">{msg}</p><div className="actions"><button className="primary" onClick={onClose}>Done</button></div></div></Modal>;
}

/** Personal Meeting ID card. */
export function PmiCard({request}:{request:any}){
  const [p,setP]=useState<any>(null);const [done,setDone]=useState('');
  useEffect(()=>{request('/me/pmi').then(setP).catch(()=>{})},[]);
  if(!p)return null;const flash=(k:string)=>{setDone(k);setTimeout(()=>setDone(''),1800)};
  return <div className="pmi"><div><span className="muted small">Personal Meeting ID</span><b className="pmi-id">{p.pretty}</b><small className="muted">{p.open_room?'Open room: anyone can start or join, no passcode':`Passcode ${p.passcode||'none'}`} · always the same link</small><label className="check"><input type="checkbox" checked={!!p.open_room} onChange={async e=>setP(await request('/me/pmi',{method:'PATCH',body:JSON.stringify({open_room:e.target.checked})}))}/> Open room: no admitting, anyone can start or join any time</label></div>
    <div className="pmi-actions"><button className="secondary" onClick={()=>{copyText(p.pretty.replace(/ /g,''));flash('id')}}><Copy size={14}/> {done==='id'?'Copied':'Copy ID'}</button><button className="secondary" onClick={()=>{copyText(`Join my iSift meeting: ${roomLink(p.code)}\nMeeting ID: ${p.pretty}${p.passcode?`\nPasscode: ${p.passcode}`:''}`);flash('inv')}}><Copy size={14}/> {done==='inv'?'Copied':'Copy invitation'}</button><button className="primary" onClick={()=>{location.hash='#/room/'+p.code}}><Video size={14}/> Start</button></div></div>;
}

/** Start a video call with the people in a chat or contact selection, and drop the link into the chat. */
async function callChannel(request:any,cid:string){
  const r=await request('/rooms',{method:'POST',body:JSON.stringify({base_url:baseUrl(),title:'Video call'})});
  await request(`/chat/channels/${cid}/messages`,{method:'POST',body:JSON.stringify({text:`📹 Join my video call: ${roomLink(r.code)}${r.passcode?`  (passcode ${r.passcode})`:''}`})});
  location.hash='#/room/'+r.code;
}

/* ---------------- Contacts ---------------- */
export function ContactsPage({request,openChat,notify}:{request:any;openChat:(cid:string)=>void;notify:(m:string)=>void}){
  const [data,setData]=useState<any>({contacts:[],groups:[]});const [sel,setSel]=useState<string[]>([]);const [scope,setScope]=useState<string>('all');const [f,setF]=useState({name:'',email:'',phone:'',account:''});const [edit,setEdit]=useState<string>('');const [err,setErr]=useState('');const [gname,setGname]=useState('');const [q,setQ]=useState('');const [olBusy,setOlBusy]=useState(false);const [olMsg,setOlMsg]=useState('');const [olSetup,setOlSetup]=useState(false);
  const load=useCallback(()=>request('/contacts').then(setData).catch((e:any)=>setErr(e.message)),[request]);useEffect(()=>{load()},[load]);
  const save=async(e:React.FormEvent)=>{e.preventDefault();setErr('');try{if(edit)await request(`/contacts/${edit}`,{method:'PATCH',body:JSON.stringify(f)});else await request('/contacts',{method:'POST',body:JSON.stringify(f)});setF({name:'',email:'',phone:'',account:f.account});setEdit('');load()}catch(x:any){setErr(x.message)}};
  const del=async(c:any)=>{if(!window.confirm(`Remove ${c.name} from your contacts?`))return;await request(`/contacts/${c.id}`,{method:'DELETE'});setSel(s=>s.filter(x=>x!==c.id));load()};
  const chat=async(body:any,call=false)=>{setErr('');try{const ch=await request('/chat/channels',{method:'POST',body:JSON.stringify(body)});if(ch.skipped?.length)notify(`${ch.skipped.join(', ')} has no iSift account and was left out.`);if(call)await callChannel(request,ch.id);else openChat(ch.id)}catch(x:any){setErr(x.message)}};
  const mkGroup=async()=>{if(!gname.trim()||!sel.length)return;setErr('');try{await request('/contact-groups',{method:'POST',body:JSON.stringify({name:gname,contact_ids:sel})});setGname('');setSel([]);load()}catch(x:any){setErr(x.message)}};
  const outlookPull=async()=>{setErr('');setOlMsg('');setOlBusy(true);try{const info=(await request('/connections')).outlook||{};if(!info.ready){setOlSetup(true);return}const C=await import('./Connections');const r=await C.outlookSignIn(info,request);setOlMsg(r?.message||'Done.');load()}catch(e:any){const C=await import('./Connections');setErr(C.outlookError(e))}finally{setOlBusy(false)}};
  const desktopPull=async()=>{setErr('');setOlMsg('');setOlBusy(true);try{const r=await request('/connections/outlook-desktop/pull',{method:'POST'});setOlMsg(r.message);load()}catch(e:any){setErr(e.message)}finally{setOlBusy(false)}};
  const csvImport=async(f:File)=>{setErr('');setOlMsg('');try{const text=await f.text();const r=await request('/contacts/import-csv',{method:'POST',body:JSON.stringify({text,account:scope==='all'||scope==='__local'?'':scope})});setOlMsg(r.message);load()}catch(e:any){setErr(e.message)}};
  const lists:string[]=Array.from(new Set<string>(data.contacts.map((c:any)=>c.account||'').filter(Boolean))).sort();
  const countOf=(a:string)=>data.contacts.filter((c:any)=>(c.account||'')===a).length;
  const merged=(()=>{const m=new Map<string,any>();for(const c of data.contacts){const k=c.email||('n:'+c.name.toLowerCase());const e=m.get(k);if(e){if(c.account&&!e.sources.includes(c.account))e.sources.push(c.account);if(!c.account)e.local=true;if(!e.phone&&c.phone)e.phone=c.phone}else m.set(k,{...c,sources:c.account?[c.account]:[],local:!c.account})}return Array.from(m.values()).sort((a:any,b:any)=>a.name.localeCompare(b.name))})();
  const base=scope==='all'?merged:data.contacts.filter((c:any)=>(c.account||'')===(scope==='__local'?'':scope)).map((c:any)=>({...c,sources:[]}));
  const shown=base.filter((c:any)=>!q||(c.name+' '+c.email).toLowerCase().includes(q.toLowerCase()));
  const mergeAll=async()=>{setErr('');try{const r=await request('/contacts/merge',{method:'POST'});setOlMsg(r.message);setScope('__local');load()}catch(x:any){setErr(x.message)}};
  const toggle=(id:string)=>setSel(s=>s.includes(id)?s.filter(x=>x!==id):[...s,id]);
  return <div className="ws-two">
    <section className="panel"><div className="ct-wrap" style={{display:'flex',gap:12}}><aside className="ct-side" aria-label="Contact lists">
      <button className={scope==='all'?'on':''} onClick={()=>setScope('all')}><span className="nm">All contacts <small>merged view</small></span><small>{merged.length}</small></button>
      <button className={scope==='__local'?'on':''} onClick={()=>setScope('__local')}><span className="nm">iSift contacts</span><small>{countOf('')}</small></button>
      {lists.map(a=><button key={a} className={scope===a?'on':''} onClick={()=>setScope(a)} title={a}><span className="nm">{a}</span><small>{countOf(a)}</small></button>)}
      <button className="primary ct-merge" onClick={mergeAll} title="Copy every account's contacts into one iSift list, once per person"><Users size={14}/> Merge all into iSift list</button>
    </aside><div style={{flex:1,minWidth:0}}><div className="panelhead"><h2><Users size={18}/> {scope==='all'?'All contacts':scope==='__local'?'iSift contacts':scope}</h2><input className="ws-search" value={q} onChange={e=>setQ(e.target.value)} placeholder="Search contacts" aria-label="Search contacts"/></div>
      {sel.length>0&&<div className="ws-bar"><b>{sel.length} selected</b><button className="secondary" onClick={()=>chat({contact_ids:sel})}><MessageSquare size={14}/> Chat</button><button className="primary" onClick={()=>chat({contact_ids:sel},true)}><Video size={14}/> Video call</button><span className="ws-gform"><input value={gname} onChange={e=>setGname(e.target.value)} placeholder="Group name" aria-label="Group name"/><button className="secondary" onClick={mkGroup} disabled={!gname.trim()}>Save as group</button></span></div>}
      {shown.length?shown.map((c:any)=><div className="ws-row" key={c.id}><input type="checkbox" aria-label={`Select ${c.name}`} checked={sel.includes(c.id)} onChange={()=>toggle(c.id)}/><div className="avatar sm">{c.name[0]?.toUpperCase()}</div><div className="ws-main"><b>{c.name}</b>{(c.sources||[]).map((a:string)=><span key={a} className="ct-badge" title={a}>{a.split('@')[0]}</span>)}<small className="muted">{c.email||'No email'}{c.phone?` · ${c.phone}`:''}{c.user_id?'':c.email?' · not on iSift yet':''}</small></div>
        <div className="ws-acts"><button className="iconbtn" title="Chat" aria-label={`Chat with ${c.name}`} disabled={!c.user_id} onClick={()=>chat({contact_ids:[c.id]})}><MessageSquare size={16}/></button><button className="iconbtn" title="Video call" aria-label={`Video call ${c.name}`} disabled={!c.user_id} onClick={()=>chat({contact_ids:[c.id]},true)}><Video size={16}/></button><button className="textbtn" onClick={()=>{setEdit(c.id);setF({name:c.name,email:c.email,phone:c.phone,account:c.account||''})}}>Edit</button><button className="iconbtn" aria-label={`Remove ${c.name}`} onClick={()=>del(c)}><Trash2 size={15}/></button></div></div>)
        :<p className="muted pad">{data.contacts.length?'No contacts match.':'No contacts yet. Add someone on the right, or bring them in from Outlook.'}</p>}
    </div></div></section>
    <div className="ws-col">
      <form className="panel ws-form" onSubmit={save}><h2><UserPlus size={17}/> {edit?'Edit contact':'Add a contact'}</h2>
        <label>Name<input value={f.name} onChange={e=>setF({...f,name:e.target.value})} required maxLength={200}/></label>
        <label>Email<input type="email" value={f.email} onChange={e=>setF({...f,email:e.target.value})} placeholder="name@example.com"/></label>
        <label>Phone (optional)<input value={f.phone} onChange={e=>setF({...f,phone:e.target.value})}/></label>
        {!edit&&<label>Save in<select value={f.account} onChange={e=>setF({...f,account:e.target.value})}><option value="">iSift contacts</option>{lists.map(a=><option key={a} value={a}>{a}</option>)}</select></label>}
        {err&&<p className="syncerr" role="alert">{err}</p>}
        <div className="actions"><button className="primary">{edit?'Save':'Add contact'}</button>{edit&&<button type="button" className="secondary" onClick={()=>{setEdit('');setF({name:'',email:'',phone:'',account:''})}}>Cancel</button>}</div>
        <small className="muted">Chat and video calls work with contacts who have an iSift account (same email address).</small></form>
      <section className="panel ws-form"><h2><Mail size={17}/> Bring in from Outlook</h2>
        <p className="muted small">Sign in to Outlook in a popup and iSift pulls your contacts (and your calendar and email). Or press “Read Outlook on this computer” to read classic Outlook installed on this Windows laptop, no sign-in needed. Or import the CSV file you export from Outlook: File → Open &amp; Export → Import/Export → Export to a file → Comma Separated Values → Contacts.</p>
        <div className="actions"><button type="button" className="primary" disabled={olBusy} onClick={outlookPull}><LogIn size={15}/> {olBusy?'Waiting for sign-in…':'Sign in to Outlook'}</button><button type="button" className="secondary" disabled={olBusy} onClick={desktopPull} title="Windows with classic Outlook installed">Read Outlook on this computer</button><label className="secondary cal-up"><Upload size={15}/> Import Outlook CSV<input type="file" accept=".csv,text/csv" hidden onChange={e=>{const f=e.target.files?.[0];e.target.value='';if(f)csvImport(f)}}/></label></div>
        {olMsg&&<p className="muted" role="status">{olMsg}</p>}</section>{olSetup&&<Modal title="Microsoft sign-in is not set up" onClose={()=>setOlSetup(false)}><div className="ws-form"><p>The Microsoft sign-in popup needs an application (client) ID that has not been added in Settings yet. You can still import the CSV file exported from Outlook.</p><div className="actions"><button className="secondary" onClick={()=>setOlSetup(false)}>Close</button></div></div></Modal>}
      <section className="panel"><h2>Groups</h2>{data.groups.length?data.groups.map((g:any)=><div className="ws-row" key={g.id}><div className="ws-main"><b>{g.name}</b><small className="muted">{g.contact_ids.length} {g.contact_ids.length===1?'person':'people'}</small></div><div className="ws-acts"><button className="iconbtn" aria-label={`Chat with ${g.name}`} title="Group chat" onClick={()=>chat({group_id:g.id,name:g.name})}><MessageSquare size={16}/></button><button className="iconbtn" aria-label={`Video call ${g.name}`} title="Video call" onClick={()=>chat({group_id:g.id,name:g.name},true)}><Video size={16}/></button><button className="iconbtn" aria-label={`Delete group ${g.name}`} onClick={async()=>{if(window.confirm(`Delete the group ${g.name}? The contacts stay.`)){await request(`/contact-groups/${g.id}`,{method:'DELETE'});load()}}}><Trash2 size={15}/></button></div></div>):<p className="muted">Tick several contacts, name the group and save it.</p>}</section>
    </div></div>;
}

/* ---------------- Chat ---------------- */
function NewChat({request,onClose,onOpen}:{request:any;onClose:()=>void;onOpen:(id:string)=>void}){
  const [data,setData]=useState<any>({contacts:[],groups:[]});const [q,setQ]=useState('');const [sel,setSel]=useState<string[]>([]);const [grp,setGrp]=useState('');const [name,setName]=useState('');const [err,setErr]=useState('');const [busy,setBusy]=useState(false);
  useEffect(()=>{request('/contacts').then(setData).catch((e:any)=>setErr(e.message))},[request]);
  const seen=new Set<string>();const people=data.contacts.filter((c:any)=>{const k=c.email||c.name;if(seen.has(k))return false;seen.add(k);return true}).filter((c:any)=>!q||(c.name+' '+c.email).toLowerCase().includes(q.toLowerCase())).sort((a:any,b:any)=>a.name.localeCompare(b.name));
  const tog=(id:string)=>setSel(s=>s.includes(id)?s.filter(x=>x!==id):[...s,id]);
  const go=async()=>{setErr('');setBusy(true);try{const ch=await request('/chat/channels',{method:'POST',body:JSON.stringify({contact_ids:sel,group_id:grp||undefined,name:(sel.length+(grp?2:0))>1?name:''})});if(ch.skipped?.length)setErr('');onOpen(ch.id)}catch(x:any){setErr(x.message)}finally{setBusy(false)}};
  return <Modal title="New chat" onClose={onClose}><div className="ws-form">
    <label>Search contacts<input value={q} onChange={e=>setQ(e.target.value)} placeholder="Type a name or email" autoFocus/></label>
    {!!data.groups.length&&<label>Or a contact group<select value={grp} onChange={e=>setGrp(e.target.value)}><option value="">None</option>{data.groups.map((g:any)=><option key={g.id} value={g.id}>{g.name}</option>)}</select></label>}
    <div className="nc-list" role="listbox" aria-label="Contacts">{people.length?people.map((c:any)=><label key={c.id} className={sel.includes(c.id)?'on':''}><input type="checkbox" checked={sel.includes(c.id)} onChange={()=>tog(c.id)}/><span className="avatar sm">{c.name[0]?.toUpperCase()}</span><span><b>{c.name}</b><small className="muted"> {c.email}</small></span></label>):<p className="muted pad">No contacts found. Add some in Commbox, Contacts tab.</p>}</div>
    {(sel.length+(grp?2:0))>1&&<label>Group name (optional)<input value={name} onChange={e=>setName(e.target.value)} maxLength={80}/></label>}
    <p className="muted small">Only people who have an iSift account can be chatted with. {sel.length?`${sel.length} selected.`:''}</p>
    {err&&<p className="syncerr" role="alert">{err}</p>}
    <div className="actions"><button className="primary" disabled={busy||(!sel.length&&!grp)} onClick={go}>Start chat</button><button className="secondary" onClick={onClose}>Cancel</button></div>
  </div></Modal>;
}

export function ChatPage({request,initial}:{request:any;initial?:string}){
  const [chs,setChs]=useState<any[]>([]);const [cur,setCur]=useState(initial||'');const [msgs,setMsgs]=useState<any[]>([]);const [text,setText]=useState('');const [err,setErr]=useState('');const end=useRef<HTMLDivElement>(null);const [newOpen,setNewOpen]=useState(false);
  const loadCh=useCallback(()=>request('/chat/channels').then(setChs).catch(()=>{}),[request]);
  useEffect(()=>{loadCh();const t=setInterval(loadCh,6000);return()=>clearInterval(t)},[loadCh]);
  useEffect(()=>{if(initial)setCur(initial)},[initial]);
  useEffect(()=>{if(!cur){setMsgs([]);return}let on=true;const pull=()=>request(`/chat/channels/${cur}/messages`).then((m:any[])=>{if(on)setMsgs(p=>p.length===m.length&&p[p.length-1]?.id===m[m.length-1]?.id?p:m)}).catch(()=>{});setMsgs([]);pull();const t=setInterval(pull,2500);return()=>{on=false;clearInterval(t)}},[cur,request]);
  useEffect(()=>{end.current?.scrollIntoView({block:'end'})},[msgs.length]);
  const send=async(e:React.FormEvent)=>{e.preventDefault();const t=text.trim();if(!t||!cur)return;setText('');setErr('');try{await request(`/chat/channels/${cur}/messages`,{method:'POST',body:JSON.stringify({text:t})});const m=await request(`/chat/channels/${cur}/messages`);setMsgs(m);loadCh()}catch(x:any){setErr(x.message);setText(t)}};
  const ch=chs.find(c=>c.id===cur);
  const linkify=(t:string)=>t.split(/(https?:\/\/\S+)/g).map((p,i)=>/^https?:\/\//.test(p)?<a key={i} href={p} onClick={e=>{const h=p.includes('#/room/')&&p.startsWith(baseUrl());if(h){e.preventDefault();location.hash=p.slice(p.indexOf('#'))}}}>{p}</a>:p);
  return <div className="ws-chat"><aside className="panel ws-chlist" aria-label="Conversations"><div className="panelhead"><h2><MessageSquare size={18}/> Chat</h2><button className="primary" onClick={()=>setNewOpen(true)}><Plus size={15}/> New chat</button></div>
      {chs.length?chs.map(c=><button key={c.id} className={`ws-ch${c.id===cur?' on':''}`} onClick={()=>setCur(c.id)}><div className="avatar sm">{c.name[0]?.toUpperCase()}</div><div className="ws-main"><b>{c.name}</b><small className="muted">{c.last?`${c.last.sender.split(' ')[0]}: ${c.last.text}`:'No messages yet'}</small></div></button>):<p className="muted pad">No conversations yet. Press New chat and pick someone from your contacts.</p>}</aside>
    <section className="panel ws-conv">{ch?<><div className="panelhead"><div><h2>{ch.name}</h2><small className="muted">{ch.kind==='group'?`${ch.members.length} people`:'Direct message'}</small></div><button className="primary" onClick={()=>callChannel(request,ch.id).catch((e:any)=>setErr(e.message))}><Video size={15}/> Video call</button></div>
      <div className="ws-msgs" role="log" aria-live="polite">{msgs.map(m=><div key={m.id} className={`ws-msg${m.me?' me':''}`}><small>{m.me?'You':m.sender} · {new Date(m.at).toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'})}</small><p>{linkify(m.text)}</p></div>)}{!msgs.length&&<p className="muted pad">Say hello 👋</p>}<div ref={end}/></div>
      {err&&<p className="syncerr" role="alert">{err}</p>}
      <form className="ws-compose" onSubmit={send}><input value={text} onChange={e=>setText(e.target.value)} placeholder="Type a message" aria-label="Message" maxLength={4000}/><button className="primary" disabled={!text.trim()}><Send size={15}/> Send</button></form></>
      :<p className="muted pad">Choose a conversation on the left, or press New chat.</p>}</section>{newOpen&&<NewChat request={request} onClose={()=>setNewOpen(false)} onOpen={(id:string)=>{setNewOpen(false);setCur(id);loadCh()}}/>}</div>;
}

/* ---------------- Notes and Whiteboards ---------------- */
type Meta={name:string;icon:any;fresh:string;noun:string};
export const FILE_KINDS:Record<string,Meta>={doc:{name:'Notes',icon:FileText,fresh:'Untitled note',noun:'note'},board:{name:'Whiteboards',icon:PenLine,fresh:'Untitled board',noun:'whiteboard'},wp:{name:'WordPerfect',icon:FileText,fresh:'Untitled document',noun:'document'},sheet:{name:'SpreadTable',icon:Table2,fresh:'Untitled workbook',noun:'workbook'},deck:{name:'PowerPresentation',icon:Presentation,fresh:'Untitled presentation',noun:'presentation'}};
const SCOPES=[['mine','My files'],['with','Shared with me'],['by','Shared by me']] as const;
const accessWord=(a:string)=>({viewer:'Viewer',commenter:'Commenter',editor:'Editor',owner:'Owner'} as any)[a]||a;
const shortDate=(s?:string|null)=>s?new Date(s).toLocaleDateString(undefined,{day:'numeric',month:'short'}):'';
export function NotesPage({request,kind,focus,onFocused}:{request:any;kind:'doc'|'board'|'wp'|'sheet'|'deck';focus?:{id:string}|null;onFocused?:()=>void}){
  const meta=FILE_KINDS[kind];const Icon=meta.icon;
  const [scope,setScope]=useState<'mine'|'with'|'by'>('mine');const [list,setList]=useState<any[]>([]);const [open,setOpen]=useState<any>(null);const [title,setTitle]=useState('');const [content,setContent]=useState('');const [state,setState]=useState('');
  const timer=useRef<any>(null);const openId=useRef('');const pend=useRef<any>({});const base=useRef('');const saving=useRef(false);const [sharing,setSharing]=useState(false);const [host,setHost]=useState<HTMLElement|null>(null);const [paneOff,setPaneOff]=useState(()=>{try{return localStorage.getItem('isift.pane.'+kind)==='1'}catch{return false}});const flipPane=()=>setPaneOff(v=>{try{localStorage.setItem('isift.pane.'+kind,v?'0':'1')}catch{}return !v});const pic=useRef<(()=>string|null)|null>(null);const shapeApi=useRef<any>(null);const [want,setWant]=useState('');const [shelf,setShelf]=useState(()=>{try{const v=localStorage.getItem('isift.shelf.'+kind);return v===null?kind==='board':v==='1'}catch{return kind==='board'}});const flipShelf=()=>setShelf(v=>{try{localStorage.setItem('isift.shelf.'+kind,v?'0':'1')}catch{}return !v});
  const url=(s:string)=>s==='mine'?`/notes?kind=${kind}`:s==='with'?`/shared/with-me?kind=${kind}`:`/shared/by-me?kind=${kind}`;
  const loadList=useCallback((s=scope)=>request(url(s)).then(setList).catch(()=>setList([])),[request,kind,scope]);
  const access:string=open?.access||'owner';const level=({viewer:1,commenter:2,editor:3,owner:4} as any)[access]||1;const ro=level<3;
  const flush=useCallback(async()=>{clearTimeout(timer.current);if(saving.current||!Object.keys(pend.current).length||!openId.current)return;const id=openId.current,patch=pend.current;pend.current={};saving.current=true;
    try{const r=await request(`/notes/${id}`,{method:'PUT',body:JSON.stringify({...patch,base:base.current})});if(id===openId.current)base.current=r.updated_at;setState('Saved')}
    catch(e:any){if(/saved changes to this file/i.test(e.message||''))setState('conflict');else{pend.current={...patch,...pend.current};setState('Not saved: '+e.message)}}
    saving.current=false;if(Object.keys(pend.current).length&&state!=='conflict')timer.current=setTimeout(flush,300)},[request]);
  const queue=(patch:any)=>{if(ro)return;setState('Saving…');pend.current={...pend.current,...patch};clearTimeout(timer.current);timer.current=setTimeout(flush,700)};
  useEffect(()=>{setOpen(null);openId.current='';pend.current={};setScope('mine');setState('');request(url('mine')).then(setList).catch(()=>setList([]));return()=>{flush()}},[kind]);
  useEffect(()=>{loadList(scope)},[scope]);
  const pick=async(id:string)=>{await flush();pend.current={};const n=await request(`/notes/${id}`);openId.current=id;base.current=n.updated_at;setOpen(n);setTitle(n.title);setContent(n.content||'');setState('')};
  useEffect(()=>{if(!focus)return;(async()=>{try{await pick(focus.id)}catch{}onFocused?.()})()},[focus?.id]);
  const create=async()=>{const n=await request('/notes',{method:'POST',body:JSON.stringify({kind,title:meta.fresh,content:''})});setScope('mine');await request(url('mine')).then(setList);pick(n.id)};
  const remove=async()=>{if(!open||!window.confirm(`Delete "${title}"? Everyone it is shared with loses access.`))return;await request(`/notes/${open.id}`,{method:'DELETE'});setOpen(null);openId.current='';pend.current={};loadList()};
  const reload=async()=>{if(open){pend.current={};setState('');await pick(open.id)}};
  const row=(n:any)=>scope==='mine'?<small className="muted">Edited {new Date(n.updated_at).toLocaleString(undefined,{day:'numeric',month:'short',hour:'numeric',minute:'2-digit'})}</small>
    :scope==='with'?<small className="muted">From {n.owner} · {accessWord(n.access)} · shared {shortDate(n.shared_at)} · edited {shortDate(n.updated_at)}{n.expires_at?` · ends ${shortDate(n.expires_at)}`:''}{n.via==='group'?' · via a group':n.via==='link'?' · via a link':''}</small>
    :<small className="muted">With {n.recipients.length?n.recipients.join(', '):'no one by name'}{n.links?.length?` · ${n.links.length} ${n.links.length===1?'link':'links'}${n.links.some((l:any)=>l.expires_at)?' (expiring)':''}`:''} · shared {shortDate(n.shared_at)} · edited {shortDate(n.updated_at)}</small>;
  const empty=scope==='mine'?'Nothing here yet. Press New.':scope==='with'?'Nothing has been shared with you yet.':'You have not shared anything yet.';
  const label=`Open ${meta.noun}`;
  return <><div className={`ws-two notes${kind==='board'?' boards':''}${paneOff?' pane-off':''}`}><section className="panel ws-pane" aria-hidden={paneOff}><div className="panelhead"><h2><Icon size={18}/> {meta.name}</h2><span className="ws-pane-btns"><button className="primary" onClick={create}><Plus size={15}/> New</button><button type="button" className="iconbtn" aria-label="Hide this panel" title="Hide this panel to give the work area more room" onClick={flipPane}><ChevronsLeft size={18}/></button></span></div>
      <div className="notes-scope" role="tablist" aria-label="Which files">{SCOPES.map(([v,l])=><button key={v} type="button" role="tab" aria-selected={scope===v} className={`wb-cat${scope===v?' on':''}`} onClick={()=>setScope(v)}>{l}</button>)}</div>
      {kind!=='doc'?<>{list.length?<label className="wb-pick">{label}<select value={want||(open?.id||'')} onChange={e=>{const v=e.target.value;if(v){setWant(v);pick(v).catch(()=>{}).finally(()=>setWant(''))}}} aria-label={label}><option value="">Choose…</option>{open&&!list.some(n=>n.id===open.id)&&<option value={open.id}>{title||open.title}</option>}{list.map(n=><option key={n.id} value={n.id}>{n.title} · {scope==='with'?`${n.owner}, ${accessWord(n.access)}`:shortDate(n.updated_at)}</option>)}</select></label>:<p className="muted pad">{empty}</p>}</>
      :list.length?list.map(n=><button key={n.id} className={`ws-ch shared-row${open?.id===n.id?' on':''}`} onClick={()=>pick(n.id)}><div className="ws-main"><b>{n.title}</b>{row(n)}</div></button>):<p className="muted pad">{empty}</p>}
      <small className="muted pad">{scope==='mine'?'Private to you until you share it. Changes save automatically.':scope==='with'?'Open a file to use it with the access you were given.':'Open a file, then press Share to see or change who has access.'}</small></section>
    <section className="panel ws-editor">{paneOff&&<button type="button" className="textbtn ws-pane-open" aria-label="Show the files panel" onClick={flipPane}><ChevronsRight size={16}/> Show {meta.name} panel</button>}{open?<><div className="panelhead"><input className="ws-title" value={title} aria-label="Title" readOnly={ro} onChange={e=>{setTitle(e.target.value);queue({title:e.target.value})}}/><span className="muted small" role="status">{state==='Saved'?<><Check size={13}/> Saved</>:state==='conflict'?'':state}</span>
        {level===4&&<button className="iconbtn" aria-label="Share" title="Share" onClick={()=>{flush();setSharing(true)}}><Share2 size={16}/></button>}{level===4&&<button className="iconbtn" aria-label="Delete" onClick={remove}><Trash2 size={16}/></button>}</div>
      <SharedBanner access={access} owner={open.owner} kind={kind}/>
      {state==='conflict'&&<div className="error shared-banner" role="alert">Someone else saved changes to this file after you opened it, so your latest edits were not saved. <button className="textbtn" onClick={reload}>Reload their version</button></div>}
      <div className="ws-subbar">{(kind==='board'||kind==='wp'||kind==='deck')&&!ro&&<button type="button" className="textbtn ws-shapes" aria-expanded={shelf} onClick={flipShelf} title={shelf?'Hide the shape library':'Show the shape library'}>{shelf?<ChevronsLeft size={16}/>:<ChevronsRight size={16}/>} {shelf?'Hide shapes':'Show shapes'}</button>}<CommentsPanel key={'c:'+open.id} request={request} note={open.id} canWrite={level>=2}/>{kind==='board'&&<div className="wb-side wb2 wb-top" ref={setHost}/>}</div>
      {(kind==='wp'||kind==='deck')&&shelf&&!ro&&<ShapeShelf onPick={lib=>shapeApi.current?.insertShape(lib)}/>}
      {kind==='doc'?<textarea className="ws-doc" value={content} aria-label="Note text" placeholder={ro?'':'Start typing…'} readOnly={ro} onChange={e=>{setContent(e.target.value);queue({content:e.target.value})}}/>
      :kind==='board'?<Board key={'b:'+open.id} name={title} pictureRef={pic} toolsHost={host} readOnly={ro} libOpen={shelf} content={content} onChange={c=>{setContent(c);queue({content:c})}}/>
      :kind==='wp'?<WordEditor ref={shapeApi} shelf={shelf} onShelf={flipShelf} key={open.id+':'+base.current} title={title} content={content} readOnly={ro} onChange={c=>{setContent(c);queue({content:c})}}/>
      :kind==='sheet'?<SheetEditor key={open.id+':'+base.current} title={title} content={content} readOnly={ro} onChange={c=>{setContent(c);queue({content:c})}}/>
      :<DeckEditor ref={shapeApi} shelf={shelf} onShelf={flipShelf} key={open.id+':'+base.current} title={title} content={content} readOnly={ro} onChange={c=>{setContent(c);queue({content:c})}}/>}</>:<p className="muted pad">Choose or create {kind==='doc'||kind==='wp'?'a '+meta.noun:'a '+meta.noun}.</p>}</section></div>
    {sharing&&open&&level===4&&<ShareDialog request={request} note={open.id} kind={kind} title={title} content={content} picture={()=>pic.current?pic.current():null} onClose={()=>setSharing(false)}/>}</>;
}
