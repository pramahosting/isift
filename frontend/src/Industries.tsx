import React from 'react';
import {ArrowLeft,ArrowRight,Check,Building2,Stethoscope,GraduationCap,Landmark,Factory,HeartHandshake,ShoppingBag,Briefcase,HardHat,Scale} from 'lucide-react';

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

export function IndustryPage({slug,onSignup}:{slug:string;onSignup?:()=>void}){
  const x=INDUSTRIES.find(i=>i.slug===slug);
  const back=()=>{if(history.length>1)history.back();else location.hash='#/website'};
  if(!x)return <div className="man-view"><header className="man-bar"><button type="button" className="secondary" onClick={back}><ArrowLeft size={15}/> Back</button><b>Industry</b></header><p className="muted" style={{padding:24}}>That industry page was not found. <a href="#/website">Back to iSift</a>.</p></div>;
  const others=INDUSTRIES.filter(i=>i.slug!==slug);
  return <div className="ind-page"><header className="man-bar"><button type="button" className="secondary" onClick={back}><ArrowLeft size={15}/> Back</button><b>iSift for {x.name}</b><span className="sp"/>
      <a className="primary" href="#/website" onClick={e=>{if(onSignup){e.preventDefault();onSignup()}}}>Start free</a></header>
    <main className="ind-main">
      <section className="ind-hero"><span className="why-ic"><x.icon size={22}/></span><h1>{x.line}</h1><p>{x.intro}</p></section>
      <section className="ind-cols"><div><h2>What gets in the way</h2><ul>{x.pains.map(p=><li key={p}>{p}</li>)}</ul></div>
        <div><h2>How iSift fits</h2><ul className="ind-fits">{x.fits.map(p=><li key={p}><Check size={15}/> {p}</li>)}</ul></div></section>
      <section><h2>Meetings you can set up today</h2><div className="ind-chips">{x.uses.map(u=><span key={u}>{u}</span>)}</div></section>
      <section className="ind-note"><h2>Worth checking for your sector</h2><ul>{x.checks.map(p=><li key={p}>{p}</li>)}</ul>
        <p className="muted small">General information only, not legal advice. Check the rules that apply to your business.</p></section>
      <section><h2>Other industries</h2><div className="ind-chips">{others.map(o=><a key={o.slug} href={`#/industry/${o.slug}`}>{o.name}</a>)}</div></section>
    </main></div>;
}
