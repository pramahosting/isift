import {shapePng} from './Whiteboard';
import {libOf} from './WbLib';
import {evaluate,show} from './sheetcalc';
import {parseDeck,parseBook} from './DocsEditors';

/** Save a file the server made (sent as base64) to the person's computer. */
export function saveFile(filename:string,mime:string,b64:string){
  const bin=atob(b64);const bytes=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)bytes[i]=bin.charCodeAt(i);
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([bytes],{type:mime}));a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),4000)}

/** The pictures of a presentation's shapes (they are drawn in the browser), so the server can place them exactly. */
export function deckShapes(deck:any){
  const out:Record<string,{png:string;w:number;h:number}>={};
  for(const s of (deck?.slides||[]))for(const q of (s.shapes||[])){const lib=libOf(q.lib);if(!lib||out[q.id])continue;try{const p=shapePng(lib,q.text);out[q.id]={png:p.url,w:p.w,h:p.h}}catch{}}
  return out}

/** What each sheet's grid shows (formulas worked out), so a PDF matches the screen. */
export function sheetShown(book:any){
  return (book?.sheets||[]).map((sh:any)=>{const val=evaluate(sh.cells);const o:Record<string,string>={};for(const k of Object.keys(sh.cells))o[k]=show(val(k));return o})}

export async function convertDownload(request:any,kind:'wp'|'sheet'|'deck',to:string,title:string,content:string,extra:{shown?:any;shapes?:any}={}){
  const r=await request('/docs/convert',{method:'POST',body:JSON.stringify({kind,to,title,content,...extra})});
  saveFile(r.filename,r.mime,r.data)}

/** For the Doc Converter tab: convert a saved file by its content. */
export async function convertSaved(request:any,kind:'wp'|'sheet'|'deck',to:string,title:string,content:string){
  if(kind==='sheet')return convertDownload(request,kind,to,title,content,{shown:sheetShown(parseBook(content))});
  if(kind==='deck')return convertDownload(request,kind,to,title,content,{shapes:deckShapes(parseDeck(content))});
  return convertDownload(request,kind,to,title,content)}

/** A Word, Excel or PowerPoint file read by the server into {kind, title, content, notes} that an iSift editor can open. */
export async function importOffice(request:any,f:File):Promise<{kind:'wp'|'sheet'|'deck';title:string;content:string;notes:string[]}>{
  const data:string=await new Promise((ok,no)=>{const r=new FileReader();r.onload=()=>ok(String(r.result).split(',')[1]||'');r.onerror=()=>no(new Error('The file could not be read.'));r.readAsDataURL(f)});
  return request('/docs/import',{method:'POST',body:JSON.stringify({name:f.name,data})})}
