import React,{useCallback,useEffect,useRef,useState} from 'react';
import {Mail,Copy,Check,KeyRound,Trash2,Globe,X as XIcon,Plus} from 'lucide-react';
import {Modal} from './Workspace';

/* isiftmail: an email address for anyone, on isiftmail or on your own domain (pramod@prama-ai.com) hosted here.
   Everything sits inside Commbox > Mail; the inbox, folders, compose and delete are the ordinary Mail screens. */

const SIG_MARK='-- \n';
/** Puts the signature into a new message (above any quoted reply), once. */
export function withSignature(body:string,sig:string){
  const s=(sig||'').trim();if(!s||body.includes(SIG_MARK+s))return body;
  const block=`\n\n${SIG_MARK}${s}`;
  return body.startsWith('\n\n—')||body.startsWith('\n\n-')?block+body:body+block;
}
/** The signature of one isiftmail address, loaded once when it is needed. */
export function useSignature(request:any,enabled:boolean,aid:string){
  const [got,setGot]=useState<{aid:string;sig:string}|null>(null);
  useEffect(()=>{if(!enabled||!aid||got?.aid===aid)return;let live=true;request(`/isiftmail/settings?aid=${encodeURIComponent(aid)}`).then((r:any)=>{if(live)setGot({aid,sig:r.signature||''})}).catch(()=>{if(live)setGot({aid,sig:''})});return()=>{live=false}},[enabled,aid,got,request]);
  return got&&got.aid===aid?got.sig:null;
}

export function IsiftmailOffer({domain,onStart,onDomain,compact}:{domain:string;onStart:()=>void;onDomain?:()=>void;compact?:boolean}){
  return <div className={`ism-offer${compact?' compact':''}`}>
    <Mail size={compact?18:30}/>
    <div><b>Need an email address?</b><p className="muted small">Get a free <b>name@{domain}</b> address in seconds, or use <b>your own domain</b> like you@your-company.com. Read, write, save drafts and set an auto-reply right here in Commbox.</p></div>
    <div className="ism-offer-btns"><button type="button" className="primary" onClick={onStart}>Get my address</button>{onDomain&&<button type="button" className="secondary" onClick={onDomain}><Globe size={14}/> Use my own domain</button>}</div>
  </div>;
}

function Copyable({label,value}:{label:string;value:string}){
  const [ok,setOk]=useState(false);
  return <div className="ism-copy"><small className="muted">{label}</small><code>{value}</code>
    <button type="button" className="secondary" aria-label={`Copy ${label}`} onClick={()=>{navigator.clipboard?.writeText(value).then(()=>{setOk(true);setTimeout(()=>setOk(false),1500)}).catch(()=>{})}}>{ok?<Check size={14}/>:<Copy size={14}/>}</button></div>;
}


function PhoneSetup({aid,request,imap,smtp,username,address,pw}:{aid:string;request:any;imap:{host:string;port:number};smtp:{host:string;port:number};username:string;address:string;pw?:string}){
  const [err,setErr]=useState('');const [busy,setBusy]=useState(false);
  const iphone=async()=>{setErr('');setBusy(true);try{const r=await request('/isiftmail/mobileconfig',{method:'POST',body:JSON.stringify({aid})});const u=URL.createObjectURL(new Blob([r.content],{type:'application/x-apple-aspen-config'}));const a=document.createElement('a');a.href=u;a.download=r.filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),2000)}catch(e:any){setErr(e.message)}finally{setBusy(false)}};
  const dom=address.split('@')[1]||'';
  return <details className="ism-phone"><summary>Use this address on your phone or in Outlook</summary>
    <div className="ism-phone-body">
      <p><b>iPhone, iPad or Mac:</b> open this page on the device, press the button, then open Settings and choose <b>Profile Downloaded</b> and Install. Your mail appears in the Mail app.</p>
      <div className="actions"><button type="button" className="secondary" disabled={busy} onClick={iphone}>{busy?'Preparing…':'Download iPhone setup'}</button></div>
      <p><b>Outlook and Android:</b> add the account with just <b>{address}</b>{pw?' and the password above':' and a new password (use Make a new password below)'}. Outlook and Android find the rest by themselves{dom?` for ${dom}`:''}. If you are asked, use:</p>
      <ul className="muted small"><li>Username <b>{username}</b></li><li>Incoming (IMAP): {imap.host}, port {imap.port}, SSL/TLS</li><li>Outgoing (SMTP): {smtp.host}, port {smtp.port}, STARTTLS</li></ul>
      {err&&<p className="syncerr" role="alert">{err}</p>}
    </div></details>;
}

/* ------------------------------------------------------------------ get an address */
export function IsiftmailSetup({status,presetDomain,request,onClose,onCreated,onDomains}:{status:any;presetDomain?:string;request:any;onClose:()=>void;onCreated:(accountId:string)=>void;onDomains:()=>void}){
  const verified:string[]=(status.domains||[]).filter((d:any)=>d.status==='verified').map((d:any)=>d.domain);
  const choices:string[]=[...(status.eligible?[status.domain]:[]),...verified];
  const [dom,setDom]=useState(presetDomain&&choices.includes(presetDomain)?presetDomain:choices[0]||status.domain);
  const [name,setName]=useState('');const [forEmail,setForEmail]=useState('');const [display,setDisplay]=useState('');
  const [chk,setChk]=useState<{ok:boolean;message:string}|null>(null);const [busy,setBusy]=useState(false);const [err,setErr]=useState('');const [made,setMade]=useState<any>(null);
  const own=dom!==status.domain;const seq=useRef(0);const [sugg,setSugg]=useState<string[]>([]);
  useEffect(()=>{if(own||!status.eligible)return;let live=true;request('/isiftmail/suggest').then((r:any)=>{if(!live)return;setSugg(r.names||[]);setName(n=>n||(r.names&&r.names[0])||'')}).catch(()=>{});return()=>{live=false}},[own,status.eligible,request]);
  useEffect(()=>{
    setChk(null);const n=name.trim();if(n.length<3)return;const id=++seq.current;
    const t=setTimeout(async()=>{try{const r=await request(`/isiftmail/check?name=${encodeURIComponent(n)}&domain=${encodeURIComponent(dom)}`);if(id===seq.current)setChk({ok:!!r.ok,message:r.message})}catch(e:any){if(id===seq.current)setChk({ok:false,message:e.message})}},350);
    return()=>clearTimeout(t);
  },[name,dom,request]);
  const create=async(e:React.FormEvent)=>{e.preventDefault();setErr('');setBusy(true);try{setMade(await request('/isiftmail/create',{method:'POST',body:JSON.stringify({name:name.trim(),domain:dom,for_email:own?forEmail.trim():'',display_name:own?display.trim():''})}))}catch(x:any){setErr(x.message)}finally{setBusy(false)}};
  const done=()=>made&&onCreated(made.assigned_to?'':made.account.id);
  return <Modal title={made?'Your address is ready':'Get an email address'} onClose={made?done:onClose}><div className="ws-form ism-form">
    {!made&&<form onSubmit={create}>
      {choices.length>1&&<label>Domain<select value={dom} onChange={e=>{setDom(e.target.value);setChk(null)}}>{choices.map(c=><option key={c} value={c}>@{c}{c===status.domain?' (free)':''}</option>)}</select></label>}
      <p className="muted">{!own&&sugg.length?'Pick a name, or type your own.':'Choose the first part of the address. Letters, numbers, dots, dashes and underscores.'}</p>
      {!own&&sugg.length>0&&<div className="ism-sugg" role="group" aria-label="Suggested names">{sugg.map(n=><button type="button" key={n} className={`ism-chip${name===n?' on':''}`} onClick={()=>setName(n)}>{n}</button>)}</div>}
      <label>Address<span className="ism-addr"><input value={name} onChange={e=>setName(e.target.value.toLowerCase().replace(/\s/g,''))} placeholder={own?'info':'your.name'} autoFocus autoComplete="off" spellCheck={false} maxLength={30} aria-describedby="ism-chk"/><b>@{dom}</b></span></label>
      <p id="ism-chk" className={chk?(chk.ok?'ism-ok':'syncerr'):'muted small'} role="status" aria-live="polite">{chk?chk.message:name.trim().length>=3?'Checking…':''}</p>
      {own&&<><label>Display name (optional)<input value={display} onChange={e=>setDisplay(e.target.value)} maxLength={80} placeholder="Pramod Singh"/></label>
        <label>For (optional)<input type="email" value={forEmail} onChange={e=>setForEmail(e.target.value)} placeholder="Leave empty for yourself, or type a team member's iSift email"/></label>
        {forEmail.trim()&&<p className="muted small">It appears in that person's Mail when they sign in to iSift with that email address. You can reset its password at any time under Your domains.</p>}</>}
      {err&&<p className="syncerr" role="alert">{err}</p>}
      <div className="actions"><button className="primary" disabled={busy||!chk?.ok}>{busy?'Creating…':'Create address'}</button><button type="button" className="secondary" onClick={onClose}>Cancel</button></div>
      <p className="muted small">Want <b>you@your-company.com</b>? <button type="button" className="linkbtn" onClick={onDomains}>Use your own domain</button>. It is hosted here and works like Microsoft 365 email.</p>
    </form>}
    {made&&<div>
      <p><b>{made.address}</b> is open.{made.assigned_to?` ${made.note}`:' It is already added to your Mail.'}</p>
      {made.assigned_to&&<><p className="muted small">Give this password to the person only if they want to use the mailbox in another app such as Outlook or a phone. iSift keeps the password for Mail itself. It is shown once.</p><Copyable label="Username" value={made.username}/><Copyable label="Password" value={made.password}/></>}
      {!made.assigned_to&&<PhoneSetup aid={made.account.id} request={request} imap={made.imap} smtp={made.smtp} username={made.username} address={made.address}/>}
      <div className="actions"><button className="primary" onClick={done}>{made.assigned_to?'Done':'Open my inbox'}</button></div>
    </div>}
  </div></Modal>;
}

/* ------------------------------------------------------------------ settings of one address */
export function IsiftmailSettings({aid,request,onClose,onChanged,onClosed,onDomains}:{aid:string;request:any;onClose:()=>void;onChanged:()=>void;onClosed:()=>void;onDomains:()=>void}){
  const [s,setS]=useState<any>(null);const [err,setErr]=useState('');const [note,setNote]=useState('');const [busy,setBusy]=useState('');
  const [sig,setSig]=useState('');const [ar,setAr]=useState({on:false,subject:'',message:'',start:'',end:''});
  const [pw,setPw]=useState<any>(null);const [confirm,setConfirm]=useState('');
  useEffect(()=>{request(`/isiftmail/settings?aid=${encodeURIComponent(aid)}`).then((r:any)=>{setS(r);setSig(r.signature||'');setAr(r.autoreply)}).catch((e:any)=>setErr(e.message))},[request,aid]);
  const run=async(what:string,fn:()=>Promise<void>)=>{setErr('');setNote('');setBusy(what);try{await fn()}catch(e:any){setErr(e.message)}finally{setBusy('')}};
  const saveSig=()=>run('sig',async()=>{await request('/isiftmail/settings',{method:'PUT',body:JSON.stringify({aid,signature:sig})});setNote('Signature saved. It is added to new messages you write.');onChanged()});
  const saveAr=()=>run('ar',async()=>{await request('/isiftmail/settings',{method:'PUT',body:JSON.stringify({aid,autoreply:ar})});setNote(ar.on?'Auto-reply is on.':'Auto-reply is off.')});
  const newPw=()=>{if(!window.confirm('Make a new password? Other apps that use the old one will need the new one. iSift keeps working.'))return;run('pw',async()=>{setPw(await request('/isiftmail/password',{method:'POST',body:JSON.stringify({aid})}))})};
  const closeBox=()=>run('close',async()=>{await request('/isiftmail/mailbox',{method:'DELETE',body:JSON.stringify({aid,confirm})});onClosed()});
  return <Modal title="isiftmail settings" onClose={onClose} wide><div className="ws-form ism-form">
    {!s&&!err&&<p className="muted">Loading…</p>}
    {err&&<p className="syncerr" role="alert">{err}</p>}{note&&<p className="ism-ok" role="status">{note}</p>}
    {s&&<>
      <h3>{s.address}</h3>
      <section className="ism-sec"><h4>Signature</h4>
        <p className="muted small">Added at the bottom of each new message you write from this address.</p>
        <textarea aria-label="Signature" rows={4} maxLength={1000} value={sig} onChange={e=>setSig(e.target.value)} placeholder={'Your name\nYour phone or website'}/>
        <div className="actions"><button className="primary" disabled={busy==='sig'||sig===(s.signature||'')} onClick={saveSig}>Save signature</button></div></section>
      <section className="ism-sec"><h4>Auto-reply</h4>
        <label className="ism-row"><input type="checkbox" checked={ar.on} onChange={e=>setAr({...ar,on:e.target.checked})}/> Reply automatically while I am away</label>
        {ar.on&&<>
          <label>Subject<input value={ar.subject} maxLength={120} onChange={e=>setAr({...ar,subject:e.target.value})} placeholder="Automatic reply"/></label>
          <label>Message<textarea rows={4} maxLength={2000} value={ar.message} onChange={e=>setAr({...ar,message:e.target.value})} placeholder="Thanks for your email. I am away until Monday and will reply when I am back."/></label>
          <div className="ism-dates"><label>From (optional)<input type="date" value={ar.start} onChange={e=>setAr({...ar,start:e.target.value})}/></label><label>Until (optional)<input type="date" value={ar.end} min={ar.start||undefined} onChange={e=>setAr({...ar,end:e.target.value})}/></label></div>
          <p className="muted small">Each sender gets the reply once a day at most.</p></>}
        <div className="actions"><button className="primary" disabled={busy==='ar'||(ar.on&&!ar.message.trim())} onClick={saveAr}>Save auto-reply</button></div></section>
      <section className="ism-sec"><h4>Use this mailbox in another app</h4>
        <PhoneSetup aid={aid} request={request} imap={s.imap} smtp={s.smtp} username={s.username} address={s.address} pw={pw?.password}/>
        {pw&&<Copyable label="New password (shown once)" value={pw.password}/>}
        <div className="actions"><button type="button" className="secondary" disabled={busy==='pw'} onClick={newPw}><KeyRound size={14}/> Make a new password</button></div></section>
      <section className="ism-sec"><h4>Your own domain</h4>
        <p className="muted small">Use an address like you@your-company.com, and make mailboxes for your team, hosted here.</p>
        <div className="actions"><button type="button" className="secondary" onClick={onDomains}><Globe size={14}/> Your domains</button></div></section>
      <section className="ism-sec danger"><h4>Close this mailbox</h4>
        <p className="muted small">This deletes the address and every message in it. It cannot be undone. The address is kept aside for a while so nobody else can take it over.</p>
        <label><span>Type <b>{s.address}</b> to confirm</span><input value={confirm} onChange={e=>setConfirm(e.target.value)} autoComplete="off"/></label>
        <div className="actions"><button type="button" className="secondary" disabled={busy==='close'||confirm.trim().toLowerCase()!==s.address} onClick={closeBox}><Trash2 size={14}/> Close this mailbox</button></div></section>
    </>}
  </div></Modal>;
}

/* ------------------------------------------------------------------ your own domains (like adding a domain in Microsoft 365) */
const PURPOSE:Record<string,string>={owner:'owner',mx:'mx',spf:'spf',dkim:'dkim',dmarc:'dmarc',autodiscover:'autodiscover',autoconfig:'autoconfig',srv:'srv'};
const NICE:Record<string,string>={owner:'Ownership',mx:'Mail delivery (MX)',spf:'SPF',dkim:'DKIM',dmarc:'DMARC',autodiscover:'Outlook auto-setup',autoconfig:'Thunderbird and phone auto-setup',srv:'Outlook auto-setup (backup)'};

function DomainCard({d,request,reload,onAddress}:{d:any;request:any;reload:()=>void;onAddress:(dom:string)=>void}){
  const [res,setRes]=useState<any>(null);const [busy,setBusy]=useState('');const [err,setErr]=useState('');
  const [boxes,setBoxes]=useState<any[]|null>(null);const [pw,setPw]=useState<any>(null);const [closing,setClosing]=useState('');const [typed,setTyped]=useState('');
  const verified=d.status==='verified';const [where,setWhere]=useState<any>(null);const [copied,setCopied]=useState(false);
  useEffect(()=>{if(verified)return;let live=true;request('/isiftmail/domains/where',{method:'POST',body:JSON.stringify({domain:d.domain})}).then((r:any)=>{if(live)setWhere(r)}).catch(()=>{});return()=>{live=false}},[verified,d.domain,request]);
  const loadBoxes=useCallback(()=>{if(verified)request(`/isiftmail/domains/mailboxes?domain=${encodeURIComponent(d.domain)}`).then((r:any)=>setBoxes(r.mailboxes)).catch((e:any)=>setErr(e.message))},[verified,d.domain,request]);
  useEffect(()=>{loadBoxes()},[loadBoxes]);
  const run=async(what:string,fn:()=>Promise<void>)=>{setErr('');setBusy(what);try{await fn()}catch(e:any){setErr(e.message)}finally{setBusy('')}};
  const check=()=>run('check',async()=>{const r=await request('/isiftmail/domains/check',{method:'POST',body:JSON.stringify({domain:d.domain})});setRes(r);reload()});
  const remove=()=>{if(!window.confirm(`Remove ${d.domain} from isiftmail?`))return;run('rm',async()=>{await request('/isiftmail/domains',{method:'DELETE',body:JSON.stringify({domain:d.domain})});reload()})};
  const reset=(a:string)=>{if(!window.confirm(`Make a new password for ${a}?`))return;run('pw'+a,async()=>{setPw({...(await request('/isiftmail/domains/mailboxes/password',{method:'POST',body:JSON.stringify({address:a})})),address:a})})};
  const closeBox=(a:string)=>run('close',async()=>{await request('/isiftmail/domains/mailboxes',{method:'DELETE',body:JSON.stringify({address:a,confirm:typed})});setClosing('');setTyped('');loadBoxes();reload()});
  const recs:any[]=res?.records||d.records;const checks=res?.checks||null;
  useEffect(()=>{if(verified)return;const t=setInterval(()=>{request('/isiftmail/domains/check',{method:'POST',body:JSON.stringify({domain:d.domain})}).then((r:any)=>{setRes(r);if(r.verified)reload()}).catch(()=>{})},20000);return()=>clearInterval(t)},[verified,d.domain,request,reload]);
  const found=checks?Object.values(checks).filter(Boolean).length:0;const total=checks?Object.keys(checks).length:0;
  const copyAll=()=>{const txt=recs.map((r:any)=>`${r.type}\t${r.name}\t${r.value}`).join('\n');navigator.clipboard?.writeText(txt).then(()=>{setCopied(true);setTimeout(()=>setCopied(false),1800)}).catch(()=>{})};
  return <section className="ism-dom">
    <div className="ism-dom-h"><h4><Globe size={15}/> {d.domain}</h4><span className={`ism-badge ${verified?'ok':'wait'}`}>{verified?'Verified':'Waiting for DNS'}</span></div>
    {!verified&&<div className="ism-steps"><ol>
      <li><b>{where?.registrar?`Your domain is managed at ${where.registrar}.`:'Open where your domain is managed.'}</b> {where?.how||'Sign in where you bought the domain and open its DNS settings.'}</li>
      <li>Add the records below (the first one proves the domain is yours). <button type="button" className="linkbtn" onClick={copyAll}>{copied?'Copied':'Copy all records'}</button></li>
      <li>That is all. iSift checks again by itself every 20 seconds{total?` (${found} of ${total} found)`:''}, and you can press <b>Check my DNS</b> at any time. Changes can take a few minutes.</li></ol></div>}
    <div className="ism-recs" role="table" aria-label={`DNS records for ${d.domain}`}>
      {recs.map((r:any,i:number)=><div key={i} className="ism-rec" role="row">
        <div className="ism-rec-h"><b>{NICE[PURPOSE[r.purpose]]||r.purpose}</b><span className="muted small">{r.required?'Required':'Recommended'}</span>{checks&&checks[r.purpose]!==undefined&&<span className={checks[r.purpose]?'ism-ok':'syncerr'}>{checks[r.purpose]?<><Check size={13}/> Found</>:<><XIcon size={13}/> Not found yet</>}</span>}</div>
        <div className="ism-rec-grid"><small className="muted">Type</small><code>{r.type}</code><small className="muted">Name / Host</small><Copyable label="Name" value={r.name}/><small className="muted">Value</small><Copyable label="Value" value={r.value}/></div>
        <p className="muted small">{r.help}</p></div>)}
      {!recs.some((r:any)=>r.purpose==='dkim')&&<p className="muted small">The DKIM record (it signs your mail) appears here once the domain is verified.</p>}
    </div>
    {res?.message&&<p className={res.verified?'ism-ok':'muted'} role="status">{res.message}</p>}{err&&<p className="syncerr" role="alert">{err}</p>}
    <div className="actions"><button className="primary" disabled={busy==='check'} onClick={check}>{busy==='check'?'Checking…':'Check my DNS'}</button>{verified&&<button className="secondary" onClick={()=>onAddress(d.domain)}><Plus size={14}/> Add a mailbox</button>}<button className="secondary" disabled={busy==='rm'} onClick={remove}>Remove domain</button></div>
    {verified&&<div className="ism-boxes"><h5>Mailboxes on {d.domain}</h5>
      {boxes===null?<p className="muted small">Loading…</p>:!boxes.length?<p className="muted small">None yet. Press Add a mailbox.</p>:boxes.map((b:any)=><div key={b.address} className="ism-box">
        <div><b>{b.address}</b>{b.display&&<span className="muted small"> · {b.display}</span>}<div className="muted small">{b.yours?'Yours':b.assignee}{b.status==='waiting'?' · appears when they sign in to iSift':''}</div></div>
        <div className="ism-box-btns"><button className="secondary" disabled={busy==='pw'+b.address} onClick={()=>reset(b.address)} title="Make a new password"><KeyRound size={14}/></button><button className="secondary" onClick={()=>{setClosing(b.address);setTyped('')}} title="Close this mailbox"><Trash2 size={14}/></button></div>
        {pw?.address===b.address&&<div className="ism-box-pw"><Copyable label="New password (shown once)" value={pw.password}/></div>}
        {closing===b.address&&<div className="ism-box-pw"><p className="muted small">This deletes the mailbox and every message in it. Type <b>{b.address}</b> to confirm.</p><input aria-label="Type the address to confirm" value={typed} onChange={e=>setTyped(e.target.value)} autoComplete="off"/><div className="actions"><button className="secondary" disabled={busy==='close'||typed.trim().toLowerCase()!==b.address} onClick={()=>closeBox(b.address)}>Close mailbox</button><button className="secondary" onClick={()=>setClosing('')}>Cancel</button></div></div>}
      </div>)}</div>}
  </section>;
}

export function IsiftmailDomains({request,onClose,onAddress,onChanged}:{request:any;onClose:()=>void;onAddress:(domain:string)=>void;onChanged:()=>void}){
  const [list,setList]=useState<any[]|null>(null);const [name,setName]=useState('');const [busy,setBusy]=useState(false);const [err,setErr]=useState('');const [mx,setMx]=useState('');
  const load=useCallback(()=>{request('/isiftmail/domains').then((r:any)=>{setList(r.domains);setMx(r.mx)}).catch((e:any)=>setErr(e.message));onChanged()},[request,onChanged]);
  useEffect(()=>{load()},[]);// eslint-disable-line react-hooks/exhaustive-deps
  const add=async(e:React.FormEvent)=>{e.preventDefault();setErr('');setBusy(true);try{await request('/isiftmail/domains',{method:'POST',body:JSON.stringify({domain:name.trim()})});setName('');load()}catch(x:any){setErr(x.message)}finally{setBusy(false)}};
  return <Modal title="Your domains" onClose={onClose} wide><div className="ws-form ism-form">
    <p className="muted">Use your own domain for email, like <b>you@your-company.com</b>, with mailboxes for your team, hosted here. Add the domain, add the DNS records shown, then check. It works like adding a domain in Microsoft 365.</p>
    <form onSubmit={add} className="ism-adddom"><label>Your domain<input value={name} onChange={e=>setName(e.target.value)} placeholder="your-company.com" autoComplete="off" spellCheck={false} aria-label="Your domain"/></label><button className="primary" disabled={busy||name.trim().length<4}>{busy?'Adding…':'Add domain'}</button></form>
    {err&&<p className="syncerr" role="alert">{err}</p>}
    {list===null&&!err&&<p className="muted">Loading…</p>}
    {list&&!list.length&&<p className="muted small">No domains yet. Mail for your domain will be delivered to {mx||'this service'}.</p>}
    {list?.map(d=><DomainCard key={d.domain} d={d} request={request} reload={load} onAddress={onAddress}/>)}
  </div></Modal>;
}
