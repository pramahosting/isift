import React,{useEffect,useRef,useState} from 'react';
import {CreditCard,Check,ArrowLeft,ShieldCheck,Trash2,X,Lock} from 'lucide-react';
import {PLAN_LABEL,PLAN_PRICES,money,PlanId,Period} from './Pricing';

declare global{interface Window{Square?:any}}
const loadSdk=(src:string)=>new Promise<void>((res,rej)=>{if(window.Square)return res();const s=document.createElement('script');s.src=src;s.onload=()=>res();s.onerror=()=>rej(new Error('The secure card form could not be loaded. Check your connection and try again.'));document.head.appendChild(s)});

/** Plan and billing: current plan, choose/upgrade, card on file (Square's secure form: iSift never sees the card number), receipts. */
export function BillingPage({request,notify,choice,isAdmin,goPricing,goAdmin,onChanged}:{request:any;notify:(m:string)=>void;choice?:{plan:PlanId;period:Period;tier?:number}|null;isAdmin:boolean;goPricing:()=>void;goAdmin:()=>void;onChanged:()=>void}){
  const [b,setB]=useState<any>(null);const [err,setErr]=useState('');const [busy,setBusy]=useState(false);
  const [tier,setTier]=useState<number>(choice?.tier||0);const [plan,setPlan]=useState<PlanId>(choice?.plan||'individual');const [period,setPeriod]=useState<Period>(choice?.period||'yearly');
  const [q,setQ]=useState<any>(null);const [endNow,setEndNow]=useState(false);const [replace,setReplace]=useState(false);const [payOpen,setPayOpen]=useState(false);
  const [recurring,setRecurring]=useState(false);const [rmode,setRmode]=useState<'months'|'date'>('months');const [rmonths,setRmonths]=useState('12');const [rdate,setRdate]=useState('');
  const load=()=>request('/billing/me').then((d:any)=>{setB(d);setTier(t=>t||d.tier||100)}).catch((e:any)=>setErr(e.message));
  useEffect(()=>{load()},[]);
  useEffect(()=>{if(!b||!b.can_manage||b.plan==='basic'){setQ(null);return}let dead=false;request('/billing/quote',{method:'POST',body:JSON.stringify({plan,period,tier:tier||100})}).then((d:any)=>!dead&&setQ(d)).catch(()=>!dead&&setQ(null));return()=>{dead=true}},[plan,period,tier,b?.plan,b?.period,b?.tier,b?.period_end]);
  const sq=b?.square;const needForm=!!sq&&b?.can_manage&&(!b.card||replace);
  const run=async(f:()=>Promise<any>,ok:string)=>{setBusy(true);setErr('');try{const r=await f();notify(ok);await load();onChanged();return r}catch(e:any){setErr(e.message||'Something went wrong.')}finally{setBusy(false)}};
  const terms=()=>period==='monthly'&&plan!=='basic'?{recurring,...(recurring?(rmode==='months'?{months:parseInt(rmonths,10)||0}:{end_date:rdate}):{})}:{};
  const termsErr=()=>period==='monthly'&&plan!=='basic'&&recurring?(rmode==='months'?((parseInt(rmonths,10)||0)<1||(parseInt(rmonths,10)||0)>60?'Enter between 1 and 60 months.':''):(!rdate?'Choose the date the payments should stop.':rdate<=new Date().toISOString().slice(0,10)?'The end date must be in the future.':'')):'';
  const pay=(tok?:()=>Promise<string>)=>run(async()=>{
    if(tok){const t=await tok();await request('/billing/card',{method:'POST',body:JSON.stringify({source_id:t})});setReplace(false)}
    const r=await request('/billing/subscribe',{method:'POST',body:JSON.stringify({plan,period,tier:tier||100,immediate:plan==='basic'&&endNow,...terms()})});setPayOpen(false);return r},plan==='basic'?(endNow?'Your plan has ended. A refund request was sent for approval.':'Your plan will move to Basic when the paid period ends.'):q?.kind==='change'?(q.refund_cents>0?'Plan changed. A refund of the extra credit was sent for approval.':'Plan changed. Only the difference was charged.'):`You are now on the ${PLAN_LABEL[plan]} plan.`);
  if(!b)return err?<p className="syncerr" role="alert">{err}</p>:<p className="muted">Loading…</p>;
  const cur=b.currency;const c2=(n:number)=>money(n/100,cur);const changing=q?.kind==='change';const tp=(b.tiers||[]).find((t:any)=>t.n===(tier||100))?.pct??100;const sc=(c:number)=>(tier||100)===100?c:Math.round(c*tp/100);const lp=(id:string)=>{const x=b.plans?.find((y:any)=>y.id===id);return x?{monthly:sc(x.monthly)/100,perMonthYearly:Math.round(sc(x.yearly)/12)/100,yearly:sc(x.yearly)/100}:PLAN_PRICES[id as PlanId]};const onSale=(id:string)=>id==='basic'||id===b.plan||!!b.plans?.find((y:any)=>y.id===id)?.available;const pr=lp(plan);const amt=period==='yearly'?pr.yearly:pr.monthly;const same=b.plan===plan&&(b.tier||100)===(tier||100)&&b.status==='active'&&b.period_end;const dueCents=changing?q.charge_cents:Math.round(amt*100);
  return <div className="bill">
    <section className="panel"><div className="panelhead"><h2>Your plan</h2><span className={`badge ${b.status==='past_due'?'red':'green'}`}>{b.status==='past_due'?'Payment failed':'Active'}</span></div>
      <p className="bill-now"><b>{b.plan_name}</b>{b.plan!=='basic'&&<> · up to {b.tier||100} participants</>}{b.company&&<> for {b.company}</>}{b.plan!=='basic'&&b.period_end&&<> · {b.auto_renew?'renews':'ends'} on {b.period_end}{b.auto_renew&&b.ends_on?`, payments stop after ${b.ends_on}`:''}</>}</p>
      {b.status==='past_due'&&<p className="syncerr" role="alert">Your last payment failed ({b.last_error}).{b.next_attempt_on?` We will try again on ${b.next_attempt_on}.`:' We will not retry automatically.'} Update your card below to keep your plan.</p>}
      {!b.can_manage&&<p className="hint">Only the company owner or an administrator can change the plan or card.</p>}</section>
    {b.can_manage&&<section className="panel"><div className="panelhead"><h2>{b.plan==='basic'?'Upgrade your plan':'Change plan'}</h2><button type="button" className="textbtn" onClick={goPricing}><ArrowLeft size={14}/> Compare plans</button></div>
      <div className="bill-plans" role="radiogroup" aria-label="Plan">{(['basic','individual','business'] as PlanId[]).filter(onSale).map(id=><label key={id} className={`bill-plan${plan===id?' on':''}`}><input type="radio" name="plan" checked={plan===id} onChange={()=>setPlan(id)}/><b>{PLAN_LABEL[id]}</b><span>{id==='basic'?'Free':money(period==='yearly'?lp(id).perMonthYearly:lp(id).monthly,cur)+' / month'}</span>{b.plan===id&&<em>Current</em>}</label>)}</div>
      {plan!=='basic'&&<label className="bill-tier"><span>Participants</span><select value={tier||100} onChange={e=>setTier(parseInt(e.target.value,10))} aria-label="Number of participants">{(b.tiers||[{n:100}]).map((t:any)=><option key={t.n} value={t.n}>{t.n} participants</option>)}</select></label>}
      {plan!=='basic'&&<div className="pr-toggle" role="group" aria-label="Billing period"><button type="button" className={period==='monthly'?'on':''} onClick={()=>setPeriod('monthly')}>Monthly</button><button type="button" className={period==='yearly'?'on':''} onClick={()=>setPeriod('yearly')}>Yearly</button></div>}
      {plan==='basic'?<><p className="hint">Moving to Basic stops automatic renewal. By default you keep your current plan until the end of the period you have paid for.</p>{q&&b.plan!=='basic'&&<label className="chk"><input type="checkbox" checked={endNow} onChange={e=>setEndNow(e.target.checked)}/> End my plan today and ask for a refund of the unused time (about {c2(q.refund_cents)}). An administrator must approve the refund.</label>}</>:<>
        {changing&&<div className="bill-quote" role="status"><div><span>New plan ({period})</span><b>{c2(q.new_price_cents)}</b></div><div><span>Credit for unused time on {b.plan_name}</span><b>− {c2(q.credit_cents)}</b></div>{q.charge_cents>0?<div className="due"><span>Difference to pay today</span><b>{c2(q.charge_cents)}</b></div>:<div className="due"><span>Nothing to pay today. Credit left over (refund on approval)</span><b>{c2(q.refund_cents)}</b></div>}<small>The new plan starts today and renews on {q.new_period_end}.{q.refund_cents>0?' The leftover credit is only returned to your card if an administrator approves the refund request.':''}</small></div>}
        {period==='monthly'&&<fieldset className="bill-rec"><label className="chk"><input type="checkbox" checked={recurring} onChange={e=>setRecurring(e.target.checked)}/> Recurring: charge my card every month</label>
          {recurring?<div className="bill-rec-opts"><label className="chk"><input type="radio" name="rmode" checked={rmode==='months'} onChange={()=>setRmode('months')}/> For <input type="number" min={1} max={60} value={rmonths} onChange={e=>{setRmonths(e.target.value);setRmode('months')}} aria-label="Number of months" className="bill-rec-n"/> months</label>
            <label className="chk"><input type="radio" name="rmode" checked={rmode==='date'} onChange={()=>setRmode('date')}/> Until <input type="date" value={rdate} min={new Date(Date.now()+864e5).toISOString().slice(0,10)} onChange={e=>{setRdate(e.target.value);setRmode('date')}} aria-label="Last day of payments"/></label>
            <small className="muted">Payments stop on their own after that. You can also stop any time.</small></div>:<small className="muted">Not recurring: you pay for one month only and the plan then returns to Basic.</small>}</fieldset>}
        {!changing&&<p className="bill-total">Total today: <b>{money(amt,cur)}</b> <small>({period==='yearly'?'one year, renews automatically':recurring?(rmode==='months'?`one month, repeats for ${rmonths||'?'} months`:`one month, repeats until ${rdate||'the chosen date'}`):'one month, no automatic renewal'}, per user in {cur})</small></p>}
        {!sq&&<div className="syncerr" role="alert">Card payments are not switched on yet. {isAdmin?<button type="button" className="textbtn inline" onClick={goAdmin}>Set up Square in Admin Console</button>:'Ask your administrator to set up Square in Admin Console > Payments.'}</div>}
        {sq&&b.card&&!replace&&<p className="bill-card"><CreditCard size={16}/> {b.card.brand} ending {b.card.last4} · expires {b.card.exp_month}/{b.card.exp_year} <button type="button" className="textbtn" onClick={()=>setReplace(true)}>Use another card</button><button type="button" className="textbtn" onClick={()=>run(()=>request('/billing/card',{method:'DELETE'}),'Card removed.')}><Trash2 size={13}/> Remove</button></p>}
</>}
      {err&&!payOpen&&<p className="syncerr" role="alert">{err}</p>}
      <button type="button" className="primary" disabled={busy||!!same&&b.period===period&&b.auto_renew||plan!=='basic'&&!sq} onClick={()=>{const te=termsErr();if(te){setErr(te);return}setErr('');if(plan!=='basic'&&!same&&(needForm||dueCents>0))setPayOpen(true);else pay()}}><Check size={16}/> {plan==='basic'?(endNow?'End plan and request refund':'Move to Basic'):same?'Keep renewing':b.plan==='basic'?`Pay ${money(amt,cur)} and upgrade`:changing?(q.charge_cents>0?`Pay ${c2(q.charge_cents)} difference and switch`:'Switch plan'):`Pay ${money(amt,cur)} and switch`}</button></section>}
    {payOpen&&sq&&<PayDialog sq={sq} needForm={needForm} card={b.card} title={`${PLAN_LABEL[plan]} plan, ${period}`} amount={changing?c2(q.charge_cents):money(amt,cur)} note={changing?`The new plan starts today and renews on ${q.new_period_end}.`:period==='yearly'?`One year, renews automatically, per user in ${cur}.`:recurring?`Charged every month ${rmode==='months'?`for ${rmonths} months`:`until ${rdate}`}, per user in ${cur}.`:`One month only, no automatic renewal, per user in ${cur}.`} busy={busy} err={err} onPay={pay} onClose={()=>{setPayOpen(false);setErr('')}}/>}
    {b.charges.length>0&&<section className="panel"><div className="panelhead"><h2>Payments</h2></div><table className="modtable"><thead><tr><th>Date</th><th>Plan</th><th>Amount</th><th>Result</th></tr></thead><tbody>{b.charges.map((c:any)=><tr key={c.id}><td>{(c.settled||'').slice(0,10)}</td><td>{PLAN_LABEL[c.plan]} ({c.period})</td><td>{money(c.amount_cents/100,cur)}</td><td>{c.status==='paid'?<>Paid {c.receipt_url&&<a href={c.receipt_url} target="_blank" rel="noreferrer">receipt</a>}</>:<span className="syncerr">Failed: {c.error}</span>}</td></tr>)}</tbody></table></section>}
    {b.refunds?.length>0&&<section className="panel"><div className="panelhead"><h2>Refund requests</h2></div><table className="modtable"><thead><tr><th>Date</th><th>Reason</th><th>Amount</th><th>Status</th></tr></thead><tbody>{b.refunds.map((x:any)=><tr key={x.id}><td>{(x.created||'').slice(0,10)}</td><td>{x.reason}</td><td>{c2(x.amount_cents)}</td><td>{x.status==='pending'?'Waiting for approval':x.status==='approved'?`Approved: ${c2(x.paid_back_cents)} returned to your card`:x.status==='partial'?'Being processed':`Declined${x.note?': '+x.note:''}`}</td></tr>)}</tbody></table></section>}
  </div>;
}


/** The card payment opens as a pop-up. The card fields are Square's own secure form: iSift never sees the card number. */
function PayDialog({sq,needForm,card,title,amount,note,busy,err,onPay,onClose}:{sq:any;needForm:boolean;card:any;title:string;amount:string;note:string;busy:boolean;err:string;onPay:(tok?:()=>Promise<string>)=>void;onClose:()=>void}){
  const form=useRef<any>(null);const [ready,setReady]=useState(false);const [loadErr,setLoadErr]=useState('');
  useEffect(()=>{if(!needForm)return;let dead=false;
    (async()=>{try{await loadSdk(sq.sdk);if(dead)return;const p=await window.Square.payments(sq.applicationId,sq.locationId);const c=await p.card();await c.attach('#sq-card');if(dead){try{c.destroy?.()}catch{};return}form.current=c;setReady(true)}catch(e:any){setLoadErr(e.message||'The card form could not start.')}})();
    return()=>{dead=true;try{form.current?.destroy?.()}catch{};form.current=null}},[needForm]);
  useEffect(()=>{const k=(e:KeyboardEvent)=>{if(e.key==='Escape'&&!busy)onClose()};window.addEventListener('keydown',k);return()=>window.removeEventListener('keydown',k)},[busy]);
  const go=()=>onPay(needForm?async()=>{const t=await form.current.tokenize();if(t.status!=='OK')throw new Error(t.errors?.[0]?.message||'Check the card details.');return t.token}:undefined);
  return <div className="pay-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&!busy)onClose()}}>
    <div className="pay-card" role="dialog" aria-modal="true" aria-label="Secure card payment">
      <button type="button" className="pay-x" onClick={onClose} disabled={busy} aria-label="Close"><X size={18}/></button>
      <p className="pay-secure"><Lock size={14}/> Secure payment by Square</p>
      <h2>{title}</h2><p className="pay-amount">{amount}</p><p className="muted small">{note}</p>
      {needForm?<><div id="sq-card" className="sq-card" aria-label="Card details"/>{!ready&&!loadErr&&<p className="muted">Loading the secure card form…</p>}</>:<p className="bill-card"><CreditCard size={16}/> {card?.brand} ending {card?.last4}</p>}
      {(err||loadErr)&&<p className="syncerr" role="alert">{err||loadErr}</p>}
      <button type="button" className="primary pay-go" disabled={busy||(needForm&&!ready)} onClick={go}><Lock size={15}/> {busy?'Processing…':`Pay ${amount}`}</button>
      <p className="muted small pay-foot"><ShieldCheck size={13}/> Card details go straight to Square. iSift only keeps the card type and last 4 digits.</p>
    </div></div>;
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
