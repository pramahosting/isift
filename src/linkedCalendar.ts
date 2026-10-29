// Remember one calendar (.ics) file the person picked, so it can be re-read on later visits.
// Uses the browser's File System Access API (Chrome / Edge). The file never leaves the browser
// except as the same upload the person already chose to make.
const DB='isift-linked-cal',STORE='h',KEY='file';
const open=()=>new Promise<IDBDatabase>((res,rej)=>{const r=indexedDB.open(DB,1);r.onupgradeneeded=()=>r.result.createObjectStore(STORE);r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error)});
const getH=async():Promise<any>=>{const d=await open();return new Promise(res=>{const r=d.transaction(STORE).objectStore(STORE).get(KEY);r.onsuccess=()=>res(r.result);r.onerror=()=>res(null)})};
const putH=async(h:any)=>{const d=await open();return new Promise<void>(res=>{const t=d.transaction(STORE,'readwrite');t.objectStore(STORE).put(h,KEY);t.oncomplete=()=>res();t.onerror=()=>res()})};
export const canLinkFile=()=>{try{return typeof (window as any).showOpenFilePicker==='function'&&typeof indexedDB!=='undefined'}catch{return false}};
export async function linkCalendarFile():Promise<File|null>{
 try{
  const [h]=await (window as any).showOpenFilePicker({multiple:false,types:[{description:'Calendar (.ics)',accept:{'text/calendar':['.ics','.ical']}}]});
  await putH(h);const f=await h.getFile();try{localStorage.setItem('isift.linkedcal.mod',String(f.lastModified))}catch{}return f;
 }catch{return null}
}
// Silent refresh: only when the browser already allows reading, and only if the file changed.
export async function refreshLinkedCalendar(upload:(f:File)=>Promise<void>){
 if(!canLinkFile())return;
 const h=await getH();if(!h)return;
 if((await h.queryPermission?.({mode:'read'}))!=='granted')return;
 const f:File=await h.getFile();
 let last='';try{last=localStorage.getItem('isift.linkedcal.mod')||''}catch{}
 if(String(f.lastModified)===last)return;
 await upload(f);try{localStorage.setItem('isift.linkedcal.mod',String(f.lastModified))}catch{}
}
