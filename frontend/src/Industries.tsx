import React from 'react';
import {ArrowLeft,ArrowRight,Check,Building2,Stethoscope,GraduationCap,Landmark,Factory,HeartHandshake,ShoppingBag,Briefcase,HardHat,Scale,Video,PenLine,CalendarClock,Mail,FileSignature,Sparkles,Presentation,Users,ChevronDown,ShieldCheck,Lock,FileText,BookOpen} from 'lucide-react';
import {LegalFooter} from './Legal';

/** Industry pages, in the style of Zoom and Zoho industry solutions. Same product, packaged per sector.
 *  Copy lists only features iSift has today. Roadmap items live in docs/industry-solutions, not here.
 *  "Check" notes are general information, not legal advice. */
export type Industry={slug:string;name:string;icon:any;line:string;intro:string;pains:string[];fits:string[];checks:string[];uses:string[]};

export const INDUSTRIES:Industry[]=[
 {slug:'real-estate',name:'Real estate',icon:Building2,line:'Appraise, sign and follow up in one place.',
  intro:'For sales agencies, property managers and buyer’s agents. Vendors, buyers and tenants join from a link, and the paperwork is signed in the same account.',
  pains:['Clients will not install an app or create an account.','Agency agreements and applications need signatures and copies.','Meetings, mail, documents and signing sit in four tools.','Appraisals and viewings are booked by phone and text.'],
  fits:['Guests join free from a link, in the browser.','Edit and sign PDFs in the same app.','Minutes drafted by AI and reviewed by a person before they go out.','Booking pages for appraisals and viewings.','Invitations from your own email address.'],
  checks:['A written agency agreement is needed before commission can be claimed, and rules differ by state.','Record retention periods differ by state; some are seven years.','Trust accounting stays in your accounting software.','AML/CTF duties for agents: check AUSTRAC for current dates.'],
  uses:['Appraisal meeting and follow-up','Agency agreement signing','Property inspection booking','Vendor update call','Tenant application meeting']},
 {slug:'healthcare',name:'Healthcare',icon:Stethoscope,line:'Telehealth without the app.',
  intro:'For clinics, allied health and care coordinators. Patients click a link and join, and notes are drafted for the clinician to approve.',
  pains:['Patients struggle with apps and logins.','Notes and admin are written twice.','Consent forms and referrals need signatures.','No-shows cost revenue.'],
  fits:['Patients join free from a link, no account.','AI notes drafted for review; nothing leaves until a person approves.','Sign consent and intake PDFs.','Booking pages and calendar sync.','Single sign-on and audit log on Business.'],
  checks:['Health information is sensitive information under the Privacy Act.','State health records laws set retention; periods are often long.','Recording needs the patient’s consent.','Ask us for the privacy and data-handling summary.'],
  uses:['Telehealth consult','New patient intake','Care-team case conference','Referral summary','Service agreement signing']},
 {slug:'education',name:'Education',icon:GraduationCap,line:'Lessons that do not stop at 40 minutes.',
  intro:'For schools, colleges, tutors and training providers. Students and parents join from a link and work together on the same page.',
  pains:['Free plans cut classes short.','Parents and students will not create accounts.','Slides, worksheets and meetings live in separate tools.','Permission forms need signatures.'],
  fits:['Free group meetings run 90 minutes.','Guests join free from a link.','Whiteboard, notes, spreadsheets and slides edited together in the meeting.','Several people can share their screen at once.','Webinars for open days; PDF signing for permission forms.'],
  checks:['Child-safety and privacy rules apply to minors.','Get parent or guardian consent before recording students.','Training providers have their own evidence and record rules.'],
  uses:['Class session with whiteboard','Parent-teacher interviews','Open-day webinar','Excursion permission form','Tutor booking page']},
 {slug:'financial-services',name:'Financial services',icon:Landmark,line:'Client meetings, file notes and signatures together.',
  intro:'For advisers, brokers, accountants and small lenders. Minutes are drafted for you to approve, and clients sign in the meeting.',
  pains:['Meetings, file notes and signed documents are in separate systems.','Advice records must be complete and kept.','Clients will not install software.'],
  fits:['Client joins free from a link.','AI minutes and action items, approved by a person.','Sign engagement letters and authorities as PDFs.','Booking pages; mail from your own firm address.','Single sign-on and audit log on Business.'],
  checks:['Advice and credit records are usually kept for years; check your licence conditions.','Customer identification duties may apply.','Get consent before recording.'],
  uses:['Discovery meeting','Engagement letter signing','Annual review','File-note drafting','Client webinar']},
 {slug:'government',name:'Government',icon:Scale,line:'Open meetings, open to everyone.',
  intro:'For councils, agencies and community services. Residents join from a link, and webinars handle consultation sessions.',
  pains:['Public consultation needs no-account participation.','Meetings are subject to records and transparency rules.','Procurement asks for security and data-location evidence.'],
  fits:['Citizens join free from a link.','Webinars with registration, Q&A and polls.','Live captions.','Minutes drafted and approved by a person.','Single sign-on and audit log on Business.'],
  checks:['Public records and open-meeting rules apply.','Security frameworks and data-location requirements vary; ask us for the trust pack.','Accessibility standards apply to public services.'],
  uses:['Council meeting','Community consultation webinar','Public information session','Staff briefing','Submission booking']},
 {slug:'manufacturing',name:'Manufacturing',icon:Factory,line:'Suppliers, specs and sign-offs in one meeting.',
  intro:'For manufacturers and distributors. Share screens together, edit a schedule live, sign the quote.',
  pains:['Supplier and customer calls span sites and time zones.','Quotes and approvals travel by email.','Office and floor teams use different tools.'],
  fits:['Suppliers join free from a link.','Several people share screens at once.','Edit spreadsheets and notes together.','Sign quotes and approvals as PDFs.','Recordings and AI action items you approve.'],
  checks:['Quality and safety records may be required by your certification.','Use an NDA before sharing drawings.'],
  uses:['Supplier review','Quote approval','Toolbox talk','Production meeting','Customer demo webinar']},
 {slug:'nonprofit',name:'Nonprofit',icon:HeartHandshake,line:'Run your board and volunteers for almost nothing.',
  intro:'For charities, clubs and community groups. Price follows the size of the room, not the number of volunteers.',
  pains:['Tight budgets and per-user pricing.','Volunteers use many email and calendar systems.','Board meetings need minutes on record.'],
  fits:['Free plan: 25 people, 90 minutes.','Guests join free.','Connect Google, Microsoft, Yahoo and iCloud calendars.','Board minutes drafted and approved by a person.','Webinars for fundraising and information nights.'],
  checks:['Charity governance standards expect minutes and records.','Protect donor and member details.'],
  uses:['Board meeting','AGM','Volunteer onboarding','Fundraising webinar','Volunteer agreement signing']},
 {slug:'retail',name:'Retail and e-commerce',icon:ShoppingBag,line:'Turn browsers into booked consultations.',
  intro:'For independent retailers and brands. Customers book and join from a link, and suppliers share screens in buying meetings.',
  pains:['Supplier negotiations span time zones.','Consultations and custom orders need booking and follow-up.','Store and franchise meetings are scattered.'],
  fits:['Booking pages for consultations.','Webinars for launches and demos.','Share screens and edit order sheets together.','Mail from your own address.','Sign wholesale terms as PDFs.'],
  checks:['Consumer law applies to claims and pricing.','Marketing messages need consent.'],
  uses:['Supplier negotiation','Custom order consultation','Product launch webinar','Wholesale terms signing','Franchise briefing']},
 {slug:'professional-services',name:'Professional services',icon:Briefcase,line:'From first call to signed engagement.',
  intro:'For lawyers, consultants, recruiters and agencies. Meet, take notes and sign in one account.',
  pains:['Confidentiality and tool sprawl.','Billable meetings need accurate notes.','Engagement letters and NDAs need signatures.'],
  fits:['Clients join free from a link.','Minutes and action items drafted for approval.','Sign engagement letters and NDAs.','Edit documents and slides in the meeting.','Single sign-on, audit log and priority support on Business.'],
  checks:['Client confidentiality and record retention apply; many records are kept for years.','Check where client data is stored.'],
  uses:['Client intake','Engagement letter','NDA signing','Project kickoff','Candidate interview']},
 {slug:'construction',name:'Construction and trades',icon:HardHat,line:'Sign off variations before the work starts.',
  intro:'For builders and trades. Owners and subcontractors join from a link on any phone.',
  pains:['Site meetings happen on mobile.','Variations and quotes must be signed before work.','Photos and decisions are scattered across texts.'],
  fits:['Join free from a link on any phone.','Sign quotes and variations as PDFs.','Booking pages for quotes and site visits.','Action items drafted for approval.','Mail from your own business address.'],
  checks:['Home building rules require written, signed variations in many states.','Keep records for warranty and defect periods.'],
  uses:['Site meeting','Variation approval','Quote acceptance','Subcontractor onboarding','Handover']},
];

export function IndustriesSection(){
  return <section className="landing-section" id="industries"><p className="eyebrow">INDUSTRIES</p><h2>iSift for your industry.</h2>
    <p className="why-lead">The same one account, set up for how your sector works. Pick yours to see how it fits.</p>
    <div className="why-grid">{INDUSTRIES.map(x=><article key={x.slug} className="why-card ind-card"><span className="why-ic"><x.icon size={20}/></span><h3>{x.name}</h3><p>{x.line}</p>
      <a className="new-link" href={`#/industry/${x.slug}`}>See how it fits <ArrowRight size={14}/></a></article>)}</div></section>;
}

/** Feature blocks, as on Zoho’s industry pages: a small label, a headline and a short paragraph, each beside a picture panel. */
const BLOCKS:Record<string,[string,string,string][]>={
 'real-estate':[['Meetings','Appraise from anywhere.','Vendors and buyers join from a link in their browser. No app, no account, and you can share your screen or a PDF.'],['Booking','Let clients pick a time.','Share a booking page for appraisals and viewings. Each booking lands in your calendar with a meeting room attached.'],['Signing','Sign the agreement in the meeting.','Edit and sign PDFs in the same app, so agency agreements and applications do not wait on a second tool.'],['AI minutes','Minutes you approve.','Minutes and action items are drafted from the conversation. Nothing goes to the vendor until you have checked it.'],['Mail','Send from your own address.','Invitations go from your own email, and Yes, No or Maybe answers come back to your inbox.']],
 'healthcare':[['Telehealth','Patients click and join.','No app, no account, no password to forget. Patients join from the link in their reminder.'],['Notes','Drafted for you, approved by you.','AI drafts minutes and actions. A clinician reviews them before anything is shared.'],['Forms','Consent before the call.','Send consent and intake PDFs to sign online, and keep them with the appointment.'],['Booking','Fewer missed appointments.','A booking page and calendar sync keep the day full and reminders on time.'],['Teams','Case conferences made simple.','Care teams meet, share documents and agree actions in one place.']],
 'education':[['Classes','Lessons that do not stop at 40 minutes.','Free group meetings run 90 minutes, and paid plans have no time limit.'],['Together','Work on the same page.','Edit a whiteboard, note, spreadsheet or slides together while you teach.'],['Parents','Meet parents without accounts.','Parents and students join from a link. Book parent-teacher interviews with a booking page.'],['Forms','Permission forms signed online.','Send excursion and enrolment forms as PDFs to sign.'],['Webinars','Open days and information nights.','Registration, panelists, questions and polls are built in.']],
 'financial-services':[['Meetings','Meet clients where they are.','Clients join from a link, with no software to install.'],['File notes','Notes that write themselves.','Minutes and action items are drafted for you to approve, which matters for advice records.'],['Signing','Engagement letters signed in the meeting.','Edit and sign PDFs without leaving the call.'],['Control','Single sign-on and an audit log.','On Business, administrators set who can use what and can see what happened.'],['Webinars','Client education sessions.','Run webinars with registration and reports.']],
 'government':[['Consultation','Everyone can join.','Residents join from a link, with live captions and no account.'],['Webinars','Information sessions at scale.','Registration, questions and polls for public sessions.'],['Records','Minutes with a person in charge.','AI drafts minutes, a person approves them.'],['Control','Single sign-on and audit log.','Administrators control access on the Business plan.']],
 'manufacturing':[['Suppliers','No app for suppliers.','Suppliers and customers join from a link, wherever they are.'],['Sharing','Share more than one screen.','Several people can share at once, side by side, to compare drawings and specs.'],['Together','Edit the schedule live.','Update a spreadsheet or note together during the call.'],['Approvals','Sign off on the spot.','Sign quotes and purchase approvals as PDFs.']],
 'nonprofit':[['Free','Start with a free plan.','25 people for 90 minutes, free for ever. Guests join free.'],['Board','Board minutes, drafted.','AI drafts minutes and actions for the chair to approve.'],['Calendars','Works with the calendars you use.','Connect Google, Microsoft, Yahoo and iCloud once.'],['Events','Fundraising webinars.','Registration pages, questions and polls are built in.']],
 'retail':[['Booking','Book consultations online.','Share a booking page for fittings, designs and custom orders.'],['Webinars','Launch products live.','Run demos and launches as webinars with registration.'],['Suppliers','Negotiate face to face.','Share screens and edit order sheets together.'],['Terms','Wholesale terms signed online.','Edit and sign PDFs in the same account.']],
 'professional-services':[['Clients','Meet without friction.','Clients join from a link, with no account to create.'],['Actions','Follow-through, not just a recap.','Minutes and action items with owners, drafted for approval.'],['Signing','From call to signed engagement.','Engagement letters and NDAs signed in the meeting.'],['Documents','Edit together.','Co-edit documents and slides while you talk.']],
 'construction':[['Site','Join from any phone.','Owners and subcontractors join from a link, with no app.'],['Variations','Sign off before work starts.','Quotes and variations signed as PDFs, in the meeting.'],['Booking','Book quotes and site visits.','A booking page keeps the diary organised.'],['Actions','Who does what, by when.','Action items drafted for you to approve.']],
};
const ICONS=[Video,CalendarClock,FileSignature,Sparkles,Mail,PenLine,Presentation,Users];
const FAQ:[string,string][]=[
 ['Do my clients need an account?','No. Anyone joins from a link in the browser, free. No app to install and no account to create.'],
 ['How much does it cost?','Basic is free for ever: 25 people for 90 minutes. Standard starts from A$2 a month per host for a 10-person room, and Business from A$7.92. Price follows the size of your meeting.'],
 ['Does AI send things on its own?','No. Minutes and action items are drafts until a person approves them.'],
 ['Can I keep my own calendars and email address?','Yes. Connect Google, Microsoft, Yahoo and iCloud, and send invitations from your own address.'],
];

export function IndustryPage({slug,onSignup}:{slug:string;onSignup?:()=>void}){
  const x=INDUSTRIES.find(i=>i.slug===slug);const [open,setOpen]=React.useState(0);
  const back=()=>{if(history.length>1)history.back();else location.hash='#/website'};
  React.useEffect(()=>{window.scrollTo(0,0)},[slug]);
  const start=(e:React.MouseEvent)=>{if(onSignup){e.preventDefault();onSignup()}};
  if(!x)return <div className="man-view"><header className="man-bar"><button type="button" className="secondary" onClick={back}><ArrowLeft size={15}/> Back</button><b>Industry</b></header><p className="muted" style={{padding:24}}>That industry page was not found. <a href="#/website">Back to iSift</a>.</p></div>;
  const blocks=BLOCKS[slug]||[];const others=INDUSTRIES.filter(i=>i.slug!==slug);
  return <div className="ind-page"><header className="man-bar ind-bar"><button type="button" className="secondary" onClick={back}><ArrowLeft size={15}/> Back</button><b>iSift for {x.name}</b><span className="sp"/>
      <a className="secondary" href="#/pricing">Pricing</a><a className="primary" href="#/website" onClick={start}>Get started</a></header>
    <section className="ind-hero2"><div className="ind-hero2-in"><div className="ind-hero2-copy"><nav className="ind-crumb" aria-label="Breadcrumb"><a href="#/website">iSift</a> &rsaquo; <span>Industries</span> &rsaquo; <b>{x.name}</b></nav><span className="ind-kicker"><x.icon size={15}/> iSift for {x.name}</span>
      <h1>{x.line}</h1><p>{x.intro}</p>
      <div className="ind-cta"><a className="primary" href="#/website" onClick={start}>Get started free <ArrowRight size={16}/></a><a className="secondary" href="#/pricing">See pricing</a></div><small>No card needed. Guests always join free.</small></div>
      <div className="ind-hero2-art" aria-hidden="true"><div className="ind-win"><div className="ind-win-bar"><i/><i/><i/></div><div className="ind-win-body"><div className="ind-tile"><x.icon size={34}/></div><div className="ind-tile s"><Users size={22}/></div><div className="ind-tile s"><Video size={22}/></div><div className="ind-tile s"><FileSignature size={22}/></div></div></div>
        <span className="ind-float f1"><Check size={13}/> Guest joined from a link</span><span className="ind-float f2"><Sparkles size={13}/> Minutes ready to approve</span></div></div></section>
    <section className="ind-stats"><div><b>90 min</b><span>free group meetings</span></div><div><b>Free</b><span>for guests, no account</span></div><div><b>From A$2</b><span>per host a month</span></div><div><b>1 account</b><span>meetings, mail, documents, signing</span></div></section>
    <section className="ind-trust"><h2>Trusted from the first call</h2><div className="ind-trust-grid">
      <article><span><Lock size={20}/></span><h3>Private by design</h3><p>All traffic uses HTTPS. Passwords are stored as salted hashes, and saved keys are encrypted.</p></article>
      <article><span><ShieldCheck size={20}/></span><h3>A person approves the AI</h3><p>Minutes and action items are drafts until someone reviews them.</p></article>
      <article><span><FileText size={20}/></span><h3>Your files are not kept</h3><p>PDFs you edit or sign are processed for your request and sent straight back.</p></article></div>
      <p className="ind-trust-links"><a href="#/trust">Trust Center</a><a href="#/privacy">Privacy</a><a href="#/legal-compliance">Legal and compliance</a></p></section>
    <main className="ind-main">
      <section className="ind-pains"><h2>What gets in the way</h2><div className="ind-pain-grid">{x.pains.map(p=><div key={p}>{p}</div>)}</div></section>
      {blocks.map((b,k)=>{const I=ICONS[k%ICONS.length];return <section key={b[1]} className={`ind-block${k%2?' flip':''}`}>
        <div className="ind-block-copy"><span className="ind-label">{b[0]}</span><h2>{b[1]}</h2><p>{b[2]}</p></div>
        <div className={`ind-block-art a${k%4}`} aria-hidden="true"><I size={54}/><span className="ind-chip c1">{b[0]}</span><span className="ind-chip c2"><Check size={12}/> Done</span></div></section>})}
      <section><h2>How iSift fits {x.name.toLowerCase()}</h2><ul className="ind-fits">{x.fits.map(p=><li key={p}><Check size={15}/> {p}</li>)}</ul></section>
      <section className="ind-solutions"><h2>Solutions for {x.name.toLowerCase()} teams</h2>{[
        [Users,'Engage the people you serve','Bring clients, families or the public together from a link.',['Meetings','Webinars','Booking pages']],
        [PenLine,'Work as one team','Keep documents, mail and calendars beside the meeting.',['Notes and docs','Spreadsheets','Slides','Mail and calendar']],
        [FileSignature,'Close the loop','Turn the conversation into signed paperwork and clear next steps.',['Sign and edit PDFs','AI minutes you approve','Action items']]
      ].map(([I,t,d,chips]:any)=><div key={t} className="ind-sol"><span className="why-ic"><I size={20}/></span><div><h3>{t}</h3><p>{d}</p><div className="ind-chips">{chips.map((c:string)=><span key={c}>{c}</span>)}</div></div></div>)}</section>
      <section><h2>Built to scale with you</h2><div className="ind-proof">
        <a href="#/pricing"><b>10 to 300</b><span>people in a meeting room, priced by the size you need</span><em>See pricing</em></a>
        <a href="#/manual/webinars"><b>Webinars</b><span>registration, panelists, private Q&amp;A, polls and reports</span><em>Read the manual</em></a>
        <a href="#/manual/booking-and-follow-up"><b>Booking</b><span>pages that put every booking in your calendar with a room</span><em>Read the manual</em></a></div></section>
      <section><h2>Meetings you can set up today</h2><div className="ind-chips">{x.uses.map(u=><span key={u}>{u}</span>)}</div></section>
      <section className="ind-note"><h2>Worth checking for your sector</h2><ul>{x.checks.map(p=><li key={p}>{p}</li>)}</ul><p className="muted small">General information only, not legal advice. Check the rules that apply to your business.</p></section>
      <section><h2>Questions</h2><div className="ind-faq">{FAQ.map(([q,a],k)=><div key={q} className={open===k?'on':''}><button type="button" onClick={()=>setOpen(open===k?-1:k)} aria-expanded={open===k}>{q}<ChevronDown size={16}/></button>{open===k&&<p>{a}</p>}</div>)}</div></section>
    </main>
    <section className="ind-res"><h2>Resources</h2><div className="ind-res-grid"><a href="#/manual/meetings-and-sharing"><BookOpen size={18}/> Meetings and sharing manual</a><a href="#/manual/documents-and-whiteboard"><BookOpen size={18}/> Documents, signing and whiteboard</a><a href="#/manual/mail-calendar-contacts"><BookOpen size={18}/> Mail, calendar and contacts</a><a href="#/pricing"><BookOpen size={18}/> Plans and pricing</a></div></section>
    <section className="ind-final"><h2>Ready to try iSift for {x.name.toLowerCase()}?</h2><p>Start free in minutes. Switch your calendars over, then invite anyone with a link.</p><div className="ind-final-cards"><div><h3>Start free</h3><p>Basic is free for ever: 25 people, 90 minutes. No card needed.</p><a className="primary" href="#/website" onClick={start}>Get started free</a></div>
      <div><h3>Business plan</h3><p>Company account, team booking, single sign-on, audit log and priority support.</p><a className="secondary" href="#/pricing">See Business</a></div></div></section>
    <section className="ind-others"><h3>Other industries</h3><div className="ind-chips">{others.map(o=><a key={o.slug} href={`#/industry/${o.slug}`}>{o.name}</a>)}</div></section>
  <LegalFooter/></div>;
}
