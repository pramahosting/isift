// Personal preferences kept on this device (not on the server). Every setting here is really used by the app.
export type Prefs={muteOnJoin:boolean;camOffOnJoin:boolean;confirmLeave:boolean;reduceMotion:boolean;bigText:boolean};
const KEY='isift.prefs';
const DEF:Prefs={muteOnJoin:false,camOffOnJoin:false,confirmLeave:false,reduceMotion:false,bigText:false};
export function getPrefs():Prefs{try{return {...DEF,...JSON.parse(localStorage.getItem(KEY)||'{}')}}catch{return {...DEF}}}
export function applyPrefs(p:Prefs=getPrefs()){try{const c=document.documentElement.classList;c.toggle('reduce-motion',p.reduceMotion);c.toggle('big-text',p.bigText)}catch{}}
export function setPref<K extends keyof Prefs>(k:K,v:Prefs[K]){const p={...getPrefs(),[k]:v};try{localStorage.setItem(KEY,JSON.stringify(p))}catch{}applyPrefs(p);return p}
