import React,{useEffect,useState} from 'react';
import {Sun,ArrowLeft,ArrowUp,ChevronDown,X,Mail} from 'lucide-react';

// Who is behind the service. Change these two lines and every page updates.
export const LEGAL={service:'iSift',email:'info@isift.au',site:'www.isift.au',updated:'17 October 2026'};

export type LegalSlug='terms'|'privacy'|'trust'|'acceptable-use'|'legal-compliance';
export const LEGAL_LINKS:{slug:LegalSlug;label:string}[]=[
  {slug:'terms',label:'Terms'},
  {slug:'privacy',label:'Privacy'},
  {slug:'trust',label:'Trust Center'},
  {slug:'acceptable-use',label:'Acceptable Use Guidelines'},
  {slug:'legal-compliance',label:'Legal & Compliance'}];
export const isLegalHash=(h:string)=>/^#\/(terms|privacy|trust|acceptable-use|legal-compliance)$/.test(h);

type Sec={h:string;p?:string[];ul?:string[]};
const mail=LEGAL.email;

const PAGES:Record<LegalSlug,{title:string;intro:string;sections:Sec[]}>={
 terms:{title:'Terms of Service',intro:'These terms are the agreement between you and iSift when you use our website and meeting service. Please read them. By creating an account, joining a meeting or using iSift, you agree to them.',sections:[
  {h:'1. The service',p:['iSift is a meeting assistant. It lets you hold video meetings in your browser, share booking pages, bring your mail, calendar and contacts together, and turn meetings into briefings, minutes and action items that a person reviews.','We may improve, change or remove features. If we make a change that matters to a paid plan, we will tell you in advance where we reasonably can.']},
  {h:'2. Your account',ul:['You must give accurate details and keep your password and access keys private. You are responsible for what happens under your account.','You must be at least 18, or have a parent or guardian who accepts these terms for you.','Tell us straight away at '+mail+' if you think someone else has used your account.','Guests can join a meeting without an account, but the host who invited them remains responsible for the meeting.']},
  {h:'3. Plans, payment and refunds',ul:['Basic is free. Individual and Business are paid plans, charged per user by card through Square, in the currency shown on the Pricing page.','Paid plans renew automatically at the end of each month or year until you cancel. You can cancel at any time and keep the plan until the end of the period you have already paid for.','When you change plan, the difference is worked out by days. An upgrade charges the difference for the rest of the period; a downgrade can create a refund.','Refunds are reviewed and approved by a person before any money is returned. We will explain our decision if we decline one.','Nothing in these terms limits your rights under the Australian Consumer Law, including any right to a refund or remedy for a major failure.']},
  {h:'4. Your content and recordings',ul:['You keep ownership of what you bring to iSift: your meetings, chat, files, calendar and mail data, recordings and minutes ("your content").','You give us permission to store, process and display your content only as needed to run the service for you, including the AI features you use.','A host who records a meeting must have the right to do so. Recording and transcription laws differ by place, and some require everyone\'s consent. iSift shows a clear Recording banner to everyone, but telling people and getting any consent that is required is the host\'s responsibility.','Recordings are saved to the host\'s own computer by default. If the host chooses to also keep a copy in the cloud, it is stored in that account\'s own folder. On the Basic plan cloud copies are deleted after 2 days.']},
  {h:'5. AI features',p:['Minutes, action items, briefings, transcripts and email drafts are produced with the help of AI. AI can be wrong or incomplete. Drafts are marked for human review, and you should check them before you rely on them or share them.','We do not use your content to train AI models. The AI provider we use is listed on the Privacy page.']},
  {h:'6. Acceptable use',p:['You must follow the Acceptable Use Guidelines. We may suspend content or an account that breaks them, and we will explain why where we can.']},
  {h:'7. Third-party services',p:['iSift can connect to services you choose, such as Microsoft, Google, Zoom, Square, and other mail and calendar providers. Their own terms apply to those services, and we are not responsible for them.']},
  {h:'8. Availability and support',p:['We work to keep iSift running but cannot promise it will always be available or error-free. Meetings use direct connections between browsers, so quality also depends on your network. Support is by email at '+mail+'; priority support is part of the Business plan.']},
  {h:'9. Our responsibility',ul:['To the extent the law allows, we are not liable for indirect or consequential loss, or for loss of profit, data or opportunity.','Where the law lets us limit our liability for a consumer-law guarantee, we limit it to supplying the service again or paying the cost of having it supplied again.','Nothing in these terms excludes or limits a right you have under the Australian Consumer Law or any other law that cannot be excluded.']},
  {h:'10. Ending your account',p:['You can stop using iSift at any time and ask us to delete your account at '+mail+'. We may suspend or end an account that seriously or repeatedly breaks these terms, or if we are required to by law. Sections that by their nature should continue (such as ownership and liability) will continue.']},
  {h:'11. Changes to these terms',p:['We may update these terms. The date at the top of the page shows the latest version. If a change is significant we will tell you before it applies. Using iSift after a change means you accept it.']},
  {h:'12. Governing law and contact',p:['These terms are governed by the laws of New South Wales, Australia, and the courts of that State, except where the law in your place of residence gives you the right to use your local courts. Questions about these terms: '+mail+'.']}]},

 privacy:{title:'Privacy Policy',intro:'This explains what personal information iSift collects, why, who handles it and what choices you have. We handle personal information in line with the Privacy Act 1988 (Cth) and the Australian Privacy Principles.',sections:[
  {h:'What we collect',ul:['Account details: your name, email, phone, country, password (stored only as a salted hash) and plan.','Meeting information: titles, times, who was invited or joined, chat messages, and notes, minutes and action items you create or approve.','Recordings and transcripts, only when a host records or uploads audio. By default a recording is saved on the host\'s own computer; a cloud copy exists only if the host chooses it.','Connected accounts: if you connect a mail or calendar account, we use the access you grant to show and send mail, read events and contacts, and book meetings. You can disconnect at any time.','Payment details: card payments are handled by Square. We do not store your full card number; we keep your plan, billing dates, amounts and the payment reference Square gives us.','Technical information: sign-in and security logs, your time zone and basic device and connection information needed to run the service.']},
  {h:'Why we use it',ul:['To provide the service: run meetings, send invitations and confirmations, show your calendar and mail, and produce the briefings, minutes and transcripts you ask for.','To take payment, issue refunds and keep billing records.','To keep iSift secure, prevent abuse and meet our legal obligations.','To contact you about your account, security and important changes. We send marketing only if you have agreed, and every marketing message lets you opt out.']},
  {h:'Who processes your information',p:['We use these providers to run iSift. They handle information only to provide their service to us, and some are located outside Australia (including in the United States).'],ul:['Hosting and database: Northflank (application hosting) and Neon (database).','Network and file storage: Cloudflare (domain, network protection, and optional cloud storage of recordings).','Payments: Square.','AI: Groq, which receives the text or audio needed to produce minutes, briefings, transcripts, booking-link email drafts and answers in the website chat assistant (what a visitor types there is sent to Groq but not stored by us). Your content is not used by us to train AI models.','Email delivery: the mail provider your administrator or you have connected.','Providers you connect yourself, such as Microsoft, Google or Zoom, under their own privacy terms.']},
  {h:'Recordings, consent and other people',p:['If you host a meeting you are responsible for telling participants and for any consent the law requires before recording. iSift shows everyone a Recording banner. If you give us other people\'s details (for example to invite them), you confirm you may do so.']},
  {h:'How long we keep it',ul:['Account and billing records are kept while your account is active and for the period the law requires after it ends.','Cloud copies of recordings on the Basic plan are deleted after 2 days. Other cloud copies stay until you delete them or close your account.','Meeting data and minutes are kept until you delete them or ask us to delete your account.']},
  {h:'Security',p:['Connections to iSift use HTTPS. Passwords are stored as salted hashes, and saved secrets such as API keys are encrypted. Access to administration is restricted to administrators. No system is perfectly secure; if there is a data breach likely to cause serious harm we will notify you and the Office of the Australian Information Commissioner as the law requires. See our Trust Center for more.']},
  {h:'Cookies and similar storage',p:['iSift uses your browser\'s storage to keep you signed in, remember small preferences (such as your meeting layout) and protect against abuse. We do not use advertising trackers.']},
  {h:'Your choices and rights',ul:['Ask to see the personal information we hold about you, or to correct it.','Ask us to delete your account and information, subject to records we must keep by law.','Disconnect connected accounts and delete recordings, minutes and other content yourself in the app.','Complain to us at '+mail+'. We will respond within a reasonable time. If you are not satisfied, you can contact the Office of the Australian Information Commissioner (oaic.gov.au).']},
  {h:'Children',p:['iSift is not directed at children under 18, and we do not knowingly collect their information. Contact us if you think a child has given us personal information.']},
  {h:'Changes and contact',p:['We will update this policy when our practices change and show the date at the top. Privacy questions or requests: '+mail+'.']}]},

 trust:{title:'Trust Center',intro:'How we protect your meetings and data, written plainly. We describe what is in place today and say clearly what is not.',sections:[
  {h:'Control of who is in your meeting',ul:['Choose who can join: anyone with the link, link and passcode, or signed-in people only. Passcode guessing is rate-limited.','Waiting room: the host admits or denies each person.','Host and co-host controls on the server, not just in the page: mute people, switch off video, remove people, decide whether participants can unmute or start video.','Discussion groups keep each group\'s video, audio and chat separate, enforced by the server.','Everyone sees a clear Recording banner while a meeting is recorded.']},
  {h:'Protecting your data',ul:['All traffic uses HTTPS.','Passwords are stored as salted hashes. Saved secrets such as API keys are encrypted before they are stored.','Recordings are saved to the host\'s own computer by default. If a cloud copy is chosen it is stored in that account\'s own folder, and Basic-plan cloud copies are deleted after 2 days.','Each person sees their own mail, calendar, contacts and meetings. Company administrators manage their own company\'s account.','An audit log records important administrative actions on Business plans.']},
  {h:'Responsible AI',ul:['Minutes, action items and briefings are drafts that a person reviews and approves before they are final.','AI prompts treat meeting text as data, not instructions, and drafts show evidence where it is available.','We do not use your content to train AI models.']},
  {h:'Where your data is processed',p:['iSift runs on Northflank with a Neon database and optional Cloudflare storage. AI processing is by Groq. Some of these providers operate outside Australia. The Privacy page lists the providers and what each does.']},
  {h:'Certifications and testing',p:['iSift has not been independently certified (for example SOC 2 or ISO 27001), and we do not claim to be. We test the product and review security as we build it. If your organisation needs a security questionnaire answered, contact '+mail+'.']},
  {h:'Reporting a security problem',p:['If you find a vulnerability, please email '+mail+' with the details. Please do not access other people\'s data or disrupt the service while testing. We will acknowledge your report and keep you informed.']}]},

 'acceptable-use':{title:'Acceptable Use Guidelines',intro:'iSift is for people to meet and work together. These guidelines apply to everyone who uses iSift, including guests. Breaking them can lead to a meeting being ended or an account being suspended.',sections:[
  {h:'You must not',ul:['Break the law, or use iSift to plan, threaten or carry out harm, harassment, stalking, hate, or abuse of any person or group.','Share sexual content involving children, or any other content that exploits or endangers a child. We report this to the authorities.','Send spam, scams, phishing or unwanted bulk invitations, or use booking pages and meeting invitations to deceive people.','Impersonate another person or organisation, or give misleading names or details to mislead others.','Record, transcribe or share a meeting without telling participants and getting any consent the law requires.','Upload or share malware, or try to break, probe, overload or bypass iSift\'s security, rate limits or access controls.','Access another person\'s account, meeting, mail or recordings without permission.','Use iSift\'s AI features to produce content that breaks this list, or to make automated decisions about people without human review.','Infringe someone\'s copyright, trademark or privacy.','Resell or share your account or access keys, or use iSift in a way that harms other customers.']},
  {h:'Hosts have extra responsibilities',ul:['Tell participants when a meeting is recorded and make sure you may record it.','Remove people who break these guidelines, and report serious problems to us.','Keep passcodes and meeting links to the people you intend.']},
  {h:'Reporting a problem',p:['If you see something that breaks these guidelines, email '+mail+' with the meeting link or time and what happened. In an emergency, contact the police (000 in Australia) first.']},
  {h:'What we may do',p:['We may end a meeting, remove content, limit features or suspend an account that breaks these guidelines. For serious or repeated breaches we may close the account. We will tell you why where we can, and you can reply to ask for a review. We may pass information to the authorities where the law requires or allows.']}]},

 'legal-compliance':{title:'Legal & Compliance',intro:'A summary of the laws and rules that matter when you use iSift, and how to reach us for legal matters. This page is general information, not legal advice.',sections:[
  {h:'Privacy',p:['We handle personal information in line with the Privacy Act 1988 (Cth) and the Australian Privacy Principles. Our Privacy Policy explains what we collect and your rights. You can request access, correction or deletion at '+mail+'.','If you are in another region (for example the European Economic Area or the United Kingdom) and want to exercise rights under your local privacy law, contact us and we will respond as that law requires.']},
  {h:'Consumer law',p:['Our services come with guarantees that cannot be excluded under the Australian Consumer Law. Nothing on our website or in our terms limits those guarantees. Paid plans can be cancelled at any time; refund requests are reviewed and approved by a person.']},
  {h:'Recording and surveillance laws',p:['Laws about recording conversations and using listening devices differ between Australian States and Territories and between countries, and some require every participant to agree. The host who records a meeting is responsible for lawful recording. iSift shows a Recording banner to everyone, keeps recordings on the host\'s computer by default and lets the host decide whether a cloud copy is kept.']},
  {h:'Email and invitations',p:['Invitations and booking messages sent through iSift are sent at your request. Under the Spam Act 2003 (Cth) you must have the right to contact the people you invite, and you must not use iSift for unsolicited commercial messages.']},
  {h:'Copyright and takedown',p:['If you believe content on iSift infringes your copyright, email '+mail+' with the content, where it is, and your contact details. We will review it and act as the law requires.']},
  {h:'Requests from authorities',p:['We may disclose information when required by law, such as a valid court order or warrant. Where the law allows, we will tell the affected account holder.']},
  {h:'Providers and international transfers',p:['Some providers that help us run iSift are outside Australia. We choose providers that handle information only to provide their service to us. The Privacy page lists them.']},
  {h:'Complaints and contact',p:['Send complaints or legal notices to '+mail+'. We will acknowledge them and reply within a reasonable time. You can also contact the Office of the Australian Information Commissioner (oaic.gov.au) about a privacy complaint.']}]}
};

export function LegalLinks({className=''}:{className?:string}){
  return <nav className={`legal-links ${className}`} aria-label="Legal">{LEGAL_LINKS.map(l=><a key={l.slug} href={`#/${l.slug}`}>{l.label}</a>)}</nav>;
}

const API:string=(import.meta as any).env.VITE_API_BASE||((import.meta as any).env.VITE_DEMO_MODE==='true'?'http://127.0.0.1:8000/api/v1':'/api/v1');
type FormKind='support'|'contact'|'feedback';
const FORMS:Record<FormKind,{label:string;title:string;hint:string;topic:string}>={
  support:{label:'Support request',title:'Send a support request',hint:'Tell us what you were doing and what went wrong. Include the meeting ID if it is about a meeting.',topic:'What do you need help with?'},
  contact:{label:'Contact us',title:'Contact us',hint:'Questions about plans, partnerships or anything else.',topic:'Subject'},
  feedback:{label:'Feedback',title:'Share your feedback',hint:'What works, what does not, and what you would like to see. We read every message.',topic:'About (optional)'}};

function FooterForm({kind,onClose}:{kind:FormKind;onClose:()=>void}){
  const f=FORMS[kind];const [k,setK]=useState<FormKind>(kind);const [name,setName]=useState('');const [email,setEmail]=useState('');const [topic,setTopic]=useState('');const [message,setMessage]=useState('');const [trap,setTrap]=useState('');
  const [busy,setBusy]=useState(false);const [err,setErr]=useState('');const [done,setDone]=useState(false);const cur=FORMS[k];
  useEffect(()=>{const h=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose()};window.addEventListener('keydown',h);return()=>window.removeEventListener('keydown',h)},[]);
  const submit=async(e:React.FormEvent)=>{e.preventDefault();setBusy(true);setErr('');
    try{const r=await fetch(`${API}/support/contact`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:k,name,email,topic,message,website:trap})});const j=await r.json().catch(()=>({}));
      if(!r.ok)setErr(typeof j.detail==='string'?j.detail:Array.isArray(j.detail)?'Please check the form and try again.':'Your message could not be sent. Please email '+LEGAL.email+'.');else setDone(true)}
    catch{setErr('Could not reach the server. Please email '+LEGAL.email+'.')}finally{setBusy(false)}};
  return <div className="ff-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}>
    <div className="ff-card" role="dialog" aria-modal="true" aria-label={cur.title}>
      <button type="button" className="ff-x" onClick={onClose} aria-label="Close"><X size={18}/></button>
      {done?<div className="ff-done"><h2>Thank you</h2><p>Your message has been sent to the iSift team. We will reply to <b>{email}</b>.</p><button type="button" className="nav-login" onClick={onClose}>Close</button></div>:
      <form onSubmit={submit}>
        <h2>{cur.title}</h2><p className="ff-hint">{cur.hint} Or email <a href={`mailto:${LEGAL.email}`}>{LEGAL.email}</a>.</p>
        <div className="ff-tabs" role="tablist">{(Object.keys(FORMS) as FormKind[]).map(x=><button type="button" role="tab" aria-selected={x===k} key={x} className={x===k?'on':''} onClick={()=>setK(x)}>{FORMS[x].label}</button>)}</div>
        <label>Your name<input value={name} onChange={e=>setName(e.target.value)} maxLength={100} autoComplete="name" required/></label>
        <label>Your email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} maxLength={200} autoComplete="email" required/></label>
        <label>{cur.topic}<input value={topic} onChange={e=>setTopic(e.target.value)} maxLength={150}/></label>
        <label>Message<textarea value={message} onChange={e=>setMessage(e.target.value)} maxLength={5000} rows={5} required/></label>
        <input className="ff-trap" tabIndex={-1} autoComplete="off" aria-hidden="true" value={trap} onChange={e=>setTrap(e.target.value)} name="website"/>
        {err&&<p className="ff-err" role="alert">{err}</p>}
        <div className="ff-actions"><button type="button" className="ff-cancel" onClick={onClose}>Cancel</button><button type="submit" className="primary" disabled={busy}>{busy?'Sending…':'Send message'}</button></div>
      </form>}
    </div></div>;
}

export function LegalFooter(_p:{tagline?:boolean}={}){
  const [map,setMap]=useState(false);const [form,setForm]=useState<FormKind|null>(null);
  const open=(k:FormKind)=>(e:React.MouseEvent)=>{e.preventDefault();setForm(k)};
  return <footer className="site-footer">
    <div className="sf-top"><div className="sf-help"><b>Need a hand?</b>
      {(Object.keys(FORMS) as FormKind[]).map(k=><a key={k} href={`mailto:${LEGAL.email}`} onClick={open(k)}>{FORMS[k].label}</a>)}
      <a href={`mailto:${LEGAL.email}`}><Mail size={13}/> {LEGAL.email}</a></div></div>
    {map&&<nav id="sf-sitemap" className="sf-sitemap" aria-label="Sitemap">
      <div><h4>iSift</h4><a href="#/">Home</a><a href="#/pricing">Plans and pricing</a></div>
      <div><h4>Legal</h4>{LEGAL_LINKS.map(l=><a key={l.slug} href={`#/${l.slug}`}>{l.label}</a>)}</div>
      <div><h4>Support</h4>{(Object.keys(FORMS) as FormKind[]).map(k=><a key={k} href={`mailto:${LEGAL.email}`} onClick={open(k)}>{FORMS[k].label}</a>)}<a href={`mailto:${LEGAL.email}`}>Email {LEGAL.email}</a></div>
    </nav>}
    <div className="sf-bar">
      <LegalLinks/>
      <button type="button" className="sf-map" aria-expanded={map} aria-controls="sf-sitemap" onClick={()=>setMap(m=>!m)}>Sitemap <ChevronDown size={14} className={map?'up':''}/></button>
    </div>
    <div className="sf-base">
      <span className="sf-copy">Copyright ©{new Date().getFullYear()} {LEGAL.service}. All rights reserved.</span>
      <button type="button" className="sf-top-link" onClick={()=>window.scrollTo({top:0,behavior:'smooth'})} aria-label="iSift · Back to top"><span className="sf-up"><ArrowUp size={20}/></span><span className="sf-uptxt">iSift · Back to top</span></button>
      <span className="sf-tag">Private by design · Human-reviewed outcomes</span>
    </div>
    {form&&<FooterForm kind={form} onClose={()=>setForm(null)}/>}
  </footer>;
}

export function LegalPage({slug,onHome,loggedIn}:{slug:LegalSlug;onHome:()=>void;loggedIn:boolean}){
  const pg=PAGES[slug];
  useEffect(()=>{window.scrollTo(0,0);const old=document.title;document.title=`${pg.title} · iSift`;return()=>{document.title=old}},[slug]);
  const home=(e:React.MouseEvent)=>{e.preventDefault();onHome()};
  const back=<a className="legal-back" href="#/" onClick={home}><ArrowLeft size={16}/> {loggedIn?'Back to my workspace':'Back to iSift home'}</a>;
  return <div className="legal-page">
    <header className="landing-nav"><a className="landing-brand" href="#/" onClick={home} aria-label="iSift home"><span className="brandicon"><Sun size={20}/></span><span><b>iSift</b><small>Make every meeting count</small></span></a>
      <nav className="public-links"><button type="button" className="nav-login" onClick={onHome}><ArrowLeft size={16}/> {loggedIn?'Back to my workspace':'Back to home'}</button></nav></header>
    <main className="legal-main">
      {back}
      <p className="eyebrow">LEGAL</p><h1>{pg.title}</h1><p className="legal-updated">Last updated {LEGAL.updated}</p>
      <nav className="legal-tabs" aria-label="Legal pages">{LEGAL_LINKS.map(l=><a key={l.slug} href={`#/${l.slug}`} className={l.slug===slug?'on':''} aria-current={l.slug===slug?'page':undefined}>{l.label}</a>)}</nav>
      <p className="legal-intro">{pg.intro}</p>
      {pg.sections.map(s=><section key={s.h}><h2>{s.h}</h2>{s.p?.map((t,i)=><p key={i}>{t}</p>)}{s.ul&&<ul>{s.ul.map((t,i)=><li key={i}>{t}</li>)}</ul>}</section>)}
      <p className="legal-contact">Questions? Email <a href={`mailto:${mail}`}>{mail}</a>.</p>
      {back}
    </main>
    <LegalFooter/>
  </div>;
}
