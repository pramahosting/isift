import React,{useEffect,useRef,useState} from 'react';
import {FileText,Table2,Presentation,FileDown,FileUp,ArrowRight,CheckCircle2,LoaderCircle} from 'lucide-react';
import {convertSaved,importOffice,uploadToPdf,pdfToDocx} from './docConvert';

type Mode='wp-pdf'|'pdf-wp'|'deck-pdf'|'sheet-pdf'|'office-open';
const MODES:{id:Mode;from:string;to:string;kind?:'wp'|'sheet'|'deck';icon:any;text:string}[]=[
  {id:'wp-pdf',from:'WordPerfect',to:'PDF',kind:'wp',icon:FileText,text:'Your document as a PDF, laid out like the page you see.'},
  {id:'pdf-wp',from:'PDF',to:'WordPerfect',icon:FileUp,text:'Turn a PDF into a document you can edit and share.'},
  {id:'deck-pdf',from:'PowerPresentation',to:'PDF',kind:'deck',icon:Presentation,text:'Every slide as a PDF page, with its colours and shapes.'},
  {id:'sheet-pdf',from:'SpreadTable',to:'PDF',kind:'sheet',icon:Table2,text:'Every sheet as a PDF, showing the worked-out values.'},
  {id:'office-open',from:'Word, Excel or PowerPoint',to:'iSift',icon:FileUp,text:'Open a .docx, .xlsx or .pptx file to edit it here, then download it in the same format.'}];
const readB64=(f:File)=>new Promise<string>((ok,no)=>{const r=new FileReader();r.onload=()=>ok(String(r.result).split(',')[1]||'');r.onerror=()=>no(new Error('The file could not be read.'));r.readAsDataURL(f)});

/** Doc Converter: WordPerfect, PowerPresentation and SpreadTable files to PDF, and a PDF into a WordPerfect document. */
export function DocConverter({request,onOpen}:{request:any;onOpen:(kind:string,id:string)=>void}){
  const [mode,setMode]=useState<Mode>('wp-pdf');const m=MODES.find(x=>x.id===mode)!;
  const [files,setFiles]=useState<any[]>([]);const [pick,setPick]=useState('');const [busy,setBusy]=useState(false);const [err,setErr]=useState('');const [done,setDone]=useState<any>(null);
  const [pdf,setPdf]=useState<File|null>(null);const [ms,setMs]=useState<File|null>(null);const [up,setUp]=useState<File|null>(null);const upIn=useRef<HTMLInputElement>(null);const [look,setLook]=useState<'exact'|'flow'>('exact');const fileIn=useRef<HTMLInputElement>(null);
  useEffect(()=>{setErr('');setDone(null);setPick('');setUp(null);if(!m.kind){setFiles([]);return}
    Promise.all([request(`/notes?kind=${m.kind}`).catch(()=>[]),request(`/shared/with-me?kind=${m.kind}`).catch(()=>[])]).then(([mine,withMe])=>{
      const l=[...(mine||[]).map((n:any)=>({id:n.id,title:n.title,note:''})),...(withMe||[]).map((n:any)=>({id:n.id,title:n.title,note:` (from ${n.owner})`}))];setFiles(l);if(l.length)setPick(l[0].id)})},[mode]);
  const run=async()=>{setErr('');setDone(null);setBusy(true);
    try{
      if(mode==='office-open'){
        if(!ms)throw new Error('Choose a Word, Excel or PowerPoint file first.');
        const r=await importOffice(request,ms);const n=await request('/notes',{method:'POST',body:JSON.stringify({kind:r.kind,title:r.title.slice(0,150),content:r.content})});
        setDone({id:n.id,title:r.title,kind:r.kind,notes:r.notes||[],opened:true});
      }else if(mode==='pdf-wp'){
        if(!pdf)throw new Error('Choose a PDF first.');
        const r=await request('/docs/pdf-to-wp',{method:'POST',body:JSON.stringify({name:pdf.name,data:await readB64(pdf),mode:look})});
        const title=pdf.name.replace(/\.pdf$/i,'').slice(0,150)||'Converted PDF';
        const n=await request('/notes',{method:'POST',body:JSON.stringify({kind:'wp',title,content:r.html})});
        setDone({id:n.id,title,pages:r.pages,notes:r.notes||[]});
      }else if(up){
        await uploadToPdf(request,up);setDone({title:up.name,pdf:true});
      }else{
        if(!pick)throw new Error('Choose a file first.');
        const n=await request(`/notes/${pick}`);await convertSaved(request,m.kind!,'pdf',n.title||'file',n.content||'');
        setDone({title:n.title,pdf:true});
      }
    }catch(e:any){setErr(e?.message||'The conversion did not finish.')}finally{setBusy(false)}};
  const toWord=async()=>{setErr('');setDone(null);setBusy(true);try{if(!pdf)throw new Error('Choose a PDF first.');const n=await pdfToDocx(request,pdf,look);setDone({title:pdf.name,word:true,notes:n||[]})}catch(e:any){setErr(e?.message||'The conversion did not finish.')}finally{setBusy(false)}};
  const ACCEPT:Record<string,string>={'wp-pdf':'.docx,.html,.htm,.txt','deck-pdf':'.pptx','sheet-pdf':'.xlsx'};
  return <div className="dconv">
    <div className="dconv-modes" role="tablist" aria-label="Conversion">{MODES.map(x=>{const I=x.icon;return <button key={x.id} type="button" role="tab" aria-selected={mode===x.id} className={`dconv-mode${mode===x.id?' on':''}`} onClick={()=>setMode(x.id)}><I size={20}/><b>{x.from} <ArrowRight size={13}/> {x.to}</b><small>{x.text}</small></button>})}</div>
    <section className="panel dconv-panel">
      <h2>{m.from} to {m.to}</h2>
      {mode==='office-open'?<>
        <p className="muted">Choose a Word (.docx), Excel (.xlsx) or PowerPoint (.pptx) file. It opens as a new file in WordPerfect, SpreadTable or PowerPresentation, where you can edit it. Download it again as .docx, .xlsx or .pptx from the Download button.</p>
        <div className="actions"><button type="button" className="secondary" onClick={()=>fileIn.current?.click()}><FileUp size={15}/> {ms?ms.name:'Choose a file'}</button><input ref={fileIn} type="file" accept=".docx,.xlsx,.pptx" hidden onChange={e=>{setMs(e.target.files?.[0]||null);setDone(null);setErr('');e.target.value=''}}/>
          <button type="button" className="primary" disabled={busy||!ms} onClick={run}>{busy?<><LoaderCircle size={15} className="spin"/> Opening…</>:<>Open to edit</>}</button></div>
      </>:mode==='pdf-wp'?<>
        <p className="muted">Choose a PDF. iSift rebuilds it as a new WordPerfect document in your list, with headings, bold and italic, text colours, lists, tables and pictures. A PDF is a fixed page, so page breaks and exact positions are not kept, and a scanned page is placed as a picture.</p>
        <fieldset className="dconv-look"><legend className="small muted">How should the pages come out?</legend>
          <label><input type="radio" name="look" checked={look==='exact'} onChange={()=>setLook('exact')}/> <b>Exactly as the PDF looks</b> (recommended): colours, shapes, pictures and layout stay; the text stays editable.</label>
          <label><input type="radio" name="look" checked={look==='flow'} onChange={()=>setLook('flow')}/> <b>Editable text flow</b>: the text re-flows like a normal document, for long text-only PDFs.</label></fieldset>
        <div className="actions"><button type="button" className="secondary" onClick={()=>fileIn.current?.click()}><FileUp size={15}/> {pdf?pdf.name:'Choose a PDF from your computer'}</button><input ref={fileIn} type="file" accept="application/pdf,.pdf" hidden onChange={e=>{setPdf(e.target.files?.[0]||null);setDone(null);setErr('');e.target.value=''}}/>
          <button type="button" className="primary" disabled={busy||!pdf} onClick={run}>{busy?<><LoaderCircle size={15} className="spin"/> Converting…</>:<>Convert to WordPerfect</>}</button>
          <button type="button" className="primary" disabled={busy||!pdf} onClick={toWord}><FileDown size={15}/> Download as Word (.docx)</button></div>
      </>:<>
        <p className="muted">Choose a file from your computer or one saved in iSift. The PDF keeps its colours, fonts, pictures and layout, and downloads straight away. Your original file is not changed.</p>
        <div className="actions"><button type="button" className="secondary" onClick={()=>upIn.current?.click()}><FileUp size={15}/> {up?up.name:`Choose a file from your computer (${ACCEPT[mode]})`}</button><input ref={upIn} type="file" accept={ACCEPT[mode]} hidden onChange={e=>{setUp(e.target.files?.[0]||null);setDone(null);setErr('');e.target.value=''}}/>{up&&<button type="button" className="textbtn" onClick={()=>setUp(null)}>Use a saved file instead</button>}</div>
        {!up&&(files.length?<label className="dconv-pick">Or a file saved in iSift<select value={pick} onChange={e=>{setPick(e.target.value);setDone(null)}} aria-label={`Choose a ${m.from} file`}>{files.map(f=><option key={f.id} value={f.id}>{f.title||'Untitled'}{f.note}</option>)}</select></label>:<p className="muted">You have no {m.from} files saved in iSift yet. Choose one from your computer above.</p>)}
        <div className="actions"><button type="button" className="primary" disabled={busy||(!pick&&!up)} onClick={run}>{busy?<><LoaderCircle size={15} className="spin"/> Converting…</>:<><FileDown size={15}/> Convert and download PDF</>}</button></div>
      </>}
      {err&&<p className="syncerr" role="alert">{err}</p>}
      {done?.word&&<div role="status"><p className="ism-ok"><CheckCircle2 size={15}/> “{done.title}” was downloaded as a Word file.</p>{(done.notes||[]).map((t:string,i:number)=><p key={i} className="muted small">{t}</p>)}</div>}
      {done?.pdf&&<p className="ism-ok" role="status"><CheckCircle2 size={15}/> “{done.title}” was downloaded as a PDF.</p>}
      {done?.opened&&<div role="status"><p className="ism-ok"><CheckCircle2 size={15}/> “{done.title}” is now in {done.kind==='wp'?'WordPerfect':done.kind==='sheet'?'SpreadTable':'PowerPresentation'}.</p>{(done.notes||[]).map((t:string,i:number)=><p key={i} className="muted small">{t}</p>)}
        <div className="actions"><button type="button" className="primary" onClick={()=>onOpen(done.kind,done.id)}>Open to edit</button></div></div>}
      {done?.id&&!done.opened&&<div role="status"><p className="ism-ok"><CheckCircle2 size={15}/> “{done.title}” is now in WordPerfect ({done.pages} {done.pages===1?'page':'pages'} converted).</p>{(done.notes||[]).map((t:string,i:number)=><p key={i} className="muted small">{t}</p>)}
        <div className="actions"><button type="button" className="primary" onClick={()=>onOpen('wp',done.id)}>Open in WordPerfect</button></div></div>}
      <p className="muted small">Also in each editor: the Download button offers PDF and the original format (Word, Excel or PowerPoint).</p>
    </section></div>;
}
