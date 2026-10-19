import React,{useEffect,useState} from 'react';
import {Check,Sun,ArrowLeft,Sparkles,Building2} from 'lucide-react';
import {LegalFooter} from './Legal';

export type PlanId='basic'|'individual'|'business';
export type Period='monthly'|'yearly';
// Monthly prices; yearly = the earlier yearly price (135.96 / 175.92) less a further 5%. Must match PLANS in backend/app/services/billing.py.
export const PLAN_PRICES:Record<PlanId,{monthly:number;perMonthYearly:number;yearly:number}>={basic:{monthly:0,perMonthYearly:0,yearly:0},individual:{monthly:13.59,perMonthYearly:10.76,yearly:129.16},business:{monthly:17.59,perMonthYearly:13.93,yearly:167.12}};
export const PLAN_LABEL:Record<string,string>={basic:'Basic',individual:'Individual',business:'Business'};
const SYMBOL:Record<string,string>={USD:'US$',AUD:'A$',GBP:'£',EUR:'€',CAD:'C$',NZD:'NZ$'};
export const money=(n:number,cur='USD')=>`${SYMBOL[cur]||cur+' '}${n.toFixed(2)}`;
export type LivePlan={id:PlanId;name:string;monthly:number;yearly:number;per_month_yearly:number;available:boolean};
const API=()=>import.meta.env.VITE_API_BASE||(import.meta.env.VITE_DEMO_MODE==='true'?'http://127.0.0.1:8000/api/v1':'/api/v1');
/** The price list the administrator keeps in Admin settings > Pricing. Re-read each time a page that shows prices opens, so a change shows at once. */
export function useLivePlans(){
  const [d,setD]=useState<{currency:string;plans:LivePlan[]}|null>(null);
  useEffect(()=>{let on=true;const get=()=>fetch(API()+'/billing/plans?t='+Date.now(),{cache:'no-store'}).then(r=>r.json()).then(x=>on&&x.plans&&setD(x)).catch(()=>{});get();const t=setInterval(get,30000);return()=>{on=false;clearInterval(t)}},[]);
  const prices=(id:PlanId)=>{const p=d?.plans.find(x=>x.id===id);return p?{monthly:p.monthly/100,perMonthYearly:p.per_month_yearly/100,yearly:p.yearly/100}:PLAN_PRICES[id]};
  const onSale=(id:PlanId)=>id==='basic'||(d?!!d.plans.find(x=>x.id===id)?.available:true);
  return {currency:d?.currency||'AUD',prices,onSale,loaded:!!d};
}
const PLANS:{id:PlanId;name:string;tag:string;cta:string;popular?:boolean;features:string[]}[]=[
 {id:'basic',name:'Basic',tag:'For individuals getting started',cta:'Start for free',features:['Video meetings in the browser with chat and screen sharing','Meetings of up to 70 minutes (a reminder appears 10 minutes before the end)','Receive calls from other iSift users (placing calls is in the paid plans)','3 AI minutes summaries a month and 1 booking page, to try the best parts','No meeting recording, no open room and no Commbox','5 new Docs files or whiteboards a day, PDFs of up to 5 pages','100 MB of storage and up to 20 hours of hosted meetings a month','Transcripts and action items','Community support']},
 {id:'individual',name:'Individual',tag:'For people who meet every day',cta:'Choose Individual',popular:true,features:['Everything in Basic, with meetings of any length, up to 300 hours of hosted meetings a month and 5 GB of storage per person','Open room: anyone with the link can join any time','Commbox: mail, calendar and contacts for all your accounts','Unlimited Docs files and whiteboards, PDFs of any length','Unlimited AI minutes, action items and morning briefings','Unlimited booking pages you share by email, like Calendly','Call other iSift users: ring them, they accept, you are in a private room','Meeting recording (saved on your computer, or in the cloud) and a host’s full controls: co-hosts, mute, remove, who can unmute','Schedule Zoom, Teams and Google Meet from one place','Email support']},
 {id:'business',name:'Business',tag:'For teams and companies',cta:'Choose Business',features:['Everything in Individual','A company account with all your people under one plan and one card','Team booking pages: one link that shares bookings across your people, round robin','Team action items: everyone sees and updates actions from teammates’ meetings','Microsoft Entra single sign-on','Switch whole modules on and off for everyone','Audit log, data retention and review rules','Priority support']}];

export function PricingPage({loggedIn,current,onBack,onChoose}:{loggedIn:boolean;current?:string;onBack:()=>void;onChoose:(p:PlanId,period:Period)=>void}){
  const [annual,setAnnual]=useState(true);const live=useLivePlans();const cur=live.currency;
  return <div className="pricing">
    <header className="landing-nav"><a className="landing-brand" href="#top" onClick={e=>{e.preventDefault();onBack()}}><span className="brandicon"><Sun size={20}/></span><span><b>iSift</b><small>Make every meeting count</small></span></a>
      <nav className="public-links"><button type="button" className="nav-login" onClick={onBack}><ArrowLeft size={16}/> {loggedIn?'Back to my workspace':'Back to home'}</button></nav></header>
    <main className="pr-main">
      <p className="eyebrow">PRICING</p><h1>Plans that grow with your meetings</h1>
      <p className="pr-sub">Start with Basic, free for ever. Move to Individual for AI minutes, booking pages and full host controls, or Business for a whole company.</p>
      <div className="pr-toggle" role="group" aria-label="Billing period"><button type="button" className={!annual?'on':''} onClick={()=>setAnnual(false)}>Monthly</button><button type="button" className={annual?'on':''} onClick={()=>setAnnual(true)}>Yearly{(()=>{const n=Math.max(0,...PLANS.filter(p=>p.id!=='basic'&&live.onSale(p.id)).map(p=>{const q=live.prices(p.id);return q.monthly>0?Math.round((1-q.yearly/(q.monthly*12))*100):0}));return n>0?<em>save about {n}%</em>:null})()}</button></div>
      <div className="pr-grid">{PLANS.filter(p=>live.onSale(p.id)||current===p.id).map(p=>{const pr=live.prices(p.id);const price=annual?pr.perMonthYearly:pr.monthly;
        return <section key={p.id} className={`pr-card${p.popular?' popular':''}${current===p.id?' current':''}`} aria-label={`${p.name} plan`}>
          {p.popular&&<span className="pr-badge"><Sparkles size={13}/> Most popular</span>}
          <h2>{p.id==='business'&&<Building2 size={18}/>} {p.name}</h2><p className="pr-tag">{p.tag}</p>
          <div className="pr-price">{price===0?<><b>{money(0,cur)}</b><small>Free for ever</small></>:<><b>{money(price,cur)}</b><small>per user, per month{annual?`, ${money(pr.yearly,cur)} billed yearly`:''}</small></>}</div>
          <button type="button" className={p.popular?'primary':'secondary'} disabled={current===p.id} onClick={()=>onChoose(p.id,annual?'yearly':'monthly')}>{current===p.id?'Your current plan':loggedIn?(p.id==='basic'?'Use Basic':`Upgrade to ${p.name}`):p.cta}</button>
          <ul>{p.features.map(f=><li key={f}><Check size={15}/>{f}</li>)}</ul></section>})}</div>
      <p className="pr-fine">Prices are per user in {cur}, taken by card through Square. Individual and Business renew automatically; you can cancel any time and keep the plan until the end of the period you paid for.</p>
    </main><LegalFooter/></div>;
}

/** Compact live price cards for the home page. Plans with no active price are not shown. */
export function HomePricing({onChoose}:{onChoose:()=>void}){
  const [annual,setAnnual]=useState(true);const live=useLivePlans();const cur=live.currency;
  const shown=PLANS.filter(p=>live.onSale(p.id));
  return <section className="landing-section" id="pricing"><p className="eyebrow">PRICING</p><h2>Start free. Pay only when you need more.</h2>
    <div className="pr-toggle" role="group" aria-label="Billing period"><button type="button" className={!annual?'on':''} onClick={()=>setAnnual(false)}>Monthly</button><button type="button" className={annual?'on':''} onClick={()=>setAnnual(true)}>Yearly <em>best value</em></button></div>
    <div className="pr-grid home-pr">{shown.map(p=>{const pr=live.prices(p.id);const price=annual?pr.perMonthYearly:pr.monthly;
      return <section key={p.id} className={`pr-card${p.popular?' popular':''}`} aria-label={`${p.name} plan`}>{p.popular&&<span className="pr-badge"><Sparkles size={13}/> Most popular</span>}
        <h3>{p.name}</h3><p className="pr-tag">{p.tag}</p>
        <div className="pr-price">{price===0?<><b>{money(0,cur)}</b><small>Free for ever</small></>:<><b>{money(price,cur)}</b><small>per user, per month{annual?`, ${money(pr.yearly,cur)} billed yearly`:''}</small></>}</div></section>})}</div>
    <p className="pr-more"><button type="button" className="primary" onClick={onChoose}>See plans and features</button></p></section>;
}
