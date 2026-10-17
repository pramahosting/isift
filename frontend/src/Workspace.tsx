import React,{useCallback,useEffect,useRef,useState} from 'react';
import {Board} from './Whiteboard';
import {Mail,LogIn,Upload,Video,MessageSquare,Users,Plus,Trash2,Send,Copy,Mic,MonitorUp,X,UserPlus,FileText,PenLine,Undo2,Eraser,Check,Share2} from 'lucide-react';

const baseUrl=()=>location.origin+location.pathname;
export const roomLink=(code:string)=>`${baseUrl()}#/room/${code}`;
const copyText=async(t:string)=>{try{await navigator.clipboard.writeText(t)}catch{window.prompt('Copy this:',t)}};

export function Modal({title,onClose,children,wide}:{title:string;onClose:()=>void;children:React.ReactNode;wide?:boolean}){
  useEffect(()=>{const h=(e:KeyboardEvent)=>e.key==='Escape'&&onClose();window.addEventListener('keydown',h);return()=>window.removeEventListener('keydown',h)},[]);
  return <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><section className={`modal ws-modal${wide?' wide':''}`} role="dialog" aria-label={title}><div className="panelhead"><h2>{title}</h2><button className="iconbtn" aria-label="Close" onClick={onClose}><X size={18}/></button></div>{children}</section></div>;
}

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
/** Draw note text onto A4-shaped pages (JPEG) for notes with letters the server's PDF font cannot show. */
function notePages(title:string,text:string):string[]{
  const W=1240,H=1754,M=110,fs=26,lh=38,out:string[]=[];let c:HTMLCanvasElement,g:CanvasRenderingContext2D,y=0;
  const fresh=()=>{c=document.createElement('canvas');c.width=W;c.height=H;g=c.getContext('2d')!;g.fillStyle='#fff';g.fillRect(0,0,W,H);g.fillStyle='#172033';y=M+10;out.push('')};
  const done=()=>{out[out.length-1]=c.toDataURL('image/jpeg',0.9)};
  fresh();g.font='bold 40px sans-serif';for(const l of wrapText(g,title||'Untitled',W-2*M)){g.fillText(l,M,y);y+=54}y+=18;g.font=`${fs}px sans-serif`;
  for(const raw of text.replace(/\r\n/g,'\n').split('\n')){for(const l of wrapText(g,raw,W-2*M)){if(y>H-M){done();fresh();g.font=`${fs}px sans-serif`}g.fillText(l,M,y);y+=lh}if(!raw)y+=lh}
  done();return out}
function wrapText(g:CanvasRenderingContext2D,line:string,w:number):string[]{
  if(!line)return[''];const words=line.split(/(\s+)/);const res:string[]=[];let cur='';
  for(const wd of words){let t=cur+wd;if(g.measureText(t).width>w&&cur.trim()){res.push(cur.trimEnd());cur=wd.trimStart()}else cur=t;
    while(g.measureText(cur).width>w&&cur.length>1){let k=cur.length-1;while(k>1&&g.measureText(cur.slice(0,k)).width>w)k--;res.push(cur.slice(0,k));cur=cur.slice(k)}}
  res.push(cur.trimEnd());return res}

export function ShareDialog({request,note,kind,title,content,picture,onClose}:{request:any;note:string;kind:'doc'|'board';title:string;content:string;picture:()=>string|null;onClose:()=>void}){
  const [data,setData]=useState<any>({contacts:[],groups:[]});const [cids,setCids]=useState<string[]>([]);const [gids,setGids]=useState<string[]>([]);
  const [typed,setTyped]=useState('');const [msg,setMsg]=useState('');const [busy,setBusy]=useState(false);const [err,setErr]=useState('');const [done,setDone]=useState<any>(null);
  useEffect(()=>{request('/contacts').then(setData).catch(()=>{})},[]);
  const tog=(a:string[],set:(x:string[])=>void,id:string)=>set(a.includes(id)?a.filter(x=>x!==id):[...a,id]);
  const send=async()=>{setErr('');const emails=typed.split(/[\s,;]+/).map(x=>x.trim()).filter(Boolean);
    if(!emails.length&&!cids.length&&!gids.length){setErr('Choose a group, a contact, or type an email address.');return}
    setBusy(true);
    try{
      await request(`/notes/${note}`,{method:'PUT',body:JSON.stringify({title,content})});            // so the PDF matches what is on screen
      const body:any={emails,contact_ids:cids,group_ids:gids,message:msg};
      if(kind==='board'){const pic=picture();if(!pic){setErr('The whiteboard is empty. Draw something first.');setBusy(false);return}body.pages=[pic]}
      let r=await request(`/notes/${note}/share`,{method:'POST',body:JSON.stringify(body)});
      if(r.needs_pictures){body.pages=notePages(title,content);r=await request(`/notes/${note}/share`,{method:'POST',body:JSON.stringify(body)})}
      setDone(r)}catch(e:any){setErr(e.message||'Could not send.')}
    setBusy(false)};
  return <Modal title={`Share ${kind==='doc'?'note':'whiteboard'} as PDF`} onClose={onClose}>
    {done?<><p role="status"><Check size={15}/> Sent to {done.sent.length} {done.sent.length===1?'person':'people'} as <b>{done.file}</b>.</p>
      {done.failed?.length>0&&<p className="error">Could not reach: {done.failed.join(', ')}</p>}
      <div className="modal-actions"><button className="primary" onClick={onClose}>Done</button></div></>
    :<>
      <p className="muted small">“{title||'Untitled'}” will be emailed as a PDF. Each person gets their own message.</p>
      {data.groups.length>0&&<><b className="small">Groups</b><div className="share-pick">{data.groups.map((g:any)=><label key={g.id} className="check"><input type="checkbox" checked={gids.includes(g.id)} onChange={()=>tog(gids,setGids,g.id)}/> {g.name} <small className="muted">({g.contact_ids.length})</small></label>)}</div></>}
      {data.contacts.length>0&&<><b className="small">Contacts and participants</b><div className="share-pick">{data.contacts.filter((c:any)=>c.email).map((c:any)=><label key={c.id} className="check"><input type="checkbox" checked={cids.includes(c.id)} onChange={()=>tog(cids,setCids,c.id)}/> {c.name} <small className="muted">{c.email}</small></label>)}</div></>}
      <label>Other email addresses<input value={typed} onChange={e=>setTyped(e.target.value)} placeholder="name@example.com, another@example.com" aria-label="Other email addresses"/></label>
      <label>Message (optional)<textarea rows={2} value={msg} onChange={e=>setMsg(e.target.value)} aria-label="Message"/></label>
      {err&&<p className="error" role="alert">{err}</p>}
      <div className="modal-actions"><button className="secondary" onClick={onClose}>Cancel</button><button className="primary" disabled={busy} onClick={send}><Send size={15}/> {busy?'Sending…':'Send PDF'}</button></div></>}
  </Modal>}

export function NotesPage({request,kind}:{request:any;kind:'doc'|'board'}){
  const [list,setList]=useState<any[]>([]);const [open,setOpen]=useState<any>(null);const [title,setTitle]=useState('');const [content,setContent]=useState('');const [state,setState]=useState('');const timer=useRef<any>(null);const openId=useRef('');const [sharing,setSharing]=useState(false);const pic=useRef<(()=>string|null)|null>(null);
  const loadList=useCallback(()=>request(`/notes?kind=${kind}`).then(setList).catch(()=>{}),[request,kind]);
  useEffect(()=>{setOpen(null);openId.current='';loadList()},[kind]);
  const pick=async(id:string)=>{clearTimeout(timer.current);const n=await request(`/notes/${id}`);openId.current=id;setOpen(n);setTitle(n.title);setContent(n.content);setState('')};
  const create=async()=>{const n=await request('/notes',{method:'POST',body:JSON.stringify({kind,title:kind==='doc'?'Untitled note':'Untitled board',content:''})});await loadList();pick(n.id)};
  const queue=(patch:any)=>{setState('Saving…');clearTimeout(timer.current);const id=openId.current;timer.current=setTimeout(async()=>{try{await request(`/notes/${id}`,{method:'PUT',body:JSON.stringify(patch)});setState('Saved');loadList()}catch(e:any){setState('Not saved: '+e.message)}},700)};
  const remove=async()=>{if(!open||!window.confirm(`Delete "${title}"?`))return;await request(`/notes/${open.id}`,{method:'DELETE'});setOpen(null);openId.current='';loadList()};
  const Icon=kind==='doc'?FileText:PenLine;
  return <><div className="ws-two notes"><section className="panel"><div className="panelhead"><h2><Icon size={18}/> {kind==='doc'?'Notes':'Whiteboards'}</h2><button className="primary" onClick={create}><Plus size={15}/> New</button></div>
      {list.length?list.map(n=><button key={n.id} className={`ws-ch${open?.id===n.id?' on':''}`} onClick={()=>pick(n.id)}><div className="ws-main"><b>{n.title}</b><small className="muted">Edited {new Date(n.updated_at).toLocaleString(undefined,{day:'numeric',month:'short',hour:'numeric',minute:'2-digit'})}</small></div></button>):<p className="muted pad">Nothing here yet. Press New.</p>}
      <small className="muted pad">Private to you. Changes save automatically.</small></section>
    <section className="panel ws-editor">{open?<><div className="panelhead"><input className="ws-title" value={title} aria-label="Title" onChange={e=>{setTitle(e.target.value);queue({title:e.target.value})}}/><span className="muted small" role="status">{state==='Saved'?<><Check size={13}/> Saved</>:state}</span><button className="iconbtn" aria-label="Share as PDF by email" title="Share as PDF by email" onClick={()=>setSharing(true)}><Share2 size={16}/></button><button className="iconbtn" aria-label="Delete" onClick={remove}><Trash2 size={16}/></button></div>
      {kind==='doc'?<textarea className="ws-doc" value={content} aria-label="Note text" placeholder="Start typing…" onChange={e=>{setContent(e.target.value);queue({content:e.target.value})}}/>:<Board key={open.id} name={title} pictureRef={pic} content={content} onChange={c=>{setContent(c);queue({content:c})}}/>}</>:<p className="muted pad">Choose or create {kind==='doc'?'a note':'a whiteboard'}.</p>}</section></div>{sharing&&open&&<ShareDialog request={request} note={open.id} kind={kind} title={title} content={content} picture={()=>pic.current?pic.current():null} onClose={()=>setSharing(false)}/>}</>;
}
