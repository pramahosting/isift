import React,{useState} from 'react';
import {CalendarCheck} from 'lucide-react';
import {Modal} from './Workspace';
import {ConnectCalendar} from './ConnectCalendar';

const OPTS:[string,string,string][]=[['google','Google','Gmail, Google Calendar, Android phones'],['microsoft','Microsoft','Outlook.com, Hotmail, Microsoft 365'],['yahoo','Yahoo','Yahoo Calendar (needs an app password)'],['icloud','iCloud','iPhone and Mac calendars (needs an app password)']];

/** "Connect all my calendars": tick every service you use, then sign in to each in turn. Shown once on first use and from the calendar page. */
export function ConnectAll({request,onClose,onDone}:{request:any;onClose:()=>void;onDone:(msg:string)=>void}){
  const [pick,setPick]=useState<string[]>([]);const [queue,setQueue]=useState<string[]|null>(null);const [i,setI]=useState(0);const [ok,setOk]=useState<string[]>([]);
  const toggle=(k:string)=>setPick(p=>p.includes(k)?p.filter(x=>x!==k):[...p,k]);
  const label=(k:string)=>OPTS.find(o=>o[0]===k)?.[1]||k;
  const next=(good:boolean)=>{const got=good?[...ok,queue![i]]:ok;setOk(got);if(i+1>=queue!.length)onDone(got.length?`Connected: ${got.map(label).join(', ')}. Your meetings are being added.`:'No calendar was connected.');else setI(i+1)};
  if(queue)return <ConnectCalendar key={queue[i]} start={queue[i]} request={request} onClose={()=>next(false)} onDone={()=>next(true)}/>;
  return <Modal title="Connect all my calendars" onClose={onClose}><div className="ws-form">
    <p className="muted">Tick every calendar you use. iSift takes you through each sign-in, then keeps all your meetings up to date in one place.</p>
    <div className="ol-prov">{OPTS.map(([k,n,sub])=><label key={k} className={`ol-opt${pick.includes(k)?' on':''}`} style={{display:'flex',gap:8,alignItems:'flex-start',cursor:'pointer'}}><input type="checkbox" checked={pick.includes(k)} onChange={()=>toggle(k)}/><span><b>{n}</b><br/><small>{sub}</small></span></label>)}</div>
    <div className="actions"><button className="primary" disabled={!pick.length} onClick={()=>{setQueue(pick);setI(0)}}><CalendarCheck size={15}/> Connect {pick.length||''} selected</button><button type="button" className="secondary" onClick={onClose}>Not now</button></div>
    <p className="muted small">You can open this again any time from the Calendar page.</p>
  </div></Modal>;
}
