import React,{useEffect,useState} from 'react';
import {Clock,Video,FileText,FilePenLine,FileSignature,PenLine,Phone,Sparkles,Users,HardDrive,ChevronDown,ChevronUp,BarChart3} from 'lucide-react';

type Stats={month:string;current:Record<string,number>;previous:Record<string,number>;history:({month:string}&Record<string,number>)[];caps:{hours:number;ai_summaries:number;recording:boolean;calls:boolean;storage_mb:number};storage_used_mb:number};
const MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const fmt=(v:number,hours?:boolean)=>hours?(v%1?v.toFixed(1):String(v)):String(Math.round(v));
const KEY='isift.usage.open';

export function UsageTiles({request}:{request:(p:string)=>Promise<any>}){
  const [s,setS]=useState<Stats|null>(null);const [err,setErr]=useState(false);
  const [open,setOpen]=useState(()=>{try{return localStorage.getItem(KEY)==='1'}catch{return false}});
  const flip=()=>setOpen(o=>{const n=!o;try{localStorage.setItem(KEY,n?'1':'0')}catch{}return n});
  useEffect(()=>{let live=true;request('/me/usage').then((d:Stats)=>{if(live)setS(d)}).catch(()=>{if(live)setErr(true)});return()=>{live=false}},[]);
  if(err)return null;
  const c=s?.current||{},p=s?.previous||{};
  const tiles:{k:string;title:string;icon:any;tone:string;hours?:boolean;off?:boolean}[]=s?[
    {k:'hours',title:'Meeting hours',icon:Clock,tone:'blue',hours:true},
    {k:'meetings',title:'Meetings hosted',icon:Users,tone:'violet'},
    {k:'recordings',title:'Recordings',icon:Video,tone:'rose',off:!s.caps.recording},
    {k:'pdf_edited',title:'PDFs edited',icon:FilePenLine,tone:'amber'},
    {k:'pdf_signed',title:'PDFs signed',icon:FileSignature,tone:'green'},
    {k:'docs_created',title:'Docs created',icon:FileText,tone:'teal'},
    {k:'docs_edited',title:'Docs edited',icon:FilePenLine,tone:'sky'},
    {k:'boards_created',title:'Whiteboards',icon:PenLine,tone:'orange'},
    {k:'calls',title:'Calls made',icon:Phone,tone:'indigo',off:!s.caps.calls},
    {k:'ai_summaries',title:'AI summaries',icon:Sparkles,tone:'pink'},
  ]:[];
  const delta=(k:string)=>{const a=c[k]||0,b=p[k]||0;if(!a||!b)return '';const d=Math.round((a-b)/b*100);return d?` ${d>0?'▲':'▼'}${Math.abs(d)}%`:''};
  const limitNote=(k:string)=>!s?'':k==='hours'&&s.caps.hours?` / ${s.caps.hours} h`:k==='ai_summaries'&&s.caps.ai_summaries?` / ${s.caps.ai_summaries}`:'';
  const month=s?`${MONTHS[Number(s.month.slice(5,7))-1]} ${s.month.slice(0,4)}`:'';
  return <section className={`ut${open?' open':''}`} aria-label="Your month in numbers">
    <button type="button" className="ut-bar" aria-expanded={open} onClick={flip}>
      <span className="ut-barl"><BarChart3 size={17}/><b>Your month</b><span className="muted small">{month}</span></span>
      {!open&&s&&<span className="ut-sum"><span><b>{fmt(c.hours||0,true)}</b> h</span><span><b>{c.meetings||0}</b> meetings</span><span><b>{(c.docs_created||0)+(c.docs_edited||0)}</b> docs</span><span><b>{(c.pdf_edited||0)+(c.pdf_signed||0)}</b> PDFs</span><span><b>{c.calls||0}</b> calls</span></span>}
      <span className="ut-chev">{open?<ChevronUp size={18}/>:<ChevronDown size={18}/>}</span>
    </button>
    {open&&(s?<div className="ut-grid">{tiles.map(t=>{const Icon=t.icon;return <div key={t.k} className={`ut-tile t-${t.tone}${t.off?' off':''}`} title={t.off?'Not in your plan':t.title}>
      <span className="ut-ic"><Icon size={15}/></span>
      <span className="ut-num">{fmt(c[t.k]||0,t.hours)}<small>{limitNote(t.k)}{t.hours&&!limitNote(t.k)?' h':''}</small></span>
      <span className="ut-title">{t.title}{!t.off&&<em>{delta(t.k)}</em>}</span>
    </div>})}
      <div className="ut-tile t-slate" title="Storage used"><span className="ut-ic"><HardDrive size={15}/></span><span className="ut-num">{s.storage_used_mb}<small>{s.caps.storage_mb?` / ${s.caps.storage_mb} MB`:' MB'}</small></span><span className="ut-title">Storage</span></div>
    </div>:<p className="muted small ut-load">Loading…</p>)}
    {open&&<p className="ut-note muted small">Counts are for this calendar month and start again on the 1st.</p>}
  </section>;
}
