import React,{useState} from 'react';
import {Globe} from 'lucide-react';

const KEY='isift.timezone';
export const deviceTz=():string=>{try{return Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC'}catch{return 'UTC'}};
/** The zone to use: a choice the person made, otherwise whatever this device (laptop or phone) reports right now. */
export const currentTz=():string=>{try{return localStorage.getItem(KEY)||deviceTz()}catch{return deviceTz()}};
export const saveTz=(tz:string|null)=>{try{tz?localStorage.setItem(KEY,tz):localStorage.removeItem(KEY)}catch{}};
export const tzLabel=(tz:string)=>{
  const parts=tz.split('/');const city=(parts[parts.length-1]||tz).replace(/_/g,' ');const region=parts.length>1?parts[0].replace(/_/g,' '):'';
  let off='';try{off=new Intl.DateTimeFormat('en',{timeZone:tz,timeZoneName:'shortOffset'}).formatToParts(new Date()).find(p=>p.type==='timeZoneName')?.value.replace('GMT','UTC')||''}catch{}
  return {city,region,off};
};
export const allZones=():string[]=>{try{return (Intl as any).supportedValuesOf('timeZone')}catch{return [deviceTz()]}};

export function TimeZoneChip({onChange}:{onChange:()=>void}){
  const [open,setOpen]=useState(false);const [tz,setTz]=useState(currentTz());
  const dev=deviceTz();const l=tzLabel(tz);const auto=tz===dev&&!(()=>{try{return localStorage.getItem(KEY)}catch{return null}})();
  const pick=(v:string)=>{saveTz(v==='auto'?null:v);setTz(currentTz());setOpen(false);onChange()};
  return <span className="tzchip">
    <button type="button" className="iconbtn tzbtn" aria-expanded={open} aria-label={`Time zone: ${l.city}. Change`} title={auto?'Time zone follows this device':'Time zone chosen by you'} onClick={()=>setOpen(o=>!o)}><Globe size={16}/><span className="tzcity">{l.city}</span>{l.off&&<span className="tzoff">{l.off}</span>}</button>
    {open&&<div className="tzmenu" role="dialog" aria-label="Time zone">
      <p><b>{l.city}{l.region?`, ${l.region}`:''}</b><br/><small>{auto?'Detected from this device. It updates by itself when you travel or use another device.':'Chosen by you.'}</small></p>
      <label>Time zone<select value={auto?'auto':tz} onChange={e=>pick(e.target.value)}><option value="auto">Automatic: this device ({tzLabel(dev).city})</option>{allZones().map(z=><option key={z} value={z}>{z.replace(/_/g,' ')}</option>)}</select></label>
      <button type="button" className="secondary" onClick={()=>setOpen(false)}>Close</button></div>}
  </span>;
}
