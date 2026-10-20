import React,{useCallback,useEffect,useMemo,useState} from 'react';
import {Mail,CalendarDays,Users,Inbox,Send,FileText,Trash2,Archive,ShieldAlert,Folder,ChevronRight,ChevronDown,Plus,PenSquare,RefreshCw,Reply,ReplyAll,Forward,MailOpen,Search,Paperclip,Star,LogIn,X,UserPlus,Pencil} from 'lucide-react';
import {Modal} from './Workspace';
import {outlookSignIn,outlookError} from './Connections';

const ROLE_ICON:any={inbox:Inbox,sent:Send,drafts:FileText,trash:Trash2,junk:ShieldAlert,archive:Archive};
const ROLE_LABEL:any={inbox:'Inbox',sent:'Sent Items',drafts:'Drafts',trash:'Deleted Items',junk:'Junk Email',archive:'Archive'};
const fname=(f:any)=>ROLE_LABEL[f.role]||f.name.split('/').pop();
const when=(iso?:string|null)=>{if(!iso)return '';const d=new Date(iso),n=new Date();if(d.toDateString()===n.toDateString())return d.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});if(d.getFullYear()===n.getFullYear())return d.toLocaleDateString([],{month:'short',day:'numeric'});return d.toLocaleDateString()};
const rk=(r:any)=>`${r.aid}:${r.uid}`;
const initial=(s:string)=>(s.replace(/["<]/g,'').trim()[0]||'?').toUpperCase();
const hue=(s:string)=>{let h=0;for(const c of s)h=(h*31+c.charCodeAt(0))%360;return `hsl(${h} 45% 42%)`};

export function MailApp({request,isAdmin,goSettings,onPulled,go}:{request:any;isAdmin:boolean;goSettings:()=>void;onPulled:()=>void;go:(p:string)=>void}){
  const [accts,setAccts]=useState<any[]>([]);const [presets,setPresets]=useState<any>({});const [loaded,setLoaded]=useState(false);
  const [ms,setMs]=useState<any>(null);                                   // Microsoft mail pulled through the sign-in popup
  const [open,setOpen]=useState<Record<string,boolean>>({});const [fold,setFold]=useState<Record<string,any[]>>({});
  const [cur,setCur]=useState<{aid:string;folder:string}|null>(null);
  const [rows,setRows]=useState<any[]>([]);const [more,setMore]=useState(false);const [q,setQ]=useState('');const [busy,setBusy]=useState(false);const [err,setErr]=useState('');const [note,setNote]=useState('');
  const [sel,setSel]=useState<string[]>([]);const [msg,setMsg]=useState<any>(null);const [favOpen,setFavOpen]=useState(true);
  const pending=React.useRef('');const picked=React.useRef(false);const [compose,setCompose]=useState<any>(null);const [adding,setAdding]=useState(false);const [editing,setEditing]=useState<any>(null);const [tab,setTab]=useState<'Home'|'View'>('Home');const [pane,setPane]=useState(true);

  const loadAccts=useCallback(async()=>{try{const [a,m]=await Promise.all([request('/mailbox/accounts'),request('/connections/microsoft/mail').catch(()=>null)]);setAccts(a.accounts);setPresets(a.presets);setMs(m&&m.connected?m:null)}catch(e:any){setErr(e.message)}finally{setLoaded(true)}},[request]);
  useEffect(()=>{loadAccts()},[loadAccts]);
  const loadFolders=useCallback(async(aid:string)=>{try{const r=await request(`/mailbox/accounts/${aid}/folders`);setFold(f=>({...f,[aid]:r.folders}));return r.folders}catch(e:any){setErr(e.message);setFold(f=>({...f,[aid]:[]}));return []}},[request]);
  const fetchRows=useCallback(async(c:{aid:string;folder:string},query:string,before=0)=>{
    setBusy(true);setErr('');
    const msRows=async()=>{const m=await request('/connections/microsoft/mail');return (m.mail||[]).map((x:any,i:number)=>({aid:'ms',acct:m.account||'Microsoft',uid:i+1,from:x.from,subject:x.subject,at:x.at,unread:!x.read,preview:x.preview||''})).filter((x:any)=>!query||(x.from+x.subject+x.preview).toLowerCase().includes(query.toLowerCase()))};
    try{
      if(c.aid==='ms'){setRows(await msRows());setMore(false);return}
      if(c.aid==='all'){                                   // one list for every inbox, newest first
        const parts=await Promise.all([...accts.map(async a=>{try{const r=await request(`/mailbox/accounts/${a.id}/messages?folder=INBOX&q=${encodeURIComponent(query)}`);return r.messages.map((x:any)=>({...x,aid:a.id,acct:a.address}))}catch{return []}}),ms?msRows().catch(()=>[]):Promise.resolve([])]);
        setRows(parts.flat().sort((a:any,b:any)=>+new Date(b.at||0)-+new Date(a.at||0)).slice(0,100));setMore(false);return}
      const r=await request(`/mailbox/accounts/${c.aid}/messages?folder=${encodeURIComponent(c.folder)}&q=${encodeURIComponent(query)}${before?`&before=${before}`:''}`);
      const list=r.messages.map((x:any)=>({...x,aid:c.aid}));
      setRows(prev=>before?[...prev,...list]:list);setMore(r.more);
    }catch(e:any){setErr(e.message);if(!before)setRows([])}finally{setBusy(false)}
  },[request,accts,ms]);
  const removeAcct=async(a:any)=>{if(!window.confirm(`Remove ${a.address} from iSift? Your mailbox itself is not touched.`))return;try{await request(`/mailbox/accounts/${a.id}`,{method:'DELETE'});if(cur?.aid===a.id||cur?.aid==='all'){setCur(null);setRows([]);setMsg(null)}await loadAccts();setNote(`${a.address} removed.`)}catch(e:any){setErr(e.message)}};
  const pick=(aid:string,folder:string)=>{picked.current=true;const c={aid,folder};setCur(c);setSel([]);setMsg(null);setQ('');setNote(pending.current);pending.current='';fetchRows(c,'')};
  const toggleAcct=async(aid:string)=>{const o=!open[aid];setOpen(s=>({...s,[aid]:o}));if(o&&!fold[aid])await loadFolders(aid)};
  // first account opens by itself
  useEffect(()=>{if(!loaded||cur)return;if(accts.length){const a=accts[0];setOpen(s=>({...s,[a.id]:true}));accts.forEach(x=>{if(x.id!==a.id)loadFolders(x.id)});loadFolders(a.id).then(()=>{if(!picked.current)pick(accts.length>1?'all':a.id,'INBOX')})}else if(ms)pick('ms','INBOX')},[loaded,accts,ms]);// eslint-disable-line
  const acct=(id:string)=>accts.find(a=>a.id===id);
  const readOnly=cur?.aid==='ms'||(sel.length>0&&sel.every(k=>k.startsWith('ms:')));
  const search=(e:React.FormEvent)=>{e.preventDefault();if(cur){setSel([]);fetchRows(cur,q)}};
  const openMsg=async(r:any)=>{
    setSel([rk(r)]);const folder=cur?.aid==='all'?'INBOX':cur!.folder;
    if(r.aid==='ms'){setMsg({aid:'ms',uid:r.uid,from:r.from,to:'',cc:'',subject:r.subject,at:r.at,text:r.preview||'',attachments:[],readonly:true});return}
    setMsg({aid:r.aid,uid:r.uid,loading:true,subject:r.subject,from:r.from,at:r.at});
    try{const m=await request(`/mailbox/accounts/${r.aid}/message?folder=${encodeURIComponent(folder)}&uid=${r.uid}`);setMsg({...m,aid:r.aid,folder});setRows(rs=>rs.map(x=>rk(x)===rk(r)?{...x,unread:false}:x));loadFolders(r.aid)}catch(e:any){setErr(e.message);setMsg(null)}
  };
  const act=async(action:string,target='')=>{
    if(!cur||!sel.length||readOnly)return;setErr('');setBusy(true);
    const folder=cur.aid==='all'?'INBOX':cur.folder;
    try{
      const by:Record<string,number[]>={};sel.forEach(k=>{const [aid,uid]=[k.slice(0,k.lastIndexOf(':')),Number(k.slice(k.lastIndexOf(':')+1))];if(aid!=='ms')(by[aid]=by[aid]||[]).push(uid)});
      for(const aid of Object.keys(by))await request(`/mailbox/accounts/${aid}/action`,{method:'POST',body:JSON.stringify({folder,uids:by[aid],action,target})});
      const mine=new Set(sel);
      if(['delete','archive','junk','move'].includes(action)){setRows(rs=>rs.filter(r=>!mine.has(rk(r))));if(msg&&mine.has(`${msg.aid}:${msg.uid}`))setMsg(null);setSel([])}
      else setRows(rs=>rs.map(r=>mine.has(rk(r))?{...r,unread:action==='unread',flagged:action==='flag'?true:action==='unflag'?false:r.flagged}:r));
      Object.keys(by).forEach(a=>loadFolders(a))}catch(e:any){setErr(e.message)}finally{setBusy(false)}
  };
  const refresh=async()=>{if(!cur)return;const list=cur.aid==='all'?accts:[acct(cur.aid)].filter(Boolean);for(const a of list as any[]){if(a.people){try{const r=await request(`/oauth/accounts/${a.id}/sync`,{method:'POST'});setNote(r.message);onPulled()}catch{}}loadFolders(a.id)}fetchRows(cur,q)};
  const reply=(all:boolean,fwd=false)=>{if(!msg||!msg.aid||msg.aid==='ms')return;const own=acct(msg.aid)?.address||'';const quoted=`\n\n— On ${msg.at?new Date(msg.at).toLocaleString():''}, ${msg.from} wrote:\n`+(msg.text||'').split('\n').map((l:string)=>'> '+l).join('\n');
    const strip=(s:string)=>(s||'').split(',').map(x=>x.trim()).filter(x=>x&&!x.toLowerCase().includes(own.toLowerCase())).join(', ');
    setCompose({aid:msg.aid,to:fwd?'':msg.reply_to||msg.from,cc:all?strip(`${msg.to||''}, ${msg.cc||''}`):'',subject:(fwd?'Fw: ':'Re: ')+String(msg.subject).replace(/^(re|fw|fwd):\s*/i,''),body:quoted,irt:fwd?'':msg.message_id||''})};
  const selRow=rows.find(r=>rk(r)===sel[0]);
  const favs=useMemo(()=>accts.map(a=>({a,unread:(fold[a.id]||[]).find((f:any)=>f.role==='inbox')?.unread})),[accts,fold]);
  const curAcct=cur?(cur.aid==='ms'?{address:ms?.account||'Microsoft 365'}:cur.aid==='all'?{address:`${accts.length+(ms?1:0)} accounts`}:acct(cur.aid)):null;
  const allUnread=accts.reduce((n,a)=>n+((fold[a.id]||[]).find((f:any)=>f.role==='inbox')?.unread||0),0);
  const moveTargets=cur&&cur.aid!=='all'&&fold[cur.aid]?fold[cur.aid].filter((f:any)=>f.name!==cur.folder):[];

  return <div className={`ol${pane?'':' nopane'}`}>
    <nav className="ol-rail" aria-label="Apps">
      <button className="on" title="Mail" aria-label="Mail"><Mail size={20}/></button>
      <button title="Calendar" aria-label="Calendar" onClick={()=>go('Calendar')}><CalendarDays size={20}/></button>
      <button title="People" aria-label="People" onClick={()=>go('Contacts')}><Users size={20}/></button>
    </nav>
    <div className="ol-main">
      <div className="ol-tabs" role="tablist">{(['Home','View'] as const).map(t=><button key={t} role="tab" aria-selected={tab===t} className={tab===t?'on':''} onClick={()=>setTab(t)}>{t}</button>)}</div>
      <div className="ol-ribbon" role="toolbar" aria-label="Mail actions">
        {tab==='Home'?<>
          <button className="ol-new" onClick={()=>setCompose({aid:cur&&cur.aid!=='ms'?cur.aid:accts[0]?.id,to:'',cc:'',subject:'',body:'',irt:''})} disabled={!accts.length}><PenSquare size={16}/> New mail</button>
          <span className="sep"/>
          <button disabled={!sel.length||readOnly||busy} onClick={()=>act('delete')} title="Delete"><Trash2 size={16}/> <span>Delete</span></button>
          <button disabled={!sel.length||readOnly||busy} onClick={()=>act('archive')} title="Archive"><Archive size={16}/> <span>Archive</span></button>
          <button disabled={!sel.length||readOnly||busy} onClick={()=>act('junk')} title="Report as junk"><ShieldAlert size={16}/> <span>Junk</span></button>
          <select aria-label="Move to" disabled={!sel.length||readOnly||busy} value="" onChange={e=>{if(e.target.value)act('move',e.target.value)}}><option value="">Move to…</option>{moveTargets.map((f:any)=><option key={f.name} value={f.name}>{fname(f)}</option>)}</select>
          <span className="sep"/>
          <button disabled={!sel.length||readOnly||busy} onClick={()=>act(selRow&&selRow.unread?'read':'unread')} title="Mark read or unread"><MailOpen size={16}/> <span>{selRow&&selRow.unread?'Mark as read':'Mark as unread'}</span></button>
          <button disabled={!sel.length||readOnly||busy} onClick={()=>act(selRow?.flagged?'unflag':'flag')} title="Flag"><Star size={16}/> <span>Flag</span></button>
          <span className="sep"/>
          <button disabled={!msg||msg.loading||readOnly} onClick={()=>reply(false)}><Reply size={16}/> <span>Reply</span></button>
          <button disabled={!msg||msg.loading||readOnly} onClick={()=>reply(true)}><ReplyAll size={16}/> <span>Reply all</span></button>
          <button disabled={!msg||msg.loading||readOnly} onClick={()=>reply(false,true)}><Forward size={16}/> <span>Forward</span></button>
          <span className="grow"/>
          <button onClick={refresh} disabled={!cur||busy} title="Sync"><RefreshCw size={16}/> <span>Sync</span></button>
        </>:<>
          <label className="ol-check"><input type="checkbox" checked={pane} onChange={e=>setPane(e.target.checked)}/> Show reading pane</label>
        </>}
      </div>
      <div className="ol-body">
        <aside className="ol-folders" aria-label="Folders">
          <button className="ol-h" onClick={()=>setFavOpen(!favOpen)}>{favOpen?<ChevronDown size={14}/>:<ChevronRight size={14}/>} <b>Favorites</b></button>
          {favOpen&&<>{(accts.length+(ms?1:0))>1&&<button className={`ol-f${cur?.aid==='all'?' on':''}`} onClick={()=>pick('all','INBOX')}><Inbox size={15}/><span className="t">All inboxes <small>{accts.length+(ms?1:0)} accounts combined</small></span>{allUnread?<em>{allUnread}</em>:null}</button>}{favs.map(({a,unread})=><button key={'fav'+a.id} className={`ol-f${cur?.aid===a.id&&cur.folder==='INBOX'?' on':''}`} onClick={()=>{setOpen(s=>({...s,[a.id]:true}));if(!fold[a.id])loadFolders(a.id);pick(a.id,'INBOX')}}><Inbox size={15}/><span className="t">Inbox <small>{a.address}</small></span>{unread?<em>{unread}</em>:null}</button>)}
            {ms&&<button className={`ol-f${cur?.aid==='ms'?' on':''}`} onClick={()=>pick('ms','INBOX')}><Inbox size={15}/><span className="t">Inbox <small>{ms.account} (Microsoft)</small></span></button>}
            {!favs.length&&!ms&&<p className="muted small pad">Add an account to see your inbox.</p>}</>}
          {accts.map(a=><div key={a.id}>
            <div className="ol-acctrow"><button className="ol-h acct" onClick={()=>toggleAcct(a.id)} title={a.address}>{open[a.id]?<ChevronDown size={14}/>:<ChevronRight size={14}/>} <b>{a.address}</b></button>
            <button className="ol-rm" title={`Edit ${a.address}`} aria-label={`Edit ${a.address}`} onClick={()=>setEditing(a)}><Pencil size={14}/></button><button className="ol-rm" title={`Remove ${a.address}`} aria-label={`Remove ${a.address}`} onClick={()=>removeAcct(a)}><Trash2 size={14}/></button></div>
            {open[a.id]&&(fold[a.id]?fold[a.id].map((f:any)=>{const I=ROLE_ICON[f.role]||Folder;return <button key={f.name} className={`ol-f${cur?.aid===a.id&&cur.folder===f.name?' on':''}`} onClick={()=>pick(a.id,f.name)}><I size={15}/><span className="t">{fname(f)}</span>{f.unread?<em>{f.unread}</em>:null}</button>}):<p className="muted small pad">Loading…</p>)}
          </div>)}
          {ms&&<div><button className="ol-h acct" onClick={()=>pick('ms','INBOX')}><ChevronRight size={14}/> <b>{ms.account}</b></button></div>}
          <button className="ol-add" onClick={()=>setAdding(true)}><UserPlus size={16}/> Add account</button>
        </aside>
        <section className="ol-list" aria-label="Messages">
          <form className="ol-search" onSubmit={search}><Search size={15}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder={cur?`Search ${cur.aid==='all'?'all inboxes':cur.aid==='ms'?'Inbox':fname({role:'',name:cur.folder})}`:'Search'} aria-label="Search mail" disabled={!cur}/>{q&&<button type="button" className="x" aria-label="Clear search" onClick={()=>{setQ('');cur&&fetchRows(cur,'')}}><X size={14}/></button>}</form>
          {cur&&<div className="ol-lh"><b>{cur.aid==='all'?'All inboxes':cur.aid==='ms'?'Inbox':fname((fold[cur.aid]||[]).find((f:any)=>f.name===cur.folder)||{role:cur.folder==='INBOX'?'inbox':'',name:cur.folder})}</b><small>{curAcct?.address}</small></div>}
          {err&&<p className="syncerr" role="alert">{err}</p>}{note&&<p className="muted pad" role="status">{note}</p>}
          <div className="ol-rows" role="list">
            {rows.map(r=><div key={rk(r)} role="listitem" className={`ol-row${r.unread?' unread':''}${sel.includes(rk(r))?' sel':''}`} onClick={()=>openMsg(r)}>
              <input type="checkbox" aria-label={`Select ${r.subject}`} checked={sel.includes(rk(r))} onClick={e=>e.stopPropagation()} onChange={e=>setSel(s=>e.target.checked?[...s,rk(r)]:s.filter(x=>x!==rk(r)))}/>
              <span className="av" style={{background:hue(r.from||'?')}}>{initial(r.from||'?')}</span>
              <div className="mid"><div className="l1"><b className="who">{r.from||'Unknown'}</b><time>{when(r.at)}</time></div><div className="l2">{r.flagged&&<Star size={12} className="flag"/>}{r.subject}</div>{cur?.aid==='all'&&<div className="l4">{r.acct}</div>}<div className="l3">{r.preview}</div></div>
            </div>)}
            {!rows.length&&!busy&&cur&&!err&&<p className="muted pad">{q?'No messages match your search.':'Nothing in this folder.'}</p>}
            {busy&&<p className="muted pad">Loading…</p>}
            {more&&!busy&&<button className="secondary ol-more" onClick={()=>cur&&fetchRows(cur,q,rows[rows.length-1]?.uid)}>Load older messages</button>}
          </div>
          {loaded&&!accts.length&&!ms&&<div className="ol-empty"><Mail size={34}/><h3>Connect your mail</h3><p className="muted">Add Gmail, Yahoo, iCloud, Outlook.com or any IMAP account and read, reply, delete and archive from here.</p><button className="primary" onClick={()=>setAdding(true)}>Add account</button></div>}
        </section>
        {pane&&<section className="ol-read" aria-label="Reading pane">
          {!msg&&<div className="ol-empty"><Mail size={40}/><p className="muted">Select an item to read</p></div>}
          {msg&&<article>
            <h2>{msg.subject}</h2>
            {msg.loading?<p className="muted">Loading…</p>:<>
              <div className="ol-from"><span className="av lg" style={{background:hue(msg.from||'?')}}>{initial(msg.from||'?')}</span><div><b>{msg.from}</b><small className="muted">{msg.to?`To: ${msg.to}`:''}{msg.cc?` · Cc: ${msg.cc}`:''}</small></div><time>{msg.at?new Date(msg.at).toLocaleString():''}</time></div>
              {!msg.readonly&&<div className="ol-qa"><button className="secondary" onClick={()=>reply(false)}><Reply size={14}/> Reply</button><button className="secondary" onClick={()=>reply(true)}><ReplyAll size={14}/> Reply all</button><button className="secondary" onClick={()=>reply(false,true)}><Forward size={14}/> Forward</button></div>}
              {msg.attachments?.length>0&&<div className="ol-att">{msg.attachments.map((a:any,i:number)=><span key={i}><Paperclip size={13}/> {a.name} <small>{Math.max(1,Math.round(a.size/1024))} KB</small></span>)}</div>}
              <div className="ol-text">{msg.text||'(no text)'}</div>
              {msg.readonly&&<p className="muted small">Only the first lines of Microsoft mail are kept. Open Outlook to read the rest.</p>}
              {msg.attachments?.length>0&&<p className="muted small">Attachments are not downloaded here.</p>}
            </>}
          </article>}
        </section>}
      </div>
    </div>
    {compose&&<Compose accts={accts} init={compose} request={request} onClose={()=>setCompose(null)} onSent={m=>{setCompose(null);setNote(m);if(cur&&cur.aid===compose.aid)loadFolders(cur.aid)}}/>}
    {editing&&<AddAccount edit={editing} presets={presets} request={request} onClose={()=>setEditing(null)} onAdded={async(id,m)=>{setEditing(null);await loadAccts();setOpen(s=>({...s,[id]:true}));await loadFolders(id);pending.current=m||'';pick(id,'INBOX')}} onPulled={()=>{}}/>}
    {adding&&<AddAccount presets={presets} request={request} onClose={()=>setAdding(false)} onAdded={async(id,m)=>{setAdding(false);await loadAccts();setOpen(s=>({...s,[id]:true}));await loadFolders(id);pending.current=m||'';pick(id,'INBOX');onPulled()}} onPulled={async()=>{await loadAccts();onPulled();setAdding(false);pick('ms','INBOX')}}/>}
  </div>;
}

function Compose({accts,init,request,onClose,onSent}:{accts:any[];init:any;request:any;onClose:()=>void;onSent:(m:string)=>void}){
  const [f,setF]=useState({aid:init.aid||accts[0]?.id||'',to:init.to||'',cc:init.cc||'',subject:init.subject||'',body:init.body||''});const [cc,setCc]=useState(!!init.cc);const [err,setErr]=useState('');const [busy,setBusy]=useState(false);
  const send=async(e:React.FormEvent)=>{e.preventDefault();setErr('');setBusy(true);try{const r=await request(`/mailbox/accounts/${f.aid}/send`,{method:'POST',body:JSON.stringify({to:f.to,cc:f.cc,subject:f.subject,body:f.body,in_reply_to:init.irt||''})});onSent(r.message)}catch(x:any){setErr(x.message)}finally{setBusy(false)}};
  return <Modal title="New message" onClose={onClose} wide><form className="ws-form ol-compose" onSubmit={send}>
    <label>From<select value={f.aid} onChange={e=>setF({...f,aid:e.target.value})}>{accts.map(a=><option key={a.id} value={a.id}>{a.address}</option>)}</select></label>
    <label>To<input value={f.to} onChange={e=>setF({...f,to:e.target.value})} placeholder="name@example.com, another@example.com" autoFocus={!f.to}/>{!cc&&<button type="button" className="textbtn" onClick={()=>setCc(true)}>Cc</button>}</label>
    {cc&&<label>Cc<input value={f.cc} onChange={e=>setF({...f,cc:e.target.value})}/></label>}
    <label>Subject<input value={f.subject} onChange={e=>setF({...f,subject:e.target.value})}/></label>
    <textarea aria-label="Message" rows={12} value={f.body} onChange={e=>setF({...f,body:e.target.value})} autoFocus={!!f.to}/>
    {err&&<p className="syncerr" role="alert">{err}</p>}
    <div className="actions"><button className="primary" disabled={busy||!f.to.trim()}><Send size={15}/> {busy?'Sending…':'Send'}</button><button type="button" className="secondary" onClick={onClose}>Discard</button></div>
  </form></Modal>;
}

function AddAccount({presets,request,onClose,onAdded,onPulled,edit}:{edit?:any;presets:any;request:any;onClose:()=>void;onAdded:(id:string,message?:string)=>void;onPulled:()=>void}){
  // Same steps as Outlook: type your email address, press Continue, sign in in the window that opens.
  const E=edit?.settings||{};const [addr,setAddr]=useState(edit?.address||'');const [step,setStep]=useState<'email'|'which'|'password'|'unavailable'>(edit?'password':'email');const [which,setWhich]=useState('');
  const [prov,setProv]=useState(edit?.provider||'other');const [un,setUn]=useState(E.username||'');const [pw,setPw]=useState('');const [busy,setBusy]=useState(false);const [err,setErr]=useState('');
  const [sh,setSh]=useState(E.smtp_host||'');const [sp,setSp]=useState(String(E.smtp_port||587));const [ih,setIh]=useState(E.imap_host||'');const [ip,setIp]=useState(String(E.imap_port||993));
  const LABEL:any={google:'Google',microsoft:'Microsoft',yahoo:'Yahoo'};
  const signIn=async(id:string)=>{
    setErr('');setBusy(true);setWhich(id);
    try{
      const r=await request(`/oauth/${id}/start`,{method:'POST',body:JSON.stringify({origin:location.origin,email:addr})});
      const w=window.open(r.url,'isift-oauth','width=520,height=720,menubar=no,toolbar=no');
      if(!w){setErr('The sign-in window was blocked. Allow pop-ups for this page and try again.');return}
      await new Promise<void>(res=>{
        const done=()=>{window.removeEventListener('message',on);clearInterval(t);res()};
        const on=(e:MessageEvent)=>{if(e.origin!==location.origin||e.data?.type!=='isift-oauth')return;done();if(e.data.ok)onAdded(e.data.accountId,e.data.message);else setErr(e.data.message||'Sign-in did not finish.')};
        window.addEventListener('message',on);const t=setInterval(()=>{if(w.closed)done()},700);
      });
    }catch(x:any){if(/not set up/i.test(x.message||'')){setStep('unavailable')}else setErr(x.message)}finally{setBusy(false)}
  };
  const next=async(e:React.FormEvent)=>{e.preventDefault();setErr('');if(!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(addr.trim())){setErr('Enter your email address, for example name@gmail.com.');return}
    setBusy(true);let p:string|null=null;try{p=(await request(`/oauth/detect?email=${encodeURIComponent(addr.trim())}`)).provider}catch{}setBusy(false);
    if(p)signIn(p);else setStep('which')};
  const add=async(e:React.FormEvent)=>{e.preventDefault();setErr('');setBusy(true);try{const body=JSON.stringify({provider:prov,address:addr.trim(),username:un.trim()||undefined,password:pw,smtp_host:sh||undefined,smtp_port:sp,imap_host:ih||undefined,imap_port:ip});const r=await request(edit?`/mailbox/accounts/${edit.id}`:'/mailbox/accounts',{method:edit?'PATCH':'POST',body});onAdded(r.account.id,r.message)}catch(x:any){setErr(x.message)}finally{setBusy(false)}};
  const desktop=async()=>{setErr('');setBusy(true);try{await request('/connections/outlook-desktop/pull',{method:'POST'});onPulled()}catch(x:any){setErr(x.message)}finally{setBusy(false)}};
  const usePassword=(p:string)=>{setProv(p);setStep('password');setErr('')};
  return <Modal title={edit?"Edit account":"Add account"} onClose={onClose}><div className="ws-form ol-add-form">
    {step==='email'&&<form onSubmit={next}>
      <p className="muted">Enter your email address. A sign-in window opens, just like in Outlook. Gmail, Yahoo, Outlook, Hotmail, Microsoft 365 and Google Workspace accounts are supported.</p>
      <label>Email<input type="email" value={addr} onChange={e=>setAddr(e.target.value)} placeholder="name@example.com" autoComplete="email" autoFocus required/></label>
      {err&&<p className="syncerr" role="alert">{err}</p>}{busy&&<p className="muted small" role="status">Waiting for the sign-in window…</p>}
      <div className="actions"><button className="primary" disabled={busy||!addr.trim()}>Continue</button><button type="button" className="secondary" onClick={onClose}>Cancel</button></div>
      <hr/><p className="muted small">Outlook is installed on this Windows laptop?</p><div className="actions"><button type="button" className="secondary" disabled={busy} onClick={desktop}>Read Outlook on this computer</button></div>
    </form>}
    {step==='which'&&<div>
      <p className="muted">Which service looks after <b>{addr}</b>?</p>
      <div className="ol-prov">
        <button disabled={busy} onClick={()=>signIn('google')}><b>Google</b><small>Gmail or Google Workspace</small></button>
        <button disabled={busy} onClick={()=>signIn('microsoft')}><b>Microsoft</b><small>Outlook.com or Microsoft 365</small></button>
        <button disabled={busy} onClick={()=>signIn('yahoo')}><b>Yahoo</b><small>Yahoo Mail</small></button>
        <button disabled={busy} onClick={()=>usePassword('other')}><b>Something else</b><small>iCloud or another provider (IMAP and an app password)</small></button>
      </div>
      {err&&<p className="syncerr" role="alert">{err}</p>}
      <div className="actions"><button className="secondary" onClick={()=>{setStep('email');setErr('')}}>Back</button></div>
    </div>}
    {step==='unavailable'&&<div>
      <p><b>{LABEL[which]||'That'} sign-in is not set up in this installation of iSift yet.</b></p>
      <p className="muted">Whoever installs iSift needs to register it once with {LABEL[which]||'the provider'} and put the ID in the <code>.env</code> file. The steps are in the setup guide under “Adding mailboxes with a sign-in window”. Nothing is wrong with your account.</p>
      {which==='microsoft'
        ?<p className="muted small">Microsoft 365 and Outlook.com no longer accept app passwords for most accounts, so this one needs the sign-in window. In the meantime you can read Outlook on this laptop (Windows) from the Add account screen.</p>
        :<p className="muted small">Meanwhile you can add this account with an app password instead.</p>}
      <div className="actions">{which!=='microsoft'&&<button className="primary" onClick={()=>usePassword(which==='google'?'gmail':which==='yahoo'?'yahoo':'other')}>Use an app password</button>}<button className={which==='microsoft'?'primary':'secondary'} onClick={()=>{setStep('email');setErr('')}}>Back</button><button className="secondary" onClick={onClose}>Close</button></div>
    </div>}
    {step==='password'&&<form onSubmit={add} className="conn-form">
      <p className="muted small span2">Account: <b>{addr}</b></p>
      <label>Provider<select value={prov} onChange={e=>setProv(e.target.value)}>{Object.entries(presets).map(([k,v]:any)=><option key={k} value={k}>{v.label}</option>)}</select></label>
      <label>App password<input type="password" value={pw} onChange={e=>setPw(e.target.value)} autoComplete="new-password" required={!edit} placeholder={edit?"Leave blank to keep the saved password":""} autoFocus/></label>{prov==='other'&&<label>Username <small>(blank = full address)</small><input value={un} onChange={e=>setUn(e.target.value)} placeholder={addr}/></label>}
      {prov==='other'&&<><label>Sending server (SMTP)<input value={sh} onChange={e=>setSh(e.target.value)} required/></label><label>Port<input value={sp} onChange={e=>setSp(e.target.value)}/></label><label>Reading server (IMAP)<input value={ih} onChange={e=>setIh(e.target.value)} required/></label><label>Port<input value={ip} onChange={e=>setIp(e.target.value)}/></label></>}
      {presets[prov]?.how&&<p className="muted small span2"><b>Where to get the app password:</b> {presets[prov].how}</p>}
      {err&&<p className="syncerr span2" role="alert">{err}</p>}
      <div className="actions span2"><button className="primary" disabled={busy||(!edit&&!pw)}>{edit?'Save changes':<><Plus size={15}/> Add account</>}</button><button type="button" className="secondary" onClick={()=>{if(edit){onClose();return}setStep('email');setErr('')}}>{edit?'Cancel':'Back'}</button></div>
    </form>}
  </div></Modal>;
}
