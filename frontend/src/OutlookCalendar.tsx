import React,{useEffect,useMemo,useRef,useState} from 'react';
import {ChevronLeft,ChevronRight,RefreshCw,CalendarPlus,Video} from 'lucide-react';
import {Modal} from './Workspace';

const COLORS=['#0f6cbd','#c239b3','#038387','#ca5010','#7160e8','#498205','#c50f1f','#986f0b'];
const HOUR=48;
type View='day'|'workweek'|'week'|'month';
const sod=(d:Date)=>{const x=new Date(d);x.setHours(0,0,0,0);return x};
const addDays=(d:Date,n:number)=>{const x=new Date(d);x.setDate(x.getDate()+n);return x};
const monday=(d:Date)=>addDays(sod(d),-((d.getDay()+6)%7));
const sameDay=(a:Date,b:Date)=>a.toDateString()===b.toDateString();
const hm=(d:Date)=>d.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});

/** Outlook-style calendar: a combined view of every calendar, or one calendar at a time. Day, work week, week and month. */
export function OutlookCalendar({meetings,onOpen,onNew,onSync,request}:{request?:any;meetings:any[];onOpen:(id:string)=>void;onNew:()=>void;onSync:()=>void}){
  const [view,setView]=useState<View>(()=>{try{return (sessionStorage.getItem('isift.calview') as View)||'week'}catch{return 'week'}});
  const [cur,setCur]=useState(()=>{try{const f=sessionStorage.getItem('isift.calfocus');if(f){sessionStorage.removeItem('isift.calfocus');const d=new Date(f);if(!isNaN(+d))return sod(d)}}catch{}return sod(new Date())});   // opened from a booking: show that date
  const [hidden,setHidden]=useState<string[]>([]);
  const [linked,setLinked]=useState<string[]>([]);   // connected Google / Microsoft accounts, listed even before they have events
  useEffect(()=>{if(!request)return;request('/mailbox/accounts').then((r:any)=>setLinked((r.accounts||[]).filter((a:any)=>a.oauth==='google'||a.oauth==='microsoft').map((a:any)=>a.address))).catch(()=>{})},[request]);
  const [day,setDay]=useState<Date|null>(null);
  const scroller=useRef<HTMLDivElement>(null);
  const setV=(v:View)=>{setView(v);try{sessionStorage.setItem('isift.calview',v)}catch{}};

  const cals=useMemo(()=>{
    const ids=Array.from(new Set([...meetings.filter(m=>m.status!=='cancelled').map(m=>m.account||''),...linked]));
    ids.sort((a,b)=>a===''?-1:b===''?1:a.localeCompare(b));
    return ids.map((id,i)=>({id,name:id||'iSift and other calendars',color:COLORS[i%COLORS.length],count:meetings.filter(m=>(m.account||'')===id&&m.status!=='cancelled').length}));
  },[meetings,linked]);
  const color=(id:string)=>cals.find(c=>c.id===id)?.color||COLORS[0];
  const shown=meetings.filter(m=>m.status!=='cancelled'&&!hidden.includes(m.account||''));
  const only=cals.length>1&&hidden.length===cals.length-1?cals.find(c=>!hidden.includes(c.id)):null;

  const start=view==='month'?monday(new Date(cur.getFullYear(),cur.getMonth(),1)):view==='day'?cur:monday(cur);
  const days=view==='month'?Array.from({length:42},(_,i)=>addDays(start,i)):Array.from({length:view==='day'?1:view==='workweek'?5:7},(_,i)=>addDays(start,i));
  const step=(n:number)=>{if(view==='month'){const d=new Date(cur);d.setMonth(d.getMonth()+n,1);setCur(d)}else setCur(addDays(cur,n*(view==='day'?1:7)))};
  const title=view==='month'?cur.toLocaleDateString([],{month:'long',year:'numeric'}):view==='day'?cur.toLocaleDateString([],{weekday:'long',day:'numeric',month:'long',year:'numeric'}):`${days[0].toLocaleDateString([],{day:'numeric',month:'short'})} – ${days[days.length-1].toLocaleDateString([],{day:'numeric',month:'short',year:'numeric'})}`;
  const evOn=(d:Date)=>shown.filter(m=>sameDay(new Date(m.start_at),d)).sort((a,b)=>+new Date(a.start_at)-+new Date(b.start_at));
  useEffect(()=>{if(scroller.current&&view!=='month')scroller.current.scrollTop=7*HOUR-4},[view]);

  // overlapping events share the column side by side
  const layout=(evs:any[])=>{
    const out:any[]=[];let cluster:any[]=[];let end=0;
    const flush=()=>{const lanes:number[]=[];cluster.forEach(e=>{let l=lanes.findIndex(x=>x<=e.s);if(l<0){l=lanes.length;lanes.push(0)}lanes[l]=e.e;e.lane=l});cluster.forEach(e=>{e.n=lanes.length;out.push(e)});cluster=[]};
    evs.forEach(m=>{const s=new Date(m.start_at),e=new Date(m.end_at);const sm=s.getHours()*60+s.getMinutes();const em=Math.max(sm+20,Math.min(24*60,sm+Math.max(15,(+e-+s)/60000)));
      if(cluster.length&&sm>=end)flush();cluster.push({m,s:sm,e:em});end=Math.max(end,em)});
    if(cluster.length)flush();return out;
  };
  const toggle=(id:string)=>setHidden(h=>h.includes(id)?h.filter(x=>x!==id):[...h,id]);
  const miniStart=monday(new Date(cur.getFullYear(),cur.getMonth(),1));
  const now=new Date();

  return <div className="oc">
    <aside className="oc-side" aria-label="Calendars">
      <button className="ol-new oc-new" onClick={onNew}><CalendarPlus size={16}/> New event</button>
      <div className="oc-mini">
        <div className="oc-mh"><b>{cur.toLocaleDateString([],{month:'long',year:'numeric'})}</b><span><button className="iconbtn" aria-label="Previous month" onClick={()=>{const d=new Date(cur);d.setMonth(d.getMonth()-1,1);setCur(d)}}><ChevronLeft size={14}/></button><button className="iconbtn" aria-label="Next month" onClick={()=>{const d=new Date(cur);d.setMonth(d.getMonth()+1,1);setCur(d)}}><ChevronRight size={14}/></button></span></div>
        <div className="oc-mg">{['M','T','W','T','F','S','S'].map((d,i)=><i key={i}>{d}</i>)}{Array.from({length:42},(_,i)=>addDays(miniStart,i)).map(d=><button key={+d} className={`${d.getMonth()!==cur.getMonth()?'o':''}${sameDay(d,now)?' t':''}${sameDay(d,cur)?' s':''}${evOn(d).length?' e':''}`} onClick={()=>setCur(d)} aria-label={d.toDateString()}>{d.getDate()}</button>)}</div>
      </div>
      <div className="oc-cals">
        <button className={`oc-all${!hidden.length?' on':''}`} onClick={()=>setHidden([])}>All calendars <small>combined</small></button>
        {cals.map(c=><div key={c.id} className={`oc-cal${only?.id===c.id?' only':''}`}>
          <label title="Show or hide this calendar"><input type="checkbox" checked={!hidden.includes(c.id)} onChange={()=>toggle(c.id)} aria-label={`Show ${c.name}`}/><i style={{background:c.color}}/></label>
          <button className="nm" onClick={()=>setHidden(cals.filter(x=>x.id!==c.id).map(x=>x.id))} title="Show only this calendar">{c.name}</button><small>{c.count}</small></div>)}
        {!cals.length&&<p className="muted small">No calendars yet. Add an account on the Mail tab, or press Sync.</p>}
      </div>
    </aside>
    <section className="oc-main">
      <div className="oc-bar">
        <button className="secondary" onClick={()=>setCur(sod(new Date()))}>Today</button>
        <button className="iconbtn" aria-label="Previous" onClick={()=>step(-1)}><ChevronLeft size={18}/></button><button className="iconbtn" aria-label="Next" onClick={()=>step(1)}><ChevronRight size={18}/></button>
        <h2>{title}</h2>{only&&<span className="oc-badge" style={{borderColor:only.color}}>{only.name}</span>}{!only&&cals.length>1&&!hidden.length&&<span className="oc-badge">Combined</span>}
        <span className="grow"/>
        <div className="oc-seg" role="group" aria-label="View">{([['day','Day'],['workweek','Work week'],['week','Week'],['month','Month']] as const).map(([v,l])=><button key={v} className={view===v?'on':''} aria-pressed={view===v} onClick={()=>setV(v)}>{l}</button>)}</div>
        <button className="secondary" onClick={onSync}><RefreshCw size={15}/> Sync</button>
      </div>
      {view==='month'?<div className="oc-month" role="grid" aria-label="Calendar">
        {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(d=><div key={d} className="oc-dow">{d}</div>)}
        {days.map(d=>{const ev=evOn(d);return <div key={+d} role="gridcell" className={`oc-cell${d.getMonth()!==cur.getMonth()?' o':''}${sameDay(d,now)?' t':''}`}>
          <button className="oc-n" onClick={()=>setDay(d)} aria-label={`${d.toDateString()}, ${ev.length} events`}>{d.getDate()}</button>
          {ev.slice(0,3).map(m=><button key={m.id} className="oc-ev" style={{borderLeftColor:color(m.account||''),background:color(m.account||'')+'22'}} title={`${hm(new Date(m.start_at))} ${m.title}`} onClick={()=>onOpen(m.id)}><b>{hm(new Date(m.start_at))}</b> {m.title}</button>)}
          {ev.length>3&&<button className="oc-more" onClick={()=>setDay(d)}>+{ev.length-3} more</button>}</div>})}
      </div>:<div className="oc-week">
        <div className="oc-head" style={{gridTemplateColumns:`52px repeat(${days.length},1fr)`}}><span/>{days.map(d=><button key={+d} className={sameDay(d,now)?'t':''} onClick={()=>{setCur(d);setV('day')}}><small>{d.toLocaleDateString([],{weekday:'short'})}</small><b>{d.getDate()}</b></button>)}</div>
        <div className="oc-scroll" ref={scroller}><div className="oc-grid" style={{gridTemplateColumns:`52px repeat(${days.length},1fr)`,height:24*HOUR}}>
          <div className="oc-hours">{Array.from({length:24},(_,h)=><span key={h} style={{top:h*HOUR}}>{h===0?'':new Date(2000,0,1,h).toLocaleTimeString([],{hour:'numeric'})}</span>)}</div>
          {days.map(d=><div key={+d} className="oc-col" onDoubleClick={onNew}>
            {Array.from({length:24},(_,h)=><i key={h} style={{top:h*HOUR}}/>)}
            {sameDay(d,now)&&<u className="oc-now" style={{top:(now.getHours()*60+now.getMinutes())/60*HOUR}}/>}
            {layout(evOn(d)).map(({m,s,e,lane,n})=><button key={m.id} className="oc-blk" style={{top:s/60*HOUR,height:Math.max(20,(e-s)/60*HOUR-2),left:`calc(${lane*100/n}% + 2px)`,width:`calc(${100/n}% - 4px)`,borderLeftColor:color(m.account||''),background:color(m.account||'')+'26'}} onClick={()=>onOpen(m.id)} title={`${hm(new Date(m.start_at))} ${m.title}`}>
              <b>{m.title}</b><span>{hm(new Date(m.start_at))}</span></button>)}
          </div>)}
        </div></div>
      </div>}
      {!meetings.length&&<p className="muted pad">No events yet. Press Sync, or add an account on the Mail tab.</p>}
    </section>
    {day&&<Modal title={day.toLocaleDateString([],{weekday:'long',day:'numeric',month:'long',year:'numeric'})} onClose={()=>setDay(null)}><div className="ws-form">
      {evOn(day).length?evOn(day).map(m=><button key={m.id} className="secondary calday" onClick={()=>{setDay(null);onOpen(m.id)}}><i className="dot" style={{background:color(m.account||'')}}/> <Video size={14}/> <b>{hm(new Date(m.start_at))}</b> {m.title}</button>):<p className="muted">Nothing scheduled.</p>}
      <div className="actions"><button className="primary" onClick={()=>{setDay(null);onNew()}}>New event</button></div></div></Modal>}
  </div>;
}
