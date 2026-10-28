import React,{useEffect,useRef,useState} from 'react';
import {FileText,Table2,Presentation,FileDown,FileUp,ArrowRight,CheckCircle2,LoaderCircle} from 'lucide-react';
import {convertSaved} from './docConvert';

type Mode='wp-pdf'|'pdf-wp'|'deck-pdf'|'sheet-pdf';
const MODES:{id:Mode;from:string;to:string;kind?:'wp'|'sheet'|'deck';icon:any;text:string}[]=[
  {id:'wp-pdf',from:'WordPerfect',to:'PDF',kind:'wp',icon:FileText,text:'Your document as a PDF, laid out like the page you see.'},
  {id:'pdf-wp',from:'PDF',to:'WordPerfect',icon:FileUp,text:'Turn a PDF into a document you can edit and share.'},
  {id:'deck-pdf',from:'PowerPresentation',to:'PDF',kind:'deck',icon:Presentation,text:'Every slide as a PDF page, with its colours and shapes.'},
  {id:'sheet-pdf',from:'SpreadTable',to:'PDF',kind:'sheet',icon:Table2,text:'Every sheet as a PDF, showing the worked-out values.'}];
const readB64=(f:File)=>new Promise<string>((ok,no)=>{const r=new FileReader();r.onload=()=>ok(String(r.result).split(',')[1]||'');r.onerror=()=>no(new Error('The file could not be read.'));r.readAsDataURL(f)});

/** Doc Converter: WordPerfect, PowerPresentation and SpreadTable files to PDF, and a PDF into a WordPerfect document. */
export function DocConverter({request,onOpen}:{request:any;onOpen:(kind:string,id:string)=>void}){
  const [mode,setMode]=useState<Mode>('wp-pdf');const m=MODES.find(x=>x.id===mode)!;
  const [files,setFiles]=useState<any[]>([]);const [pick,setPick]=useState('');const [busy,setBusy]=useState(false);const [err,setErr]=useState('');const [done,setDone]=useState<any>(null);
  const [pdf,setPdf]=useState<File|null>(null);const fileIn=useRef<HTMLInputElement>(null);
  useEffect(()=>{setErr('');setDone(null);setPick('');if(!m.kind){setFiles([]);return}
    Promise.all([request(`/notes?kind=${m.kind}`).catch(()=>[]),request(`/shared/with-me?kind=${m.kind}`).catch(()=>[])]).then(([mine,withMe])=>{
      const l=[...(mine||[]).map((n:any)=>({id:n.id,title:n.title,note:''})),...(withMe||[]).map((n:any)=>({id:n.id,title:n.title,note:` (from ${n.owner})`}))];setFiles(l);if(l.length)setPick(l[0].id)})},[mode]);
  const run=async()=>{setErr('');setDone(null);setBusy(true);
    try{
      if(mode==='pdf-wp'){
        if(!pdf)throw new Error('Choose a PDF first.');
        const r=await request('/docs/pdf-to-wp',{method:'POST',body:JSON.stringify({name:pdf.name,data:await readB64(pdf)})});
        const title=pdf.name.replace(/\.pdf$/i,'').slice(0,150)||'Converted PDF';
        const n=await request('/notes',{method:'POST',body:JSON.stringify({kind:'wp',title,content:r.html})});
        setDone({id:n.id,title,pages:r.pages,notes:r.notes||[]});
      }else{
        if(!pick)throw new Error('Choose a file first.');
        const n=await request(`/notes/${pick}`);await convertSaved(request,m.kind!,'pdf',n.title||'file',n.content||'');
        setDone({title:n.title,pdf:true});
      }
    }catch(e:any){setErr(e?.message||'The conversion did not finish.')}finally{setBusy(false)}};
  return <div className="dconv">
    <div className="dconv-modes" role="tablist" aria-label="Conversion">{MODES.map(x=>{const I=x.icon;return <button key={x.id} type="button" role="tab" aria-selected={mode===x.id} className={`dconv-mode${mode===x.id?' on':''}`} onClick={()=>setMode(x.id)}><I size={20}/><b>{x.from} <ArrowRight size={13}/> {x.to}</b><small>{x.text}</small></button>})}</div>
    <section className="panel dconv-panel">
      <h2>{m.from} to {m.to}</h2>
      {mode==='pdf-wp'?<>
        <p className="muted">Choose a PDF. iSift rebuilds it as a new WordPerfect document in your list, with headings, bold and italic, text colours, lists, tables and pictures. A PDF is a fixed page, so page breaks and exact positions are not kept, and a scanned page is placed as a picture.</p>
        <div className="actions"><button type="button" className="secondary" onClick={()=>fileIn.current?.click()}><FileUp size={15}/> {pdf?pdf.name:'Choose a PDF'}</button><input ref={fileIn} type="file" accept="application/pdf,.pdf" hidden onChange={e=>{setPdf(e.target.files?.[0]||null);setDone(null);setErr('');e.target.value=''}}/>
          <button type="button" className="primary" disabled={busy||!pdf} onClick={run}>{busy?<><LoaderCircle size={15} className="spin"/> Converting…</>:<>Convert to WordPerfect</>}</button></div>
      </>:<>
        <p className="muted">Choose one of your {m.from} files. The PDF keeps its colours, fonts, pictures and layout, and downloads straight away. Your original file is not changed.</p>
        {files.length?<label className="dconv-pick">File<select value={pick} onChange={e=>{setPick(e.target.value);setDone(null)}} aria-label={`Choose a ${m.from} file`}>{files.map(f=><option key={f.id} value={f.id}>{f.title||'Untitled'}{f.note}</option>)}</select></label>:<p className="muted">You have no {m.from} files yet. Create one in the {m.from} tab first.</p>}
        <div className="actions"><button type="button" className="primary" disabled={busy||!pick} onClick={run}>{busy?<><LoaderCircle size={15} className="spin"/> Converting…</>:<><FileDown size={15}/> Convert and download PDF</>}</button></div>
      </>}
      {err&&<p className="syncerr" role="alert">{err}</p>}
      {done?.pdf&&<p className="ism-ok" role="status"><CheckCircle2 size={15}/> “{done.title}” was downloaded as a PDF.</p>}
      {done?.id&&<div role="status"><p className="ism-ok"><CheckCircle2 size={15}/> “{done.title}” is now in WordPerfect ({done.pages} {done.pages===1?'page':'pages'} converted).</p>{(done.notes||[]).map((t:string,i:number)=><p key={i} className="muted small">{t}</p>)}
        <div className="actions"><button type="button" className="primary" onClick={()=>onOpen('wp',done.id)}>Open in WordPerfect</button></div></div>}
      <p className="muted small">Also in each editor: the Download button offers PDF and the original format (Word, Excel or PowerPoint).</p>
    </section></div>;
}
