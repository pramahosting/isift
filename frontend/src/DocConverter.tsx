import React,{useEffect,useRef,useState} from 'react';
import {FileText,Table2,Presentation,FileDown,FileUp,ArrowRight,CheckCircle2,LoaderCircle,CircleAlert,Clock} from 'lucide-react';
import {convertSaved,importOffice,uploadToPdf,pdfToDocx} from './docConvert';

type Mode='wp-pdf'|'pdf-wp'|'deck-pdf'|'sheet-pdf'|'office-open';
const MODES:{id:Mode;from:string;to:string;kind?:'wp'|'sheet'|'deck';icon:any;text:string}[]=[
  {id:'wp-pdf',from:'WordPerfect',to:'PDF',kind:'wp',icon:FileText,text:'Your documents as PDFs, laid out like the page you see.'},
  {id:'pdf-wp',from:'PDF',to:'WordPerfect',icon:FileUp,text:'Turn PDFs into documents you can edit and share, or Word files.'},
  {id:'deck-pdf',from:'PowerPresentation',to:'PDF',kind:'deck',icon:Presentation,text:'Every slide as a PDF page, with its colours and shapes.'},
  {id:'sheet-pdf',from:'SpreadTable',to:'PDF',kind:'sheet',icon:Table2,text:'Every sheet as a PDF, showing the worked-out values.'},
  {id:'office-open',from:'Word, Excel or PowerPoint',to:'iSift',icon:FileUp,text:'Open .docx, .xlsx or .pptx files to edit them here, then download them in the same format.'}];
const ACCEPT:Record<string,string>={'wp-pdf':'.docx,.html,.htm,.txt','deck-pdf':'.pptx','sheet-pdf':'.xlsx','pdf-wp':'application/pdf,.pdf','office-open':'.docx,.xlsx,.pptx'};
const PARALLEL=3;   // files converted at the same time from this screen (the server converts each in its own worker)
const readB64=(f:File)=>new Promise<string>((ok,no)=>{const r=new FileReader();r.onload=()=>ok(String(r.result).split(',')[1]||'');r.onerror=()=>no(new Error('The file could not be read.'));r.readAsDataURL(f)});

type Job={key:string;name:string;state:'wait'|'run'|'done'|'err';msg?:string;open?:{kind:string;id:string}};

/** Doc Converter: many files at once. WordPerfect, PowerPresentation and SpreadTable (saved or from the computer) to PDF, PDFs to WordPerfect or Word, and Word / Excel / PowerPoint files into the editors. */
export function DocConverter({request,onOpen}:{request:any;onOpen:(kind:string,id:string)=>void}){
  const [mode,setMode]=useState<Mode>('wp-pdf');const m=MODES.find(x=>x.id===mode)!;
  const [saved,setSaved]=useState<any[]>([]);const [picks,setPicks]=useState<string[]>([]);const [ups,setUps]=useState<File[]>([]);const [look,setLook]=useState<'exact'|'flow'>('exact');
  const [jobs,setJobs]=useState<Job[]>([]);const busy=jobs.some(j=>j.state==='wait'||j.state==='run');const fileIn=useRef<HTMLInputElement>(null);
  useEffect(()=>{setJobs([]);setPicks([]);setUps([]);if(!m.kind){setSaved([]);return}
    Promise.all([request(`/notes?kind=${m.kind}`).catch(()=>[]),request(`/shared/with-me?kind=${m.kind}`).catch(()=>[])]).then(([mine,withMe])=>{
      setSaved([...(mine||[]).map((n:any)=>({id:n.id,title:n.title,note:''})),...(withMe||[]).map((n:any)=>({id:n.id,title:n.title,note:` (from ${n.owner})`}))])})},[mode]);
  const patch=(key:string,p:Partial<Job>)=>setJobs(js=>js.map(j=>j.key===key?{...j,...p}:j));
  /** Runs every job, PARALLEL at a time, and shows each one's progress as it goes. */
  const runAll=async(list:{key:string;name:string;go:()=>Promise<Partial<Job>|void>}[])=>{
    setJobs(list.map(j=>({key:j.key,name:j.name,state:'wait' as const})));
    let next=0;const worker=async()=>{while(next<list.length){const j=list[next++];patch(j.key,{state:'run'});
      try{const r=await j.go();patch(j.key,{state:'done',...(r||{})})}catch(e:any){patch(j.key,{state:'err',msg:e?.message||'The conversion did not finish.'})}}};
    await Promise.all(Array.from({length:Math.min(PARALLEL,list.length)},worker))};
  const startPdf=()=>{const list:any[]=[];
    ups.forEach((f,i)=>list.push({key:'u'+i,name:f.name,go:async()=>{await uploadToPdf(request,f);return {msg:'Downloaded as PDF'}}}));
    picks.forEach(id=>{const s=saved.find(x=>x.id===id);list.push({key:'s'+id,name:s?.title||'Untitled',go:async()=>{const n=await request(`/notes/${id}`);await convertSaved(request,m.kind!,'pdf',n.title||'file',n.content||'');return {msg:'Downloaded as PDF'}}})});
    runAll(list)};
  const startPdfWp=(word:boolean)=>runAll(ups.map((f,i)=>({key:'p'+i,name:f.name,go:async()=>{
    if(word){const notes=await pdfToDocx(request,f,look);return {msg:'Downloaded as Word (.docx)'+(notes?.length?'. '+notes.join(' '):'')}}
    const r=await request('/docs/pdf-to-wp',{method:'POST',body:JSON.stringify({name:f.name,data:await readB64(f),mode:look})});
    const title=f.name.replace(/\.pdf$/i,'').slice(0,150)||'Converted PDF';
    const n=await request('/notes',{method:'POST',body:JSON.stringify({kind:'wp',title,content:r.html})});
    return {msg:`In WordPerfect (${r.pages} ${r.pages===1?'page':'pages'})`+((r.notes||[]).length?'. '+r.notes.join(' '):''),open:{kind:'wp',id:n.id}}}})));
  const startOffice=()=>runAll(ups.map((f,i)=>({key:'o'+i,name:f.name,go:async()=>{
    const r=await importOffice(request,f);const n=await request('/notes',{method:'POST',body:JSON.stringify({kind:r.kind,title:r.title.slice(0,150),content:r.content})});
    return {msg:`In ${r.kind==='wp'?'WordPerfect':r.kind==='sheet'?'SpreadTable':'PowerPresentation'}.`+((r.notes||[]).length?' '+r.notes.join(' '):''),open:{kind:r.kind,id:n.id}}}})));
  const choose=(e:React.ChangeEvent<HTMLInputElement>)=>{setUps(Array.from(e.target.files||[]));setJobs([]);e.target.value=''};
  const label=ups.length?(ups.length===1?ups[0].name:`${ups.length} files chosen`):(mode==='pdf-wp'?'Choose PDFs from your computer':`Choose files from your computer (${ACCEPT[mode]})`);
  const Icon=(j:Job)=>j.state==='done'?<CheckCircle2 size={15} className="ok"/>:j.state==='err'?<CircleAlert size={15} className="bad"/>:j.state==='run'?<LoaderCircle size={15} className="spin"/>:<Clock size={15}/>;
  return <div className="dconv">
    <div className="dconv-modes" role="tablist" aria-label="Conversion">{MODES.map(x=>{const I=x.icon;return <button key={x.id} type="button" role="tab" aria-selected={mode===x.id} className={`dconv-mode${mode===x.id?' on':''}`} onClick={()=>setMode(x.id)}><I size={20}/><b>{x.from} <ArrowRight size={13}/> {x.to}</b><small>{x.text}</small></button>})}</div>
    <section className="panel dconv-panel">
      <h2>{m.from} to {m.to}</h2>
      {mode==='office-open'?<p className="muted">Choose Word (.docx), Excel (.xlsx) or PowerPoint (.pptx) files, as many as you like. Each opens as a new file in WordPerfect, SpreadTable or PowerPresentation, where you can edit it. Download it again as .docx, .xlsx or .pptx from the Download button.</p>
        :mode==='pdf-wp'?<>
        <p className="muted">Choose one or many PDFs. They are converted at the same time. Each can become a WordPerfect document in your list, or be downloaded straight as a Word file.</p>
        <fieldset className="dconv-look"><legend className="small muted">How should the pages come out?</legend>
          <label><input type="radio" name="look" checked={look==='exact'} onChange={()=>setLook('exact')}/> <b>Exactly as the PDF looks</b> (recommended): colours, shapes, pictures and layout stay; the text stays editable.</label>
          <label><input type="radio" name="look" checked={look==='flow'} onChange={()=>setLook('flow')}/> <b>Editable text flow</b>: the text re-flows like a normal document, for long text-only PDFs.</label></fieldset></>
        :<p className="muted">Choose files from your computer, or tick files saved in iSift, as many as you like. They are converted at the same time and each PDF downloads as soon as it is ready. The PDF keeps its colours, fonts, pictures and layout. Your originals are not changed.</p>}
      <div className="actions"><button type="button" className="secondary" onClick={()=>fileIn.current?.click()}><FileUp size={15}/> {label}</button>
        <input ref={fileIn} type="file" multiple accept={ACCEPT[mode]} hidden onChange={choose}/>{ups.length>0&&<button type="button" className="textbtn" onClick={()=>{setUps([]);setJobs([])}}>Clear</button>}</div>
      {m.kind&&(saved.length?<fieldset className="dconv-saved"><legend className="small muted">Or tick files saved in iSift</legend>
        {saved.map(f=><label key={f.id}><input type="checkbox" checked={picks.includes(f.id)} onChange={e=>setPicks(p=>e.target.checked?[...p,f.id]:p.filter(x=>x!==f.id))}/> {f.title||'Untitled'}{f.note}</label>)}</fieldset>
        :<p className="muted small">You have no {m.from} files saved in iSift yet. Choose some from your computer above.</p>)}
      <div className="actions">
        {m.kind&&<button type="button" className="primary" disabled={busy||(!ups.length&&!picks.length)} onClick={startPdf}><FileDown size={15}/> Convert {ups.length+picks.length>1?`${ups.length+picks.length} files`:'and download PDF'}</button>}
        {mode==='pdf-wp'&&<><button type="button" className="primary" disabled={busy||!ups.length} onClick={()=>startPdfWp(false)}>Convert to WordPerfect</button>
          <button type="button" className="primary" disabled={busy||!ups.length} onClick={()=>startPdfWp(true)}><FileDown size={15}/> Download as Word (.docx)</button></>}
        {mode==='office-open'&&<button type="button" className="primary" disabled={busy||!ups.length} onClick={startOffice}>Open to edit</button>}</div>
      {jobs.length>0&&<ul className="dconv-jobs" aria-live="polite">{jobs.map(j=><li key={j.key} className={j.state}><span className="dconv-ic">{Icon(j)}</span><span className="dconv-nm">{j.name}</span>
        <small className={j.state==='err'?'syncerr':'muted'}>{j.state==='wait'?'Waiting':j.state==='run'?'Converting…':j.msg||''}</small>
        {j.open&&<button type="button" className="textbtn" onClick={()=>onOpen(j.open!.kind,j.open!.id)}>Open</button>}</li>)}</ul>}
      {jobs.length>1&&!busy&&<p className="muted small" role="status">{jobs.filter(j=>j.state==='done').length} of {jobs.length} done{jobs.some(j=>j.state==='err')?', some failed':''}. If your browser asks to allow several downloads, choose Allow.</p>}
      <p className="muted small">Also in each editor: the Download button offers PDF and the original format (Word, Excel or PowerPoint).</p>
    </section></div>;
}
