import {useEffect,useState} from 'react';

/** What each plan includes right now: the limits and modules the administrator set in Admin Console. Read from the server so the landing page, price list and comparison always match. */
export type PM={plans:Record<string,{limits:Record<string,any>;modules_off:string[]}>;modules:{id:string;label:string;enabled:boolean}[]};
export const PLAN_ORDER=['basic','individual','business'] as const;
export const PLAN_NAME:Record<string,string>={basic:'Basic',individual:'Standard',business:'Business'};
const API=()=>import.meta.env.VITE_API_BASE||(import.meta.env.VITE_DEMO_MODE==='true'?'http://127.0.0.1:8000/api/v1':'/api/v1');

export function usePlanMatrix():PM|null{
  const [d,setD]=useState<PM|null>(null);
  useEffect(()=>{let on=true;const get=()=>fetch(API()+'/plan-matrix?t='+Date.now(),{cache:'no-store'}).then(r=>r.json()).then(x=>on&&x?.plans&&setD(x)).catch(()=>{});get();const t=setInterval(get,30000);return()=>{on=false;clearInterval(t)}},[]);
  return d;
}
export type Need={module?:string|string[];limit?:string};
/** Does this plan include the feature: its module(s) are on for everyone and for the plan, and its switch (if any) is on. */
export function planHas(pm:PM|null,plan:string,n:Need):boolean{
  if(!pm)return true;const p=pm.plans[plan];if(!p)return false;
  const mods=n.module?(Array.isArray(n.module)?n.module:[n.module]):[];
  if(mods.length&&!mods.some(id=>{const m=pm.modules.find(x=>x.id===id);return (!m||m.enabled)&&!p.modules_off.includes(id)}))return false;
  if(n.limit&&p.limits[n.limit]===false)return false
  return true;
}
export const plansWith=(pm:PM|null,n:Need)=>PLAN_ORDER.filter(id=>planHas(pm,id,n));
/** " (paid plans)", " (Business plan)" and so on; "" when every plan has it; null when no plan does. */
export function planNote(pm:PM|null,n:Need):string|null{
  const w=plansWith(pm,n).join(',');
  return ({'basic,individual,business':'','individual,business':' (paid plans)','business':' (Business plan)','individual':' (Standard plan)','basic':' (Basic plan)','basic,individual':' (Basic and Standard plans)','basic,business':' (Basic and Business plans)'} as Record<string,string>)[w]??(w?'':null);
}
export const namesOf=(ids:readonly string[])=>ids.length===3?'every plan':ids.length===2&&ids[0]==='individual'?'the Standard and Business plans':ids.map(i=>PLAN_NAME[i]).join(' and ')+(ids.length===1?' plan':' plans');
const mb=(n:number)=>n>=1024?`${+(n/1024).toFixed(1)} GB`:`${n} MB`;
/** The plan's allowances as readable lines (used by the plan cards and the Compare plans table). */
export function limitText(pm:PM|null,plan:string){
  const L=pm?.plans[plan]?.limits||{};const paid=plan!=='basic';
  return {
    people:paid?'tiers':`Up to ${L.max_participants||25}`,
    length:L.meeting_minutes?`${L.meeting_minutes} minutes`:'Any length',
    ai:L.ai_per_month?`${L.ai_per_month} a month`:'Unlimited',
    booking:L.booking_pages?`${L.booking_pages}`:'Unlimited',
    docs:L.docs_per_day?`${L.docs_per_day} new files a day`:'Unlimited',
    pdf:L.pdf_pages?`Up to ${L.pdf_pages} pages`:'Any length',
    storage:L.storage_mb?mb(L.storage_mb):'Unlimited',
    hours:L.meeting_hours_per_month?`${L.meeting_hours_per_month} hours a month`:'Unlimited',
    recording:!L.recording?'No':L.cloud_recording?'Yes: stored in the cloud, download link emailed to the host':'Yes: saved on the host’s computer at the end of the meeting',
    yes:(k:string)=>L[k]?'Yes':'No'};
}
