import React,{useEffect,useState} from 'react';
import {Check,Sun,ArrowLeft,Sparkles,Building2} from 'lucide-react';
import {LegalFooter} from './Legal';

export type PlanId='basic'|'individual'|'business';
export type Period='monthly'|'yearly';
// Monthly prices; yearly = the earlier yearly price (135.96 / 175.92) less a further 5%. Must match PLANS in backend/app/services/billing.py.
export const PLAN_PRICES:Record<PlanId,{monthly:number;perMonthYearly:number;yearly:number}>={basic:{monthly:0,perMonthYearly:0,yearly:0},individual:{monthly:13.59,perMonthYearly:10.76,yearly:129.16},business:{monthly:17.59,perMonthYearly:13.93,yearly:167.12}};
export const PLAN_LABEL:Record<string,string>={basic:'Basic',individual:'Standard',business:'Business'};
const SYMBOL:Record<string,string>={USD:'US$',AUD:'A$',GBP:'£',EUR:'€',CAD:'C$',NZD:'NZ$'};
export const money=(n:number,cur='USD')=>`${SYMBOL[cur]||cur+' '}${n.toFixed(2)}`;
export type Tier={n:number;pct:number};
const COMMON:Tier[]=[{n:25,pct:60},{n:50,pct:80},{n:100,pct:100},{n:150,pct:135},{n:200,pct:170},{n:300,pct:240}];
export const DEFAULT_TIERS:Record<string,Tier[]>={individual:[{n:10,pct:14.72},...COMMON],business:[{n:10,pct:45},...COMMON]};
export type LivePlan={id:PlanId;name:string;monthly:number;yearly:number;per_month_yearly:number;available:boolean};
const API=()=>import.meta.env.VITE_API_BASE||(import.meta.env.VITE_DEMO_MODE==='true'?'http://127.0.0.1:8000/api/v1':'/api/v1');
/** The price list the administrator keeps in Admin Console > Commercial > Pricing. Re-read each time a page that shows prices opens, so a change shows at once. */
export function useLivePlans(){
  const [d,setD]=useState<{currency:string;plans:LivePlan[];tiers?:Record<string,Tier[]>}|null>(null);
  useEffect(()=>{let on=true;const get=()=>fetch(API()+'/billing/plans?t='+Date.now(),{cache:'no-store'}).then(r=>r.json()).then(x=>on&&x.plans&&setD(x)).catch(()=>{});get();const t=setInterval(get,30000);return()=>{on=false;clearInterval(t)}},[]);
  const tiersOf=(id:string):Tier[]=>d?.tiers?.[id]?.length?d.tiers[id]:(DEFAULT_TIERS[id]||[]);
  /** Price for a plan at a number of people: the listed price is for 100 people, each tier is a percentage of it (Standard and Business each have their own table) (same rounding as the server, in cents). */
  const prices=(id:PlanId,tier=100)=>{const p=d?.plans.find(x=>x.id===id);const base=p?{m:p.monthly,y:p.yearly}:{m:Math.round(PLAN_PRICES[id].monthly*100),y:Math.round(PLAN_PRICES[id].yearly*100)};const pct=tiersOf(id).find(t=>t.n===tier)?.pct??100;const k=(c:number)=>tier===100?c:Math.round(c*pct/100);return {monthly:k(base.m)/100,yearly:k(base.y)/100,perMonthYearly:Math.round(k(base.y)/12)/100}};
  const onSale=(id:PlanId)=>id==='basic'||(d?!!d.plans.find(x=>x.id===id)?.available:true);
  return {currency:d?.currency||'AUD',prices,onSale,tiersOf,loaded:!!d};
}
type PlanDef={id:PlanId;name:string;tag:string;cta:string;popular?:boolean;features:string[]};
const PLANS:PlanDef[]=[
 {id:'basic',name:'Basic',tag:'Free for ever, to get started',cta:'Start for free',features:['Video meetings in the browser: up to 25 people, meetings of up to 70 minutes','Chat, screen sharing, reactions, raise hand and live captions','Meeting recording, saved on the host\u2019s own computer when the meeting ends','Zoom-style phone view: you large, others on the next screens','Receive calls from other iSift users','3 AI meeting summaries a month and 1 booking page','5 new Docs files or whiteboards a day, 100 MB of storage','Transcripts and action items','Community support']},
 {id:'individual',name:'Standard',tag:'For people who meet every day',cta:'Choose Standard',popular:true,features:['Everything in Basic, with meetings of any length and up to the number of people you pick (10 to 300)','Several people share their screen or window at once, with a pointer and pen you can hand over','Watch a YouTube video together, in sync on every device, and share a browser tab with its sound','Meeting recording, open room, co-hosts, mute and remove, waiting room and lock meeting','Commbox: mail, calendar and contacts for all your accounts','Unlimited AI minutes, action items and morning briefings','Unlimited booking pages, like Calendly','Call other iSift users: ring them, they accept, you are in a private room','Schedule Zoom, Teams and Google Meet from one place','5 GB of storage per person and email support']},
 {id:'business',name:'Business',tag:'For teams and companies',cta:'Choose Business',features:['Everything in Standard','A company account with all your people under one plan and one card','Team booking pages: one link that shares bookings across your people, round robin','Team action items: everyone sees and updates actions from teammates’ meetings','Microsoft Entra single sign-on','Switch whole modules on and off for everyone','Audit log, data retention and review rules','Priority support']}];

const FAQ:[string,string][]=[
 ['What does the number of participants change?','It is the most people your meetings can hold at once. Pick the size that fits your biggest meeting. You can move to a bigger or smaller size at any time and only the difference is charged, with unused days credited.'],
 ['Is the price per person in my team?','Prices are per host: the person who starts the meetings. The people they invite join free, even without an account. Business gives your whole company one plan and one card.'],
 ['What do I get free in Basic?','Meetings of up to 25 people for up to 70 minutes, chat, screen sharing, reactions, captions, meeting recording (saved on the host\u2019s own computer when the meeting ends; paid plans store it in the cloud and email the host a download link), and a taste of the AI features.'],
 ['Can I cancel?','Yes, any time. You keep your plan until the end of the period you paid for. If you end it early, the unused time can be refunded once an administrator approves it.'],
 ['How do I pay?','By card through Square. iSift never sees your card number. Yearly plans are about 5% to 20% cheaper than paying monthly.'],
 ['Can I share my screen from a phone?','Phones do not allow websites to share the screen, so on a phone you share photos, PDFs, documents, the whiteboard or a video link. From a laptop you can share the whole screen, one window or one browser tab.']];

const ROWS:[string,string,string,string][]=[
 ['People in a meeting','Up to 25','10 to 300 (you choose)','10 to 300 (you choose)'],
 ['Meeting length','70 minutes','Any length','Any length'],
 ['Chat, reactions, raise hand, captions','Yes','Yes','Yes'],
 ['Several people sharing at once, pointer and pen','No','Yes','Yes'],
 ['Watch a video together','No','Yes','Yes'],
 ['Recording','Yes: saved on the host\u2019s computer at the end of the meeting','Yes: stored in the cloud, download link emailed to the host','Yes: stored in the cloud, download link emailed to the host'],
 ['Waiting room, lock meeting, co-hosts','Basic','Full','Full'],
 ['Open room, Commbox, booking pages','No','Yes','Yes'],
 ['AI summaries and action items','3 a month','Unlimited','Unlimited'],
 ['Storage','100 MB','5 GB per person','5 GB per person'],
 ['Company account and team features','No','No','Yes'],
 ['Single sign-on, audit log, retention rules','No','No','Yes'],
 ['Support','Community','Email','Priority']];

/** One plan card. Paid plans have a participants dropdown that changes the price. */
function PlanCard({p,annual,live,tier,setTier,current,loggedIn,onChoose,compact,h}:{p:PlanDef;annual:boolean;live:ReturnType<typeof useLivePlans>;tier:number;setTier:(n:number)=>void;current?:string;loggedIn?:boolean;onChoose?:()=>void;compact?:boolean;h:'h2'|'h3'}){
  const cur=live.currency;const paid=p.id!=='basic';const pr=live.prices(p.id,paid?tier:100);const price=annual?pr.perMonthYearly:pr.monthly;const H=h;
  return <section className={`pr-card${p.popular?' popular':''}${current===p.id?' current':''}`} aria-label={`${p.name} plan`}>
    {p.popular&&<span className="pr-badge"><Sparkles size={13}/> Most popular</span>}
    <H>{p.id==='business'&&<Building2 size={18}/>} {p.name}</H><p className="pr-tag">{p.tag}</p>
    {paid?<label className="pr-pick"><span>Participants</span><select value={tier} onChange={e=>setTier(parseInt(e.target.value,10))} aria-label={`${p.name}: number of participants`}>{live.tiersOf(p.id).map(t=><option key={t.n} value={t.n}>{t.n} participants</option>)}</select></label>:<div className="pr-pick fixed"><span>Participants</span><b>Up to 25</b></div>}
    <div className="pr-price">{price===0?<><b>{money(0,cur)}</b><small>Free for ever</small></>:<><b>{money(price,cur)}</b><small>per host, per month{annual?`, ${money(pr.yearly,cur)} billed yearly`:', billed monthly'}</small></>}</div>
    {onChoose&&<button type="button" className={p.popular?'primary':'secondary'} disabled={current===p.id&&!paid} onClick={onChoose}>{current===p.id&&!paid?'Your current plan':loggedIn?(p.id==='basic'?'Use Basic':current===p.id?'Change size or billing':`Upgrade to ${p.name}`):p.cta}</button>}
    {!compact&&<ul>{p.features.map(f=><li key={f}><Check size={15}/>{f}</li>)}</ul>}
  </section>;
}
const useTiers=()=>{const [t,setT]=useState<Record<string,number>>({individual:10,business:10});return [t,(id:string)=>(n:number)=>setT(o=>({...o,[id]:n}))] as const};

export function PricingPage({loggedIn,current,onBack,onChoose}:{loggedIn:boolean;current?:string;onBack:()=>void;onChoose:(p:PlanId,period:Period,tier:number)=>void}){
  const [annual,setAnnual]=useState(true);const live=useLivePlans();const [tiers,setTier]=useTiers();
  const save=(()=>{const n=Math.max(0,...PLANS.filter(p=>p.id!=='basic'&&live.onSale(p.id)).map(p=>{const q=live.prices(p.id);return q.monthly>0?Math.round((1-q.yearly/(q.monthly*12))*100):0}));return n})();
  return <div className="pricing">
    <header className="landing-nav"><a className="landing-brand" href="#top" onClick={e=>{e.preventDefault();onBack()}}><span className="brandicon"><Sun size={20}/></span><span><b>iSift</b><small>Make every meeting count</small></span></a>
      <nav className="public-links"><button type="button" className="nav-login" onClick={onBack}><ArrowLeft size={16}/> {loggedIn?'Back to my workspace':'Back to home'}</button></nav></header>
    <main className="pr-main">
      <p className="eyebrow">PRICING</p><h1>Plans that grow with your meetings</h1>
      <p className="pr-sub">Start free. Pick Standard or Business, choose how many people your meetings need, and pay monthly or yearly. Guests you invite always join free.</p>
      <div className="pr-toggle" role="group" aria-label="Billing period"><button type="button" className={!annual?'on':''} onClick={()=>setAnnual(false)}>Monthly</button><button type="button" className={annual?'on':''} onClick={()=>setAnnual(true)}>Yearly{save>0?<em>save about {save}%</em>:null}</button></div>
      <div className="pr-grid">{PLANS.filter(p=>live.onSale(p.id)||current===p.id).map(p=><PlanCard key={p.id} h="h2" p={p} annual={annual} live={live} tier={tiers[p.id]||10} setTier={setTier(p.id)} current={current} loggedIn={loggedIn} onChoose={()=>onChoose(p.id,annual?'yearly':'monthly',p.id==='basic'?100:(tiers[p.id]||10))}/>)}</div>
      <p className="pr-fine">Prices are per host in {live.currency}, taken by card through Square. Standard and Business renew automatically; you can cancel any time and keep the plan until the end of the period you paid for.</p>
      <h2 className="pr-h2">Compare plans</h2>
      <div className="pr-tablewrap"><table className="pr-table"><thead><tr><th></th><th>Basic</th><th>Standard</th><th>Business</th></tr></thead><tbody>{ROWS.map(r=><tr key={r[0]}><th scope="row">{r[0]}</th><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td></tr>)}</tbody></table></div>
      <h2 className="pr-h2">Questions</h2>
      <div className="pr-faq">{FAQ.map(([q,a])=><details key={q}><summary>{q}</summary><p>{a}</p></details>)}</div>
    </main><LegalFooter/></div>;
}

/** Compact live price cards for the home page, with the same participants dropdown. Plans with no active price are not shown. */
export function HomePricing({onChoose}:{onChoose:()=>void}){
  const [annual,setAnnual]=useState(true);const live=useLivePlans();const [tiers,setTier]=useTiers();
  const shown=PLANS.filter(p=>live.onSale(p.id));
  return <section className="landing-section" id="pricing"><p className="eyebrow">PRICING</p><h2>Start free. Pay only when you need more.</h2>
    <div className="pr-toggle" role="group" aria-label="Billing period"><button type="button" className={!annual?'on':''} onClick={()=>setAnnual(false)}>Monthly</button><button type="button" className={annual?'on':''} onClick={()=>setAnnual(true)}>Yearly <em>best value</em></button></div>
    <div className="pr-grid home-pr">{shown.map(p=><PlanCard key={p.id} h="h3" p={p} annual={annual} live={live} tier={tiers[p.id]||10} setTier={setTier(p.id)} compact/>)}</div>
    <p className="pr-more"><button type="button" className="primary" onClick={onChoose}>See plans and features</button></p></section>;
}
