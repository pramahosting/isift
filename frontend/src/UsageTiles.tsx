import React,{useEffect,useState} from 'react';
import {Clock,Video,FileText,FilePenLine,FileSignature,PenLine,Phone,Sparkles,Users,HardDrive} from 'lucide-react';

type Stats={month:string;current:Record<string,number>;previous:Record<string,number>;history:({month:string}&Record<string,number>)[];caps:{hours:number;ai_summaries:number;recording:boolean;calls:boolean;storage_mb:number};storage_used_mb:number};
const MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const label=(m:string)=>MONTHS[Number(m.slice(5,7))-1]||m;
const fmt=(v:number,hours?:boolean)=>hours?(v%1?v.toFixed(1):String(v)):String(Math.round(v));

function Bars({vals,months}:{vals:number[];months:string[]}){
  const max=Math.max(1,...vals);
  return <svg className="ut-bars" viewBox="0 0 120 34" role="img" aria-label={`Last six months: ${vals.join(', ')}`}>
    {vals.map((v,i)=>{const h=Math.max(v>0?3:1,Math.round((v/max)*26));return <g key={i}><rect x={i*20+3} y={28-h} width={14} height={h} rx={2} className={i===vals.length-1?'now':''}/><text x={i*20+10} y={34} textAnchor="middle">{label(months[i]).slice(0,1)}</text></g>})}
  </svg>;
}

export function UsageTiles({request}:{request:(p:string)=>Promise<any>}){
  const [s,setS]=useState<Stats|null>(null);const [err,setErr]=useState(false);
  useEffect(()=>{let live=true;request('/me/usage').then((d:Stats)=>{if(live)setS(d)}).catch(()=>{if(live)setErr(true)});return()=>{live=false}},[]);
  if(err)return null;
  if(!s)return <section className="ut" aria-label="This month"><div className="ut-head"><b>Your month</b></div><p className="muted small">Loading…</p></section>;
  const c=s.current,p=s.previous,H=s.history;
  const tiles:{k:string;title:string;icon:any;hours?:boolean;note?:string;off?:boolean}[]=[
    {k:'hours',title:'Hours in meetings you hosted',icon:Clock,hours:true,note:s.caps.hours?`of ${s.caps.hours} h your plan allows`:undefined},
    {k:'meetings',title:'Meetings hosted',icon:Users},
    {k:'recordings',title:'Recordings made',icon:Video,off:!s.caps.recording,note:!s.caps.recording?'Not in your plan':undefined},
    {k:'pdf_edited',title:'PDFs edited',icon:FilePenLine},
    {k:'pdf_signed',title:'PDFs signed',icon:FileSignature},
    {k:'docs_created',title:'Documents created',icon:FileText},
    {k:'docs_edited',title:'Documents edited',icon:FilePenLine},
    {k:'boards_created',title:'Whiteboards created',icon:PenLine},
    {k:'calls',title:'Calls made',icon:Phone,off:!s.caps.calls,note:!s.caps.calls?'Not in your plan':undefined},
    {k:'ai_summaries',title:'AI summaries',icon:Sparkles,note:s.caps.ai_summaries?`of ${s.caps.ai_summaries} a month`:undefined},
  ];
  const delta=(k:string)=>{const a=c[k]||0,b=p[k]||0;if(!a&&!b)return null;if(!b)return {t:'new this month',cls:'up'};const d=Math.round((a-b)/b*100);return {t:`${d>0?'+':''}${d}% vs last month`,cls:d>0?'up':d<0?'down':''}};
  const pct=s.caps.hours?Math.min(100,Math.round((c.hours||0)/s.caps.hours*100)):0;
  return <section className="ut" aria-label="Your month in numbers">
    <div className="ut-head"><b>Your month</b><span className="muted small">{MONTHS[Number(s.month.slice(5,7))-1]} {s.month.slice(0,4)} · counts reset on the 1st</span></div>
    <div className="ut-grid">{tiles.map(t=>{const Icon=t.icon;const d=delta(t.k);return <div key={t.k} className={`ut-tile${t.off?' off':''}`}>
      <div className="ut-top"><span className="ut-ic"><Icon size={16}/></span><span className="ut-title">{t.title}</span></div>
      <div className="ut-num">{fmt(c[t.k]||0,t.hours)}{t.hours&&<small> h</small>}</div>
      {t.hours&&s.caps.hours>0&&<div className="ut-meter" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><i style={{width:pct+'%'}}/></div>}
      <div className="ut-foot">{t.note?<span className="muted">{t.note}</span>:d?<span className={`ut-d ${d.cls}`}>{d.t}</span>:<span className="muted">Nothing yet</span>}</div>
      {(t.k==='hours'||t.k==='meetings'||t.k==='docs_created')&&<Bars vals={H.map(x=>t.k==='hours'?x.hours:x[t.k]||0)} months={H.map(x=>x.month)}/>}
    </div>})}
      <div className="ut-tile"><div className="ut-top"><span className="ut-ic"><HardDrive size={16}/></span><span className="ut-title">Storage used</span></div>
        <div className="ut-num">{s.storage_used_mb}<small> MB</small></div>
        {s.caps.storage_mb>0&&<><div className="ut-meter" role="progressbar" aria-valuenow={Math.min(100,Math.round(s.storage_used_mb/s.caps.storage_mb*100))}><i style={{width:Math.min(100,Math.round(s.storage_used_mb/s.caps.storage_mb*100))+'%'}}/></div><div className="ut-foot"><span className="muted">of {s.caps.storage_mb} MB</span></div></>}</div>
    </div>
  </section>;
}
