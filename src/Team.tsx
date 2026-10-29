import React,{useCallback,useEffect,useState} from 'react';
import {Users} from 'lucide-react';

const STATUS=[['needs_review','Needs review'],['proposed','Proposed'],['assigned','Assigned'],['in_progress','In progress'],['completed','Completed']];

/** Business plan: action items from teammates' normal meetings, so the whole team sees and updates them. Hidden when there is no Business company account. */
export function TeamActions({request}:{request:any}){
  const [rows,setRows]=useState<any[]|null>(null);const [err,setErr]=useState('');const [open,setOpen]=useState(false);
  const load=useCallback(async()=>{try{setRows(await request('/team/action-items'))}catch{setRows(null)}},[request]);
  useEffect(()=>{load()},[load]);
  if(rows===null)return null;
  const set=async(id:string,status:string)=>{setErr('');try{await request(`/team/action-items/${id}`,{method:'PATCH',body:JSON.stringify({status})});load()}catch(e:any){setErr(e.message)}};
  const shown=rows.filter(r=>open||r.status!=='completed');
  return <section className="panel team-actions"><div className="panelhead"><h2><Users size={18}/> Team action items</h2><label className="chk small"><input type="checkbox" checked={open} onChange={e=>setOpen(e.target.checked)}/> Show completed</label></div>
    <p className="muted pad small">From your teammates’ meetings on your company account. Sensitive meetings are never shared. Anyone on the team can change a status.</p>
    {err&&<p className="syncerr pad" role="alert">{err}</p>}
    {shown.length?shown.map(a=><div className="actionrow" key={a.id}><div><b>{a.description}</b><p className="muted">{a.meeting_title} · Owner: {a.owner||'Unassigned'} · Due: {a.due_date||'Not specified'}{a.mine?'':` · Meeting by ${a.meeting_owner}`}</p></div>
      <select aria-label="Team action status" value={a.status} onChange={e=>set(a.id,e.target.value)}>{STATUS.map(([v,t])=><option key={v} value={v}>{t}</option>)}</select></div>):<p className="muted pad">No open team action items.</p>}</section>;
}
