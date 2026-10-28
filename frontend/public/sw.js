/* iSift service worker: shows push notifications (meeting starting, invitations, new email) even when iSift is closed. */
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('push',e=>{
  let d={};try{d=e.data?e.data.json():{}}catch{d={title:'iSift',body:e.data?e.data.text():''}}
  e.waitUntil((async()=>{
    const wins=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    // while iSift is open and in view it shows its own meeting card, so a second banner would only be noise
    if(d.kind==='meeting'&&wins.some(w=>w.visibilityState==='visible'&&w.focused))return;
    await self.registration.showNotification(d.title||'iSift',{body:d.body||'',icon:'/icon-192.png',badge:'/favicon-32.png',tag:d.tag||'isift',renotify:true,data:{url:d.url||'',kind:d.kind||''},requireInteraction:d.kind==='meeting'});
  })())});
self.addEventListener('notificationclick',e=>{
  e.notification.close();const u=(e.notification.data&&e.notification.data.url)||'';
  e.waitUntil((async()=>{
    let target=self.registration.scope;
    try{if(u){const x=new URL(u,self.registration.scope);target=x.href}}catch{}
    const wins=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    for(const w of wins){if(new URL(w.url).origin===new URL(target).origin){await w.focus();if(u&&new URL(target).origin===location.origin){try{w.postMessage({type:'isift-open',url:target})}catch{}}return}}
    if(self.clients.openWindow)await self.clients.openWindow(target)
  })())});
