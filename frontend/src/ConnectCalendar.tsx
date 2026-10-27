import React,{useState} from 'react';
import {ExternalLink,CalendarPlus,Smartphone} from 'lucide-react';
import {Modal} from './Workspace';

type Step='pick'|'email'|'apppw'|'unavailable';
const GUIDE:any={
  yahoo:{label:'Yahoo',caldav:'yahoo',url:'https://login.yahoo.com/account/security',open:'Open Yahoo account security',steps:['Press the button below and sign in to Yahoo.','Choose Generate app password, type iSift as the name and press Generate.','Copy the 16-letter password and paste it here.']},
  icloud:{label:'iPhone (iCloud)',caldav:'icloud',url:'https://appleid.apple.com/account/manage',open:'Open Apple account',steps:['Press the button below and sign in with your Apple ID.','Open Sign-In and Security, then App-Specific Passwords, and make one called iSift.','Copy it and paste it here. Use your Apple ID email as the address.']},
};

/** One place to connect a calendar: pick Gmail, Outlook, Yahoo, iPhone or Android (or type an email) and iSift takes the shortest route. */
export function ConnectCalendar({request,onClose,onDone}:{request:any;onClose:()=>void;onDone:(msg:string)=>void}){
  const [step,setStep]=useState<Step>('pick');const [addr,setAddr]=useState('');const [kind,setKind]=useState('');const [pw,setPw]=useState('');
  const [busy,setBusy]=useState(false);const [err,setErr]=useState('');const [which,setWhich]=useState('');

  const signIn=async(id:string)=>{
    setErr('');setBusy(true);setWhich(id);
    try{
      const r=await request(`/oauth/${id}/start`,{method:'POST',body:JSON.stringify({origin:location.origin,email:addr.trim()})});
      const w=window.open(r.url,'isift-oauth','width=520,height=720,menubar=no,toolbar=no');
      if(!w){setErr('The sign-in window was blocked. Allow pop-ups for this page and try again.');return}
      await new Promise<void>(res=>{
        const end=()=>{window.removeEventListener('message',on);clearInterval(t);res()};
        const on=(e:MessageEvent)=>{if(e.origin!==location.origin||e.data?.type!=='isift-oauth')return;end();if(e.data.ok)onDone(e.data.message||'Calendar connected.');else setErr(e.data.message||'Sign-in did not finish.')};
        window.addEventListener('message',on);const t=setInterval(()=>{if(w.closed)end()},700);
      });
    }catch(x:any){if(/not set up/i.test(x.message||''))setStep('unavailable');else setErr(x.message)}finally{setBusy(false)}
  };
  const withPassword=(k:string)=>{setKind(k);setStep('apppw');setErr('')};
  const route=async(e:React.FormEvent)=>{e.preventDefault();setErr('');const a=addr.trim().toLowerCase();
    if(!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(a)){setErr('Enter your email address, for example name@gmail.com.');return}
    const d=a.split('@')[1];
    if(/^(yahoo\.|ymail\.|rocketmail\.)/.test(d)){withPassword('yahoo');return}
    if(/^(icloud|me|mac)\.com$/.test(d)){withPassword('icloud');return}
    setBusy(true);let p:string|null=null;
    try{p=(await request(`/oauth/detect?email=${encodeURIComponent(a)}`)).provider}catch{}
    if(!p){try{const m=await request(`/mailbox/autoconfig?email=${encodeURIComponent(a)}`);if(m?.oauth)p=m.oauth}catch{}}
    setBusy(false);
    if(p==='yahoo'){withPassword('yahoo');return}
    if(p){signIn(p);return}
    setErr('We could not tell which service looks after that address. Pick it from the list instead, or add a calendar link from the Connections page.');setStep('pick')};
  const addPassword=async(e:React.FormEvent)=>{e.preventDefault();setErr('');setBusy(true);
    try{const g=GUIDE[kind];const r=await request('/connections/caldav',{method:'POST',body:JSON.stringify({provider:g.caldav,label:addr.trim(),username:addr.trim(),password:pw})});
      onDone(r.message||'Calendar connected.')}
    catch(x:any){setErr(x.message)}finally{setBusy(false)}};

  const tile=(label:string,sub:string,go:()=>void,icon?:React.ReactNode)=><button type="button" disabled={busy} onClick={go}>{icon}<b>{label}</b><small>{sub}</small></button>;
  return <Modal title="Connect a calendar" onClose={onClose}><div className="ws-form ol-add-form">
    {step==='pick'&&<div>
      <p className="muted">Choose where your calendar lives. Your meetings appear in iSift and stay up to date.</p>
      <div className="ol-prov">
        {tile('Gmail / Google','Google Calendar, Gmail and Google Workspace',()=>signIn('google'))}
        {tile('Android','Android phones use your Google calendar',()=>signIn('google'),<Smartphone size={16}/>)}
        {tile('Outlook / Microsoft','Outlook.com, Hotmail and Microsoft 365',()=>signIn('microsoft'))}
        {tile('iPhone','Your iCloud calendar (needs an app password)',()=>withPassword('icloud'),<Smartphone size={16}/>)}
        {tile('Yahoo','Yahoo Calendar (needs an app password)',()=>withPassword('yahoo'))}
        {tile('Type my email','iSift finds the right one',()=>setStep('email'))}
      </div>
      <p className="muted small">On a phone, the calendar is saved in a Google, iCloud, Microsoft or Yahoo account. Choose that account here.</p>
      {busy&&<p className="muted small" role="status">Waiting for the sign-in window…</p>}
      {err&&<p className="syncerr" role="alert">{err}</p>}
      <div className="actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button></div>
    </div>}
    {step==='email'&&<form onSubmit={route}>
      <label>Email<input type="email" value={addr} onChange={e=>setAddr(e.target.value)} placeholder="name@example.com" autoComplete="email" autoFocus required/></label>
      {busy&&<p className="muted small" role="status">Checking…</p>}{err&&<p className="syncerr" role="alert">{err}</p>}
      <div className="actions"><button className="primary" disabled={busy||!addr.trim()}><CalendarPlus size={15}/> Continue</button><button type="button" className="secondary" onClick={()=>{setStep('pick');setErr('')}}>Back</button></div>
    </form>}
    {step==='apppw'&&GUIDE[kind]&&<form onSubmit={addPassword} className="conn-form">
      <p className="muted span2"><b>{GUIDE[kind].label}</b> shares your calendar through an app password, which is safer than your main password and can be removed at any time.</p>
      <ol className="span2" style={{margin:'0 0 6px 18px',padding:0}}>{GUIDE[kind].steps.map((s:string,i:number)=><li key={i}>{s}</li>)}</ol>
      <div className="span2"><a className="secondary btnlike" href={GUIDE[kind].url} target="_blank" rel="noreferrer"><ExternalLink size={14}/> {GUIDE[kind].open}</a></div>
      <label className="span2">Your {GUIDE[kind].label.split(' ')[0]} email<input type="email" value={addr} onChange={e=>setAddr(e.target.value)} placeholder={kind==='yahoo'?'name@yahoo.com':'name@icloud.com'} required/></label>
      <label className="span2">App password<input type="password" value={pw} onChange={e=>setPw(e.target.value)} autoComplete="new-password" required/></label>
      {err&&<p className="syncerr span2" role="alert">{err}</p>}
      <div className="actions span2"><button className="primary" disabled={busy||!pw||!addr.trim()}>{busy?'Checking…':'Connect calendar'}</button><button type="button" className="secondary" onClick={()=>{setStep('pick');setErr('');setPw('')}}>Back</button></div>
    </form>}
    {step==='unavailable'&&<div>
      <p><b>{which==='microsoft'?'Microsoft':'Google'} sign-in is not set up in this installation of iSift yet.</b></p>
      <p className="muted">Whoever installs iSift needs to register it once with {which==='microsoft'?'Microsoft':'Google'}. Nothing is wrong with your account.</p>
      <div className="actions"><button className="primary" onClick={()=>{setStep('pick');setErr('')}}>Back</button></div>
    </div>}
  </div></Modal>;
}
