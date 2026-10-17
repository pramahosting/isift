import React,{useEffect,useState} from 'react';
import {Check,Sun,ArrowLeft,Sparkles,Building2} from 'lucide-react';
import {LegalFooter} from './Legal';

export type PlanId='basic'|'individual'|'business';
export type Period='monthly'|'yearly';
// Zoom list prices (Pro $16.99 / $14.16, Business $21.99 / $18.33 per month) less 20%. Must match PLANS in backend/app/services/billing.py.
export const PLAN_PRICES:Record<PlanId,{monthly:number;perMonthYearly:number;yearly:number}>={basic:{monthly:0,perMonthYearly:0,yearly:0},individual:{monthly:13.59,perMonthYearly:11.33,yearly:135.96},business:{monthly:17.59,perMonthYearly:14.66,yearly:175.92}};
export const PLAN_LABEL:Record<string,string>={basic:'Basic',individual:'Individual',business:'Business'};
const SYMBOL:Record<string,string>={USD:'US$',AUD:'A$',GBP:'£',EUR:'€',CAD:'C$',NZD:'NZ$'};
export const money=(n:number,cur='USD')=>`${SYMBOL[cur]||cur+' '}${n.toFixed(2)}`;
const PLANS:{id:PlanId;name:string;tag:string;cta:string;popular?:boolean;features:string[]}[]=[
 {id:'basic',name:'Basic',tag:'For individuals getting started',cta:'Start for free',features:['Video meetings in the browser with chat and screen sharing','Shared docs and a whiteboard','Commbox: mail, calendar and contacts','Transcripts and action items','Community support']},
 {id:'individual',name:'Individual',tag:'For people who meet every day',cta:'Choose Individual',popular:true,features:['Everything in Basic','AI minutes, action items and morning briefings','Booking pages you share by email, like Calendly','Meeting recording and a host’s full controls: co-hosts, mute, remove, who can unmute','Schedule Zoom, Teams and Google Meet from one place','Email support']},
 {id:'business',name:'Business',tag:'For teams and companies',cta:'Choose Business',features:['Everything in Individual','A company account with all your people under one plan and one card','Microsoft Entra single sign-on','Switch whole modules on and off for everyone','Audit log, data retention and review rules','Priority support']}];

export function PricingPage({loggedIn,current,onBack,onChoose}:{loggedIn:boolean;current?:string;onBack:()=>void;onChoose:(p:PlanId,period:Period)=>void}){
  const [annual,setAnnual]=useState(true);const [cur,setCur]=useState('AUD');
  useEffect(()=>{fetch((import.meta.env.VITE_API_BASE||(import.meta.env.VITE_DEMO_MODE==='true'?'http://127.0.0.1:8000/api/v1':'/api/v1'))+'/billing/plans').then(r=>r.json()).then(d=>d.currency&&setCur(d.currency)).catch(()=>{})},[]);
  return <div className="pricing">
    <header className="landing-nav"><a className="landing-brand" href="#top" onClick={e=>{e.preventDefault();onBack()}}><span className="brandicon"><Sun size={20}/></span><span><b>iSift</b><small>Make every meeting count</small></span></a>
      <nav className="public-links"><button type="button" className="nav-login" onClick={onBack}><ArrowLeft size={16}/> {loggedIn?'Back to my workspace':'Back to home'}</button></nav></header>
    <main className="pr-main">
      <p className="eyebrow">PRICING</p><h1>Plans that grow with your meetings</h1>
      <p className="pr-sub">Start with Basic, free for ever. Move to Individual for AI minutes, booking pages and full host controls, or Business for a whole company.</p>
      <div className="pr-toggle" role="group" aria-label="Billing period"><button type="button" className={!annual?'on':''} onClick={()=>setAnnual(false)}>Monthly</button><button type="button" className={annual?'on':''} onClick={()=>setAnnual(true)}>Yearly <em>save about 17%</em></button></div>
      <div className="pr-grid">{PLANS.map(p=>{const pr=PLAN_PRICES[p.id];const price=annual?pr.perMonthYearly:pr.monthly;
        return <section key={p.id} className={`pr-card${p.popular?' popular':''}${current===p.id?' current':''}`} aria-label={`${p.name} plan`}>
          {p.popular&&<span className="pr-badge"><Sparkles size={13}/> Most popular</span>}
          <h2>{p.id==='business'&&<Building2 size={18}/>} {p.name}</h2><p className="pr-tag">{p.tag}</p>
          <div className="pr-price">{price===0?<><b>{money(0,cur)}</b><small>Free for ever</small></>:<><b>{money(price,cur)}</b><small>per user, per month{annual?`, ${money(pr.yearly,cur)} billed yearly`:''}</small></>}</div>
          <button type="button" className={p.popular?'primary':'secondary'} disabled={current===p.id} onClick={()=>onChoose(p.id,annual?'yearly':'monthly')}>{current===p.id?'Your current plan':loggedIn?(p.id==='basic'?'Use Basic':`Upgrade to ${p.name}`):p.cta}</button>
          <ul>{p.features.map(f=><li key={f}><Check size={15}/>{f}</li>)}</ul></section>})}</div>
      <p className="pr-fine">Prices are per user in {cur}, taken by card through Square. Individual and Business renew automatically; you can cancel any time and keep the plan until the end of the period you paid for.</p>
    </main><LegalFooter/></div>;
}
