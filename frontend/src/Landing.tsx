import React from 'react';
import {Check,X,Minus,Layers,ListChecks,ShieldCheck,CalendarClock,FileSignature,Armchair,Lock,Phone,BadgeDollarSign,Presentation,Mail,BookOpen,Download,ArrowLeft,Hand,ArrowRight,Users,LayoutGrid,MonitorUp,PlayCircle} from 'lucide-react';
import {useLivePlans,money} from './Pricing';

/** Landing page sections: what happens after a meeting, why iSift, an honest comparison, and how data is handled. */

export function OutcomeSection(){
  return <section className="landing-section" id="outcome"><p className="eyebrow">THE DIFFERENCE</p><h2>The meeting ends. The work is already sorted.</h2>
    <div className="ba-grid">
      <div className="ba-card before"><h3>With most meeting tools</h3><ul>
        <li>The call ends and you are left with a recording.</li><li>You write the minutes from memory, an hour later.</li><li>Actions live in someone’s notebook and get chased by email.</li><li>Booking, mail, documents and PDFs are four other apps.</li></ul></div>
      <div className="ba-arrow" aria-hidden="true"><ArrowRight size={26}/></div>
      <div className="ba-card after"><h3>With iSift</h3><ul>
        <li><Check size={15}/> Minutes are drafted from the transcript, and a person reviews them before they go out.</li>
        <li><Check size={15}/> Every action item has an owner and a due date, and shows up where the work happens.</li>
        <li><Check size={15}/> A morning briefing tells you what is on today and what is still open.</li>
        <li><Check size={15}/> Booking, webinars, your own email address, calendar, notes, whiteboard and PDF signing sit beside the meeting.</li></ul></div>
    </div></section>;
}

const WHY=[
 {i:Layers,t:'One workspace, not six tabs',d:'Video meetings, a Calendly-style booking page, mail, calendar and contacts, notes, whiteboard and PDF signing, all signed in once and all linked to the meeting they belong to.'},
 {i:ListChecks,t:'Follow-through, not just a summary',d:'Most tools stop at a recap. iSift turns the conversation into minutes, owned action items and a briefing before your next meeting.'},
 {i:ShieldCheck,t:'AI-empowered, human-approved',d:'Draft minutes and actions are marked for review. Nothing is sent as final until someone checks it, which matters for clients, boards and regulated work.'},
 {i:CalendarClock,t:'Booking pages built in',d:'Share a link and let people pick a free time. Each booking lands in your calendar with a meeting room attached. No second subscription.'},
 {i:FileSignature,t:'Edit and sign PDFs in the browser',d:'Change text, add shapes, draw a signature, sign with your own certificate. The file is not stored on our servers.'},
 {i:LayoutGrid,t:'A meeting screen that feels like Zoom',d:'A clean toolbar with only what you need, and a More menu for the rest: pin the tools you use. Reactions, raise hand, live captions with a saveable transcript, waiting room, lock meeting and hide profile pictures. On a phone you are large on the first screen and everyone else swipes in after.'},
 {i:MonitorUp,t:'Share together, point and draw',d:'Share a whole screen, one window or one browser tab, with its sound. Let several people share at once, side by side, and hand someone the pen to point and draw on your screen, then take it back.'},
 {i:PlayCircle,t:'Watch a video together',d:'Paste a YouTube link and everyone watches in sync on their own device, phones included. You play, pause and skip for the whole meeting.'},
 {i:Armchair,t:'Meeting rooms people enjoy',d:'A virtual boardroom with a wooden table, name plates, windows and your own background, or a simple gallery view. Switch with one button.'},
 {i:Phone,t:'Call a teammate in one click',d:'Ring another iSift user like a phone call. They accept and you are in a private room together.'},
 {i:Presentation,t:'Webinars you run like Zoom or Webex',d:'Registration pages with your own questions, panelists, a practice session before you go live, and attendees who can only watch. You mute people or turn their video off, and invite one person or a group to speak. Attendee questions come to you privately, with Q&A, upvotes, polls and raise hand. Afterwards get attendance, question and poll reports as CSV, and send follow-up emails.'},
 {i:Mail,t:'Your own email address, set up in minutes',d:'Get a name@isift address or use your own domain with mailboxes for your team. Phones and Outlook or Thunderbird are set up from one page, with built-in spam and abuse protection, inside the same Commbox as your calendar and contacts.'},
 {i:Lock,t:'You stay in control',d:'Basic hosts save recordings on their own computer when the meeting ends; paid plans store them in the cloud and email a download link. Administrators set what each person may use: call time, recording, documents, Commbox and more.'},
 {i:BadgeDollarSign,t:'Plain, local pricing',d:'Free, Standard and Business. Pick how many participants you need from a dropdown, in your currency, and yearly saves you money. No per-feature add-ons to work out.'},
];
export function WhySection(){
  return <section className="landing-section" id="why-isift"><p className="eyebrow">WHY ISIFT</p><h2>Everything around the meeting, in one calm place.</h2>
    <p className="why-lead">iSift is built for people whose work happens in meetings: advisers, consultants, small teams and anyone who is tired of stitching tools together.</p>
    <div className="why-grid">{WHY.map(w=><article key={w.t} className="why-card"><span className="why-ic"><w.i size={20}/></span><h3>{w.t}{/AI/.test(w.t)&&<i className="ai-tag">AI</i>}</h3><p>{w.d}</p></article>)}</div></section>;
}

type Cell=string|true|false|null;
const Y=true,N=false;
const COLS=['iSift','Zoom','Zoho Meeting','Webex','GoTo Meeting','Microsoft Teams','Google Meet'];
const SUB=['','','','','','',''];
const ROWS:{label:string;cells:Cell[]}[]=[
 {label:'Video meetings in the browser',cells:[Y,Y,Y,Y,Y,Y,Y]},
 {label:'Free plan: group meeting length',cells:['90 minutes','40 minutes','60 minutes','40 minutes','Trial only','60 minutes','60 minutes']},
 {label:'People in one meeting on paid plans',cells:['10 to 300, the size you choose and pay for','100 (Pro)','10 to 250, by size','150 to 1,000, by plan','150 to 250, by plan','300','100 to 500, by plan']},
 {label:'Meeting recording',cells:['Yes, built in. Basic: saved on the host\u2019s computer at the end of the meeting. Paid: stored in the cloud, download link emailed to the host','Paid plans','Included, 5 GB cloud','Local free, cloud on paid plans','Cloud recording on paid plans','Paid plans','Paid plans']},
 {label:'AI minutes and action items',cells:['Yes, built in, AI drafts and a person reviews','Yes (paid plans)',null,'AI Assistant (paid plans)','Business plan','Needs Copilot add-on','Gemini, paid plans']},
 {label:'Mail, calendar and contacts in the same app',cells:['Yes, built in (paid plans)','Some','Zoho Mail, separate',N,N,'Outlook, separate','Gmail, separate']},
 {label:'Your own email address or domain, set up for you',cells:['Yes, built in, with team mailboxes (paid plans)','No','Zoho Mail, separate','No','No','Outlook, separate','Gmail, separate']},
 {label:'Whiteboard',cells:[Y,Y,Y,Y,'Drawing tools','Paid plans','Separate app']},
 {label:'Notes (linked to your meetings)',cells:['Yes, built in, linked to each meeting','Zoom Notes','Separate Zoho app',null,N,'OneNote or Loop, separate','Separate app']},
 {label:'Word processor documents (WordPerfect)',cells:['Yes, built in, share and co-write','Zoom Docs','Zoho Writer, separate','No','No','Word, separate','Google Docs, separate']},
 {label:'Spreadsheets (SpreadTable)',cells:['Yes, built in, with formulas','Tables in Zoom Docs','Zoho Sheet, separate','No','No','Excel, separate','Google Sheets, separate']},
 {label:'Presentations (PowerPresentation)',cells:['Yes, built in, present in the meeting','No','Zoho Show, separate','No','No','PowerPoint, separate','Google Slides, separate']},
 {label:'PDF and Word editor: edit text, delete or replace pictures',cells:['Yes, built in (PDFs of up to 5 pages free)','Separate app','Separate app','Separate app','Separate app','Separate app','Separate app']},
 {label:'Sign PDFs: drawn signature or certified digital signature',cells:['Yes, built in, in the same app','Separate app','Zoho Sign, separate','Separate app','Separate app','Separate app','Separate app']},
 {label:'Reactions, raise hand and live captions',cells:[Y,Y,null,Y,null,Y,Y]},
 {label:'Several people sharing at once, with pointer and pen',cells:['Yes, built in (paid plans)','Yes (host option)',null,null,null,null,null]},
 {label:'Watch a YouTube video together, in sync',cells:['Yes, built in (paid plans)',null,null,null,null,null,null]},
 {label:'Take control of someone’s computer',cells:['Give anyone control of a shared PDF or photo to page and scroll it, or hand them the pen on a shared screen. Take it back any time',Y,Y,Y,Y,Y,null]},
 {label:'Call another user inside the app',cells:['Yes, built in (paid plans)',Y,null,Y,null,Y,Y]},
 {label:'Webinars: registration, panelists, private Q&A, polls, reports',cells:['Yes, built in (paid plans)','Separate product','Separate product','Webex Webinars','GoTo Webinar (separate)','Teams Premium','Paid plans']},
];
function Mark({v}:{v:Cell}){
  if(v===true)return <span className="cmp-yes" aria-label="Yes"><Check size={16}/></span>;
  if(v===false)return <span className="cmp-no" aria-label="No"><X size={15}/></span>;
  if(v===null)return <span className="cmp-na" aria-label="Not stated"><Minus size={14}/></span>;
  return <span className="cmp-txt">{v}</span>;
}
export function CompareSection(){
  const live=useLivePlans();
  // the cheapest way in: the lowest price on sale, over every paid plan and every size on the Pricing page (so it follows the administrator's changes)
  const opts=(['individual','business'] as const).filter(id=>live.onSale(id)).flatMap(id=>live.tiersOf(id).map(t=>({id,n:t.n,v:live.prices(id,t.n).perMonthYearly}))).filter(o=>o.v>0).sort((a,b)=>a.v-b.v);
  const best=opts[0];
  const price:Cell[]=[best?`${money(best.v,live.currency)} a month (${best.n} people)`:'Free','US$14.16 (Pro)','From US$1 (10 people)','A$17.50 (Starter)','From about US$12 (Professional)','Part of Microsoft 365','US$7 (Workspace Starter)'];
  return <section className="landing-section" id="compare"><p className="eyebrow">HOW ISIFT COMPARES</p><h2>Where iSift fits next to the tools you already know.</h2>
    <p className="why-lead">Zoom, Webex, GoTo Meeting and Teams are built for large and managed meetings, and Zoho Meeting is the closest on price. iSift brings meetings, notes, whiteboard, booking and mail together for one person or a small team, and you pay only for the number of people you need in a meeting.</p>
    <div className="cmp-wrap" role="region" aria-label="Comparison table" tabIndex={0}><table className="cmp">
      <thead><tr><th scope="col"></th>{COLS.map((c,i)=><th key={c} scope="col" className={i===0?'me':''}>{c}{SUB[i]&&<small>{SUB[i]}</small>}</th>)}</tr></thead>
      <tbody>{ROWS.map(r=><tr key={r.label}><th scope="row">{r.label}</th>{r.cells.map((c,i)=><td key={i} className={i===0?'me':''}><Mark v={c}/></td>)}</tr>)}
        <tr><th scope="row">Paid plan from (billed yearly, per host)</th>{price.map((c,i)=><td key={i} className={i===0?'me':''}><Mark v={c}/></td>)}</tr></tbody></table></div>
    <p className="cmp-note">Based on each product’s published plans, checked in October 2026; a dash means we could not confirm it. Competitor prices are US dollars except Webex, which is Australian dollars; iSift’s price is in {live.currency}. Plans and features change, so check each vendor before you decide. “Separate app” means it is not part of the core product. iSift does not do webinars, very large meetings, calls to phone numbers or remote control of another computer yet.</p></section>;
}

export function TrustSection(){
  const items=[
   ['Encrypted connection','All traffic uses HTTPS. Passwords are stored as salted hashes, and saved API keys are encrypted.'],
   ['Recordings stay with you','Basic hosts save the recording on their own computer when the meeting ends. On paid plans it is stored in the cloud and a download link is emailed to the host.'],
   ['Your files are not kept','PDFs you edit or sign are processed for your request and sent straight back. They are not stored.'],
   ['A person approves the AI','Minutes and action items are drafts until someone reviews them. The Privacy page lists every provider we use and what it does.'],
  ];
  return <section className="landing-section" id="trust"><p className="eyebrow">TRUST</p><h2>Clear about your data.</h2>
    <div className="why-grid four">{items.map(([t,d])=><article key={t} className="why-card"><span className="why-ic"><ShieldCheck size={20}/></span><h3>{t}</h3><p>{d}</p></article>)}</div></section>;
}


/* ---------------------------------------------------------------- what is new, why iSift, manuals */
export const MANUALS:{slug:string;t:string;d:string;pages:number}[]=[
 {slug:'meetings-and-sharing',t:'Meetings and sharing',d:'Start and join meetings, manage people, share a file and give someone control of it.',pages:7},
 {slug:'webinars',t:'Webinars',d:'Register people, run a practice session, answer private questions, run polls and let people speak.',pages:10},
 {slug:'booking-and-follow-up',t:'Booking, minutes and action items',d:'Booking pages, reviewed minutes, owned action items and the morning briefing.',pages:4},
 {slug:'mail-calendar-contacts',t:'Mail, calendar and contacts',d:'Commbox: add a mail account, use your calendar and look after contacts.',pages:3},
 {slug:'documents-and-whiteboard',t:'Documents, PDF signing and whiteboard',d:'WordPerfect, SpreadTable, PowerPresentation, Sign and Edit PDF and the whiteboard.',pages:4},
];

export function NewSection(){
  const items=[
   {i:Presentation,t:'Webinars',d:'Run webinars with registration, panelists, polls, Q&A and reports. Attendees only watch.',m:'webinars'},
   {i:Hand,t:'Give control of a file',d:'Share a PDF or photo and let one person page and scroll it for everyone. Take it back any time.',m:'meetings-and-sharing'},
   {i:Mail,t:'Your own email address',d:'An iSift address in minutes, or your own domain with team mailboxes.',m:'mail-calendar-contacts'},
   {i:Users,t:'Simple host controls',d:'Mute people, turn off video or invite someone to speak, all from one small menu beside each person.',m:'meetings-and-sharing'},
  ];
  return <section className="landing-section" id="whats-new"><p className="eyebrow">WHAT’S NEW</p><h2>New in iSift.</h2>
    <div className="why-grid four new-grid">{items.map(w=><article key={w.t} className="why-card new-card"><span className="why-ic"><w.i size={20}/></span><span className="new-tag">New</span><h3>{w.t}</h3><p>{w.d}</p><a className="new-link" href={`#/manual/${w.m}`}>Read the manual <ArrowRight size={14}/></a></article>)}</div></section>;
}

export function BetterSection(){
  const rows=[
   ['Everything in one place','Zoom, Zoho, Teams, Webex, GoTo and Meet each cover meetings; notes, whiteboard, documents, PDF signing, booking and mail usually mean other apps or add-ons. In iSift they sit beside the meeting.'],
   ['Webinars are included','Webinars are a separate product or an add-on with Zoom, Zoho, GoTo and Teams. In iSift they are part of the paid plans, with registration, Q&A, polls and reports.'],
   ['You pay for the people you need','Choose how many participants you need from a dropdown. No per-feature add-ons to work out.'],
   ['A free plan with 90-minute meetings','Group meetings on the free plan run for 90 minutes, longer than the free plans of Zoom, Webex and Meet.'],
   ['AI that a person approves','Minutes and action items are drafts until someone reviews them, which matters for clients, boards and regulated work.'],
   ['Control without installing anything','Share a file and give someone control of it, mute and manage people and run a webinar, all in the browser.'],
  ];
  return <section className="landing-section" id="why-better"><p className="eyebrow">WHY ISIFT</p><h2>Why people choose iSift over Zoom, Zoho, Teams, Meet and the rest.</h2>
    <div className="why-grid">{rows.map(([t,d])=><article key={t} className="why-card"><span className="why-ic"><Check size={20}/></span><h3>{t}</h3><p>{d}</p></article>)}</div>
    <p className="cmp-note">Comparisons reflect each product’s published plans in October 2026. See the table above for details, and check each vendor before you decide.</p></section>;
}

export function ManualsSection(){
  return <section className="landing-section" id="manuals"><p className="eyebrow">USER MANUALS</p><h2>Step-by-step manuals with screenshots.</h2>
    <p className="why-lead">One short manual for each group of features. Open it here, or download the PDF.</p>
    <div className="why-grid">{MANUALS.map(m=><article key={m.slug} className="why-card man-card"><span className="why-ic"><BookOpen size={20}/></span><h3>{m.t}</h3><p>{m.d}</p><small className="muted">{m.pages} pages, PDF</small>
      <div className="man-act"><a className="primary" href={`#/manual/${m.slug}`}>Open</a><a className="secondary" href={`/manuals/${m.slug}.pdf`} download={`iSift-${m.slug}.pdf`}><Download size={14}/> Download</a></div></article>)}</div></section>;
}

export function ManualViewer({slug}:{slug:string}){
  const m=MANUALS.find(x=>x.slug===slug);const src=`/manuals/${slug}.pdf`;
  const back=()=>{if(history.length>1)history.back();else location.hash='#/website'};
  return <div className="man-view"><header className="man-bar"><button type="button" className="secondary" onClick={back}><ArrowLeft size={15}/> Back</button><b>{m?m.t:'Manual'}</b>
    <span className="sp"/>{m&&<a className="primary" href={src} download={`iSift-${slug}.pdf`}><Download size={14}/> Download PDF</a>}</header>
    {m?<><iframe className="man-frame" title={m.t} src={src+'#view=FitH'}/><p className="muted small man-fallback">The manual does not show? <a href={src} target="_blank" rel="noopener">Open the PDF directly</a>.</p></>:<p className="syncerr" role="alert">That manual was not found.</p>}</div>;
}
