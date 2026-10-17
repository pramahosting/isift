import React,{useEffect,useRef,useState} from 'react';
import {CreditCard,Check,ArrowLeft,ShieldCheck,Trash2} from 'lucide-react';
import {PLAN_LABEL,PLAN_PRICES,money,PlanId,Period} from './Pricing';

declare global{interface Window{Square?:any}}
const loadSdk=(src:string)=>new Promise<void>((res,rej)=>{if(window.Square)return res();const s=document.createElement('script');s.src=src;s.onload=()=>res();s.onerror=()=>rej(new Error('The secure card form could not be loaded. Check your connection and try again.'));document.head.appendChild(s)});

/** Plan and billing: current plan, choose/upgrade, card on file (Square's secure form: iSift never sees the card number), receipts. */
export function BillingPage({request,notify,choice,isAdmin,goPricing,goAdmin,onChanged}:{request:any;notify:(m:string)=>void;choice?:{plan:PlanId;period:Period}|null;isAdmin:boolean;goPricing:()=>void;goAdmin:()=>void;onChanged:()=>void}){
  const [b,setB]=useState<any>(null);const [err,setErr]=useState('');const [busy,setBusy]=useState(false);
  const [plan,setPlan]=useState<PlanId>(choice?.plan||'individual');const [period,setPeriod]=useState<Period>(choice?.period||'yearly');
  const [q,setQ]=useState<any>(null);const [endNow,setEndNow]=useState(false);const [formReady,setFormReady]=useState(false);const [replace,setReplace]=useState(false);const card=useRef<any>(null);
  const load=()=>request('/billing/me').then(setB).catch((e:any)=>setErr(e.message));
  useEffect(()=>{load()},[]);
  useEffect(()=>{if(!b||!b.can_manage||b.plan==='basic'){setQ(null);return}let dead=false;request('/billing/quote',{method:'POST',body:JSON.stringify({plan,period})}).then((d:any)=>!dead&&setQ(d)).catch(()=>!dead&&setQ(null));return()=>{dead=true}},[plan,period,b?.plan,b?.period,b?.period_end]);
  const sq=b?.square;const needForm=!!sq&&b?.can_manage&&(!b.card||replace);
  useEffect(()=>{if(!needForm)return;let dead=false;
    (async()=>{try{await loadSdk(sq.sdk);if(dead)return;const pay=await window.Square.payments(sq.applicationId,sq.locationId);const c=await pay.card();await c.attach('#sq-card');card.current=c;setFormReady(true)}catch(e:any){setErr(e.message||'The card form could not start.')}})();
    return()=>{dead=true;try{card.current?.destroy?.()}catch{};card.current=null;setFormReady(false)}},[needForm]);
  const run=async(f:()=>Promise<any>,ok:string)=>{setBusy(true);setErr('');try{const r=await f();notify(ok);await load();onChanged();return r}catch(e:any){setErr(e.message||'Something went wrong.')}finally{setBusy(false)}};
  const pay=()=>run(async()=>{
    if(needForm){const t=await card.current.tokenize();if(t.status!=='OK')throw new Error(t.errors?.[0]?.message||'Check the card details.');await request('/billing/card',{method:'POST',body:JSON.stringify({source_id:t.token})});setReplace(false)}
    return request('/billing/subscribe',{method:'POST',body:JSON.stringify({plan,period,immediate:plan==='basic'&&endNow})})},plan==='basic'?(endNow?'Your plan has ended. A refund request was sent for approval.':'Your plan will move to Basic when the paid period ends.'):q?.kind==='change'?(q.refund_cents>0?'Plan changed. A refund of the extra credit was sent for approval.':'Plan changed. Only the difference was charged.'):`You are now on the ${PLAN_LABEL[plan]} plan.`);
  if(!b)return err?<p className="syncerr" role="alert">{err}</p>:<p className="muted">Loading…</p>;
  const cur=b.currency;const c2=(n:number)=>money(n/100,cur);const changing=q?.kind==='change';const pr=PLAN_PRICES[plan];const amt=period==='yearly'?pr.yearly:pr.monthly;const same=b.plan===plan&&b.status==='active'&&b.period_end;
  return <div className="bill">
    <section className="panel"><div className="panelhead"><h2>Your plan</h2><span className={`badge ${b.status==='past_due'?'red':'green'}`}>{b.status==='past_due'?'Payment failed':'Active'}</span></div>
      <p className="bill-now"><b>{b.plan_name}</b>{b.company&&<> for {b.company}</>}{b.plan!=='basic'&&b.period_end&&<> · {b.auto_renew?'renews':'ends'} on {b.period_end}</>}</p>
      {b.status==='past_due'&&<p className="syncerr" role="alert">Your last payment failed ({b.last_error}).{b.next_attempt_on?` We will try again on ${b.next_attempt_on}.`:' We will not retry automatically.'} Update your card below to keep your plan.</p>}
      {!b.can_manage&&<p className="hint">Only the company owner or an administrator can change the plan or card.</p>}</section>
    {b.can_manage&&<section className="panel"><div className="panelhead"><h2>{b.plan==='basic'?'Upgrade your plan':'Change plan'}</h2><button type="button" className="textbtn" onClick={goPricing}><ArrowLeft size={14}/> Compare plans</button></div>
      <div className="bill-plans" role="radiogroup" aria-label="Plan">{(['basic','individual','business'] as PlanId[]).map(id=><label key={id} className={`bill-plan${plan===id?' on':''}`}><input type="radio" name="plan" checked={plan===id} onChange={()=>setPlan(id)}/><b>{PLAN_LABEL[id]}</b><span>{id==='basic'?'Free':money(period==='yearly'?PLAN_PRICES[id].perMonthYearly:PLAN_PRICES[id].monthly,cur)+' / month'}</span>{b.plan===id&&<em>Current</em>}</label>)}</div>
      {plan!=='basic'&&<div className="pr-toggle" role="group" aria-label="Billing period"><button type="button" className={period==='monthly'?'on':''} onClick={()=>setPeriod('monthly')}>Monthly</button><button type="button" className={period==='yearly'?'on':''} onClick={()=>setPeriod('yearly')}>Yearly</button></div>}
      {plan==='basic'?<><p className="hint">Moving to Basic stops automatic renewal. By default you keep your current plan until the end of the period you have paid for.</p>{q&&b.plan!=='basic'&&<label className="chk"><input type="checkbox" checked={endNow} onChange={e=>setEndNow(e.target.checked)}/> End my plan today and ask for a refund of the unused time (about {c2(q.refund_cents)}). An administrator must approve the refund.</label>}</>:<>
        {changing&&<div className="bill-quote" role="status"><div><span>New plan ({period})</span><b>{c2(q.new_price_cents)}</b></div><div><span>Credit for unused time on {b.plan_name}</span><b>− {c2(q.credit_cents)}</b></div>{q.charge_cents>0?<div className="due"><span>Difference to pay today</span><b>{c2(q.charge_cents)}</b></div>:<div className="due"><span>Nothing to pay today. Credit left over (refund on approval)</span><b>{c2(q.refund_cents)}</b></div>}<small>The new plan starts today and renews on {q.new_period_end}.{q.refund_cents>0?' The leftover credit is only returned to your card if an administrator approves the refund request.':''}</small></div>}
        {!changing&&<p className="bill-total">Total today: <b>{money(amt,cur)}</b> <small>({period==='yearly'?'one year':'one month'}, renews automatically, per user in {cur})</small></p>}
        {!sq&&<div className="syncerr" role="alert">Card payments are not switched on yet. {isAdmin?<button type="button" className="textbtn inline" onClick={goAdmin}>Set up Square in Admin settings</button>:'Ask your administrator to set up Square in Admin settings > Payments.'}</div>}
        {sq&&b.card&&!replace&&<p className="bill-card"><CreditCard size={16}/> {b.card.brand} ending {b.card.last4} · expires {b.card.exp_month}/{b.card.exp_year} <button type="button" className="textbtn" onClick={()=>setReplace(true)}>Use another card</button><button type="button" className="textbtn" onClick={()=>run(()=>request('/billing/card',{method:'DELETE'}),'Card removed.')}><Trash2 size={13}/> Remove</button></p>}
        {needForm&&<><div id="sq-card" className="sq-card" aria-label="Card details"/>{!formReady&&!err&&<p className="muted">Loading the secure card form…</p>}<p className="muted"><ShieldCheck size={13}/> Card details go straight to Square. iSift only keeps the card type and last 4 digits.</p></>}</>}
      {err&&<p className="syncerr" role="alert">{err}</p>}
      <button type="button" className="primary" disabled={busy||!!same&&b.period===period&&b.auto_renew||plan!=='basic'&&(!sq||(needForm&&!formReady))} onClick={pay}><Check size={16}/> {plan==='basic'?(endNow?'End plan and request refund':'Move to Basic'):same?'Keep renewing':b.plan==='basic'?`Pay ${money(amt,cur)} and upgrade`:changing?(q.charge_cents>0?`Pay ${c2(q.charge_cents)} difference and switch`:'Switch plan'):`Pay ${money(amt,cur)} and switch`}</button></section>}
    {b.charges.length>0&&<section className="panel"><div className="panelhead"><h2>Payments</h2></div><table className="modtable"><thead><tr><th>Date</th><th>Plan</th><th>Amount</th><th>Result</th></tr></thead><tbody>{b.charges.map((c:any)=><tr key={c.id}><td>{(c.settled||'').slice(0,10)}</td><td>{PLAN_LABEL[c.plan]} ({c.period})</td><td>{money(c.amount_cents/100,cur)}</td><td>{c.status==='paid'?<>Paid {c.receipt_url&&<a href={c.receipt_url} target="_blank" rel="noreferrer">receipt</a>}</>:<span className="syncerr">Failed: {c.error}</span>}</td></tr>)}</tbody></table></section>}
    {b.refunds?.length>0&&<section className="panel"><div className="panelhead"><h2>Refund requests</h2></div><table className="modtable"><thead><tr><th>Date</th><th>Reason</th><th>Amount</th><th>Status</th></tr></thead><tbody>{b.refunds.map((x:any)=><tr key={x.id}><td>{(x.created||'').slice(0,10)}</td><td>{x.reason}</td><td>{c2(x.amount_cents)}</td><td>{x.status==='pending'?'Waiting for approval':x.status==='approved'?`Approved: ${c2(x.paid_back_cents)} returned to your card`:x.status==='partial'?'Being processed':`Declined${x.note?': '+x.note:''}`}</td></tr>)}</tbody></table></section>}
  </div>;
}


/** Administrator: refund requests wait here until someone approves (money goes back to the card through Square) or declines. */
export function RefundsPanel({request}:{request:any}){
  const [rows,setRows]=useState<any[]>([]);const [msg,setMsg]=useState('');const [err,setErr]=useState('');const [busy,setBusy]=useState('');const [amt,setAmt]=useState<Record<string,string>>({});const [note,setNote]=useState<Record<string,string>>({});
  const load=()=>request('/admin/billing/refunds').then((d:any)=>setRows(d.refunds)).catch((e:any)=>setErr(e.message));
  useEffect(()=>{load()},[]);
  const m=(n:number,c:string)=>`${(n/100).toFixed(2)} ${c||''}`;
  const act=async(x:any,what:'approve'|'decline')=>{
    if(what==='approve'&&!window.confirm(`Send ${amt[x.id]||m(x.amount_cents,x.currency)} back to the customer's card? This moves real money and cannot be undone.`))return;
    setBusy(x.id);setErr('');setMsg('');
    try{const cents=amt[x.id]?Math.round(parseFloat(amt[x.id])*100):undefined;await request(`/admin/billing/refunds/${x.id}/${what}`,{method:'POST',body:JSON.stringify({amount_cents:cents,note:note[x.id]||''})});setMsg(what==='approve'?'Refund sent to Square.':'Request declined.');await load()}catch(e:any){setErr(e.message);await load()}finally{setBusy('')}};
  const open=rows.filter(r=>r.status==='pending'||r.status==='partial');const done=rows.filter(r=>!open.includes(r));
  return <section className="panel"><div className="panelhead"><h2>Refund requests</h2><span className="muted">{open.length} waiting</span></div>
    <p className="hint">Created when someone changes to a cheaper plan or ends a plan early. Nothing is refunded until you approve it here. You can refund less than requested.</p>
    {err&&<p className="syncerr" role="alert">{err}</p>}{msg&&<p className="okmsg" role="status">{msg}</p>}
    {open.length===0&&<p className="muted">No refund requests are waiting.</p>}
    {open.map(x=><div className="refund-row" key={x.id}><div className="grow"><b>{x.account}</b> asks for <b>{m(x.amount_cents,x.currency)}</b><small>{x.reason} · {(x.created||'').slice(0,10)} · can still be returned to the card: {m(x.refundable_cents,x.currency)}{x.status==='partial'?` · ${m(x.paid_back_cents,x.currency)} already sent`:''}</small></div>
      <input aria-label="Amount to refund" placeholder={(x.amount_cents/100).toFixed(2)} value={amt[x.id]||''} onChange={e=>setAmt({...amt,[x.id]:e.target.value})} inputMode="decimal" style={{width:90}}/>
      <input aria-label="Note to the customer" placeholder="Note (optional)" value={note[x.id]||''} onChange={e=>setNote({...note,[x.id]:e.target.value})}/>
      <button className="primary" disabled={busy===x.id} onClick={()=>act(x,'approve')}>Approve and refund</button>{x.status==='pending'&&<button className="secondary danger" disabled={busy===x.id} onClick={()=>act(x,'decline')}>Decline</button>}</div>)}
    {done.length>0&&<details><summary>Decided ({done.length})</summary><table className="modtable"><tbody>{done.slice(0,30).map(x=><tr key={x.id}><td>{(x.decided||x.created||'').slice(0,10)}</td><td>{x.account}</td><td>{m(x.amount_cents,x.currency)}</td><td>{x.status==='approved'?`Approved, ${m(x.paid_back_cents,x.currency)} sent by ${x.decided_by}`:`Declined by ${x.decided_by}`}{x.note?` · ${x.note}`:''}</td></tr>)}</tbody></table></details>}
  </section>}
