/** Notifications that reach this device even when iSift is closed (Web Push). */
const b64=(s:string)=>{const p='='.repeat((4-s.length%4)%4);const r=atob((s+p).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from(r,c=>c.charCodeAt(0))};
export const pushSupported=()=>{try{return 'serviceWorker' in navigator&&'PushManager' in window&&'Notification' in window}catch{return false}};
export const permission=():string=>{try{return 'Notification' in window?Notification.permission:'denied'}catch{return 'denied'}};
/** iPhone and iPad only allow notifications for an app added to the Home Screen. */
export const needsHomeScreen=()=>{try{const ios=/iPhone|iPad|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);const standalone=(navigator as any).standalone===true||matchMedia('(display-mode: standalone)').matches;return ios&&!standalone}catch{return false}};
const reg=async()=>{const r=await navigator.serviceWorker.register('/sw.js');await navigator.serviceWorker.ready;return r};
async function subscribe(request:any){
  const r=await reg();const {key}=await request('/push/key');
  let s=await r.pushManager.getSubscription();
  if(s){const cur=s.options?.applicationServerKey;if(cur&&btoa(String.fromCharCode(...new Uint8Array(cur))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'')!==key){await s.unsubscribe();s=null}}
  if(!s)s=await r.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64(key)});
  await request('/push/subscribe',{method:'POST',body:JSON.stringify({subscription:s.toJSON(),ua:navigator.userAgent})});
}
export async function enablePush(request:any):Promise<string>{
  if(!pushSupported())return needsHomeScreen()?'On iPhone or iPad, first add iSift to your Home Screen (Share, then Add to Home Screen), open it from there, then turn notifications on.':'This browser does not support notifications.';
  const p=await Notification.requestPermission();if(p!=='granted')return p==='denied'?'Notifications are blocked for this site. Allow them in your browser settings (the lock icon next to the address), then try again.':'Notifications were not turned on.';
  try{await subscribe(request)}catch(e:any){return /permission denied|not allowed/i.test(e?.message||'')?'This browser would not register for notifications. Private or incognito windows cannot; open iSift in a normal window and try again.':(e?.message||'Notifications could not be turned on.')}return '';
}
/** Keeps an already-allowed device registered (a browser can drop its subscription). Silent. */
export async function refreshPush(request:any){try{if(pushSupported()&&permission()==='granted')await subscribe(request)}catch{}}
export async function disablePush(request:any){try{const r=await navigator.serviceWorker.getRegistration('/sw.js');const s=await r?.pushManager.getSubscription();if(s){await request('/push/unsubscribe',{method:'POST',body:JSON.stringify({endpoint:s.endpoint})}).catch(()=>{});await s.unsubscribe()}}catch{}}
export async function deviceOn():Promise<boolean>{try{if(!pushSupported()||permission()!=='granted')return false;const r=await navigator.serviceWorker.getRegistration('/sw.js');return !!(await r?.pushManager.getSubscription())}catch{return false}}
