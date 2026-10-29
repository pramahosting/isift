import React,{useEffect,useState} from 'react';
import {Save,Trash2,UserPlus,Copy,Building2,KeyRound,User as UserIcon,Clock3,Puzzle} from 'lucide-react';
import {DayPreset,DAY_NAMES} from './DayPreset';
import {AddinsTab} from './Addins';
import {allZones,deviceTz,currentTz,tzLabel,saveTz} from './timezone';

const DAYS=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
const PLAN_NAME:Record<string,string>={basic:'Basic',individual:'Standard',business:'Business'};
const ROLE_NAME:Record<string,string>={owner:'Owner',admin:'Administrator',member:'Member'};

export function AccountPage({request,notify,onChanged,goPricing,goBilling}:{request:any;notify:(m:string)=>void;onChanged:()=>void;goPricing:()=>void;goBilling:()=>void}){
  const [data,setData]=useState<any>(null);const [tab,setTab]=useState(()=>{try{const t=sessionStorage.getItem('isift.acctTab');sessionStorage.removeItem('isift.acctTab');return t||'profile'}catch{return 'profile'}});
  const [err,setErr]=useState('');const [busy,setBusy]=useState(false);
  const load=()=>request('/account').then(setData).catch((e:any)=>setErr(e.message||'Could not load your account.'));
  useEffect(()=>{load()},[]);
  const run=async(f:()=>Promise<any>,ok?:string)=>{setErr('');setBusy(true);try{const r=await f();if(ok||r?.message)notify(ok||r.message);return r}catch(e:any){setErr(e.message||'Something went wrong.')}finally{setBusy(false)}};
  if(!data)return <section className="panel">{err?<p className="syncerr" role="alert">{err}</p>:'Loading…'}</section>;
  const tabs:[string,string,any][]=[['profile','Profile',UserIcon],['time','Time and location',Clock3],['password','Password',KeyRound],['company','Company',Building2],['addins','Add-ins and embedding',Puzzle]];
  return <div className="acct">
    <div className="tabs" role="tablist" aria-label="My account">{tabs.map(([id,label,I])=><button key={id} role="tab" aria-selected={tab===id} className={tab===id?'on':''} onClick={()=>{setTab(id);setErr('')}}><I size={16}/>{label}</button>)}</div>
    {err&&<p className="syncerr" role="alert">{err}</p>}
    {tab==='profile'&&<ProfileTab data={data} run={run} request={request} reload={()=>{load();onChanged()}} busy={busy}/>}
    {tab==='time'&&<TimeTab data={data} run={run} request={request} reload={()=>{load();onChanged()}} busy={busy}/>}
    {tab==='password'&&<PasswordTab data={data} run={run} request={request} busy={busy}/>}
    {tab==='addins'&&<AddinsTab request={request} run={run}/>}
    {tab==='company'&&<CompanyTab data={data} run={run} request={request} reload={load} busy={busy} goPricing={goPricing} goBilling={goBilling}/>}
  </div>;
}

function ProfileTab({data,run,request,reload,busy}:any){
  const [f,setF]=useState({display_name:data.user.display_name||'',phone:data.profile.phone,job_title:data.profile.job_title,department:data.profile.department,bio:data.profile.bio,language:data.profile.language,virtual_room:data.profile.virtual_room!==false});
  const set=(k:string)=>(e:any)=>setF({...f,[k]:e.target.value});
  return <section className="panel"><div className="panelhead"><h2>Profile</h2><span className="muted small">{data.user.role==='admin'?'Administrator':'Member'}</span></div>
    <form className="acct-form" onSubmit={e=>{e.preventDefault();run(()=>request('/account',{method:'PATCH',body:JSON.stringify(f)})).then(r=>r&&reload())}}>
      <label>Name<input value={f.display_name} onChange={set('display_name')} maxLength={100} required/></label>
      <label>Email<input value={data.user.email} readOnly aria-readonly/><small className="muted">Your email is your sign-in and cannot be changed here.</small></label>
      <label>Phone<input value={f.phone} onChange={set('phone')} maxLength={40} autoComplete="tel"/></label>
      <label>Job title<input value={f.job_title} onChange={set('job_title')} maxLength={100}/></label>
      <label>Department<input value={f.department} onChange={set('department')} maxLength={100}/></label>
      <label>Preferred language<input value={f.language} onChange={set('language')} maxLength={40} placeholder="English"/></label>
      <label className="span2 check"><input type="checkbox" checked={f.virtual_room} onChange={e=>setF({...f,virtual_room:e.target.checked})}/> Virtual room: show meeting participants around a boardroom table (up to 10 people). Switch off to always show the gallery in meetings you host. You can also change this for each meeting.</label>
      <label className="span2">About me<textarea value={f.bio} onChange={set('bio')} maxLength={500} rows={3}/></label>
      <div className="span2"><button className="primary" disabled={busy}><Save size={16}/> Save profile</button></div></form></section>;
}

function TimeTab({data,run,request,reload,busy}:any){
  const p=data.profile;
  const [tz,setTz]=useState(p.timezone||'auto');const [city,setCity]=useState(p.city);const [country,setCountry]=useState(p.country);
  const [days,setDays]=useState<number[]>(p.work_days);const [ws,setWs]=useState(p.work_start);const [we,setWe]=useState(p.work_end);
  const dev=deviceTz();
  return <section className="panel"><div className="panelhead"><h2>Time and location</h2></div>
    <form className="acct-form" onSubmit={e=>{e.preventDefault();run(async()=>{const r=await request('/account',{method:'PATCH',body:JSON.stringify({timezone:tz==='auto'?'':tz,city,country,work_days:days,work_start:ws,work_end:we})});saveTz(tz==='auto'?null:tz);return r},'Time and location saved.').then(r=>r&&reload())}}>
      <label className="span2">Time zone<select value={tz} onChange={e=>setTz(e.target.value)}><option value="auto">Automatic: this device ({tzLabel(dev).city})</option>{allZones().map(z=><option key={z} value={z}>{z.replace(/_/g,' ')}</option>)}</select><small className="muted">Used for your calendar, briefings and booking pages. Now: {tzLabel(tz==='auto'?currentTz():tz).city} ({tzLabel(tz==='auto'?currentTz():tz).off}).</small></label>
      <label>City<input value={city} onChange={e=>setCity(e.target.value)} maxLength={100} autoComplete="address-level2"/></label>
      <label>Country<input value={country} onChange={e=>setCountry(e.target.value)} maxLength={100} autoComplete="country-name"/></label>
      <div className="span2"><span className="lbl">Working days</span><DayPreset days={days} onChange={setDays}/><div className="mf-days" role="group" aria-label="Working days">{DAY_NAMES.map((n,i)=><label key={n} className={`daychk${days.includes(i)?' on':''}`}><input type="checkbox" checked={days.includes(i)} onChange={e=>setDays(d=>e.target.checked?[...d,i].sort():d.filter(x=>x!==i))}/>{n}</label>)}</div></div>
      <label>Day starts<input type="time" value={ws} onChange={e=>setWs(e.target.value)}/></label>
      <label>Day ends<input type="time" value={we} onChange={e=>setWe(e.target.value)}/></label>
      <div className="span2"><button className="primary" disabled={busy}><Save size={16}/> Save</button></div></form></section>;
}

function PasswordTab({data,run,request,busy}:any){
  const [cur,setCur]=useState('');const [nw,setNw]=useState('');const [again,setAgain]=useState('');const [bad,setBad]=useState('');
  if(!data.password.can_change)return <section className="panel"><div className="panelhead"><h2>Password</h2></div><p className="hint">{data.password.why}</p></section>;
  return <section className="panel"><div className="panelhead"><h2>Change password</h2></div>
    <form className="acct-form" onSubmit={e=>{e.preventDefault();setBad('');if(nw!==again){setBad('The two new passwords are not the same.');return}run(()=>request('/account/password',{method:'POST',body:JSON.stringify({current:cur,new:nw})})).then(r=>{if(r){setCur('');setNw('');setAgain('')}})}}>
      <label className="span2">Current password<input type="password" value={cur} onChange={e=>setCur(e.target.value)} autoComplete="current-password" required/></label>
      <label>New password<input type="password" value={nw} onChange={e=>setNw(e.target.value)} minLength={8} maxLength={128} autoComplete="new-password" required/><small className="muted">8 to 128 characters.</small></label>
      <label>Repeat new password<input type="password" value={again} onChange={e=>setAgain(e.target.value)} autoComplete="new-password" required/></label>
      {bad&&<p className="syncerr span2" role="alert">{bad}</p>}
      <div className="span2"><button className="primary" disabled={busy}><KeyRound size={16}/> Change password</button></div></form></section>;
}

function CompanyTab({data,run,request,reload,busy,goPricing,goBilling}:any){
  const c=data.company;
  const [name,setName]=useState('');const [plan,setPlan]=useState('basic');
  const [m,setM]=useState({name:'',email:'',role:'member',password:''});const [temp,setTemp]=useState<{email:string;pw:string}|null>(null);
  if(!c)return <section className="panel"><div className="panelhead"><h2>Company account</h2></div>
    <p className="hint">A company account brings your colleagues together under one name. You become its owner and can add people, give them roles. The company shares one plan.</p>
    <form className="acct-form" onSubmit={e=>{e.preventDefault();run(()=>request('/account/company',{method:'POST',body:JSON.stringify({name})}),'Company account created.').then(r=>r&&reload())}}>
      <label>Company name<input value={name} onChange={e=>setName(e.target.value)} maxLength={120} required/></label>
      <div className="span2"><button className="primary" disabled={busy}><Building2 size={16}/> Create company account</button></div></form></section>;
  const manage=c.can_manage,owner=c.my_role==='owner';
  return <>
    <section className="panel"><div className="panelhead"><h2>{c.name}</h2><span className="badge gray">{PLAN_NAME[c.plan]||c.plan} plan</span></div>
      {manage&&<form className="acct-form" onSubmit={e=>{e.preventDefault();run(()=>request('/account/company',{method:'PATCH',body:JSON.stringify({name:name||c.name})}),'Company saved.').then(r=>{if(r){setName('');reload()}})}}>
        <label>Company name<input value={name||c.name} onChange={e=>setName(e.target.value)} maxLength={120}/></label>
        <p className="hint span2">The company is on the <b>{PLAN_NAME[c.plan]||c.plan}</b> plan. {owner||manage?<button type="button" className="textbtn inline" onClick={goBilling}>Change plan or card</button>:'Only the owner or an administrator can change it.'}</p>
        <div className="span2"><button className="secondary" disabled={busy}><Save size={16}/> Save name</button></div></form>}
      {!manage&&<p className="hint">You are a {ROLE_NAME[c.my_role]?.toLowerCase()} of this company.</p>}</section>
    <section className="panel"><div className="panelhead"><h2>People ({c.members.length})</h2></div>
      <table className="modtable"><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th/></tr></thead><tbody>{c.members.map((x:any)=><tr key={x.email}>
        <td><b>{x.name||x.email}</b></td><td>{x.email}</td>
        <td>{manage&&x.role!=='owner'?<select value={x.role} aria-label={`Role of ${x.email}`} onChange={e=>run(()=>request(`/account/company/members/${encodeURIComponent(x.email)}`,{method:'PATCH',body:JSON.stringify({role:e.target.value})}),'Role changed.').then(reload)}><option value="admin">Administrator</option><option value="member">Member</option></select>:ROLE_NAME[x.role]}</td>
        <td><span className={`badge ${x.status==='active'?'green':'gray'}`}>{x.status==='active'?'Active':'Invited'}</span></td>
        <td>{x.role!=='owner'&&(manage||x.email===data.user.email.toLowerCase())&&<button className="iconbtn" title={x.email===data.user.email.toLowerCase()?'Leave company':`Remove ${x.email}`} onClick={()=>window.confirm(x.email===data.user.email.toLowerCase()?'Leave this company?':`Remove ${x.email} from the company?`)&&run(()=>request(`/account/company/members/${encodeURIComponent(x.email)}`,{method:'DELETE'})).then(reload)}><Trash2 size={16}/></button>}</td></tr>)}</tbody></table>
      {manage&&<><h3 className="acct-h">Add a person</h3>
        <form className="acct-form" onSubmit={e=>{e.preventDefault();run(()=>request('/account/company/members',{method:'POST',body:JSON.stringify(m)})).then(r=>{if(r){setTemp(r.temp_password?{email:m.email,pw:r.temp_password}:null);setM({name:'',email:'',role:'member',password:''});reload()}})}}>
          <label>Name<input value={m.name} onChange={e=>setM({...m,name:e.target.value})} maxLength={100}/></label>
          <label>Email<input type="email" value={m.email} onChange={e=>setM({...m,email:e.target.value})} required/></label>
          <label>Role<select value={m.role} onChange={e=>setM({...m,role:e.target.value})}><option value="member">Member</option><option value="admin">Administrator</option></select></label>
          {c.can_create_accounts&&<label>Starting password<input value={m.password} onChange={e=>setM({...m,password:e.target.value})} placeholder="Leave empty to create one" autoComplete="off"/><small className="muted">Only used if they do not have a sign-in yet.</small></label>}
          <div className="span2"><button className="primary" disabled={busy}><UserPlus size={16}/> Add to company</button></div></form>
        {temp&&<div className="okmsg" role="status">Sign-in for <b>{temp.email}</b>: temporary password <code>{temp.pw}</code> <button className="textbtn inline" onClick={()=>navigator.clipboard?.writeText(temp.pw)}><Copy size={13}/> Copy</button><br/><small>Shown once. They can change it under My account, Password.</small></div>}</>}
      <div className="acct-foot">{owner?<button className="secondary danger" onClick={()=>window.confirm('Delete this company account? People keep their own sign-ins.')&&run(()=>request('/account/company',{method:'DELETE'})).then(reload)}>Delete company account</button>:null}</div></section></>;
}
