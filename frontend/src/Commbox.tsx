import React from 'react';
import {Mail,CalendarDays,Users} from 'lucide-react';

export const COMM_TABS=[['Mail',Mail],['Calendar',CalendarDays],['Contacts',Users]] as const;

/** One place for the three Outlook-style tools: Mail, Calendar and Contacts (People). */
export function CommboxPage({tab,setTab,children,tabs}:{tab:string;setTab:(t:string)=>void;children:React.ReactNode;tabs?:string[]}){
  return <div className="commbox">
    <div className="cb-tabs" role="tablist" aria-label="Commbox"><h1>Commbox</h1>
      {COMM_TABS.filter(([n])=>!tabs||tabs.includes(n)).map(([name,Icon])=><button key={name} role="tab" aria-selected={tab===name} className={tab===name?'on':''} onClick={()=>setTab(name)}><Icon size={17}/> {name}</button>)}
    </div>
    {children}
  </div>;
}
