import React from 'react';

export const DAY_NAMES=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
const SETS:Record<string,number[]>={weekdays:[0,1,2,3,4],weekends:[5,6],every:[0,1,2,3,4,5,6]};
const same=(a:number[],b:number[])=>a.length===b.length&&[...a].sort().every((x,i)=>x===[...b].sort()[i]);
/** Drop-down shortcut that ticks the right day boxes: Every day, Weekdays (Mon to Fri), Weekends (Sat and Sun) or Custom. */
export function DayPreset({days,onChange,label='Quick select'}:{days:number[];onChange:(d:number[])=>void;label?:string}){
  const cur=Object.keys(SETS).find(k=>same(days,SETS[k]))||'custom';
  return <select className="daypreset" aria-label={label} value={cur} onChange={e=>{const v=e.target.value;if(SETS[v])onChange([...SETS[v]])}}>
    <option value="custom" disabled={cur!=='custom'}>Custom days</option><option value="weekdays">Weekdays (Monday to Friday)</option><option value="weekends">Weekends (Saturday and Sunday)</option><option value="every">Every day</option></select>;
}
