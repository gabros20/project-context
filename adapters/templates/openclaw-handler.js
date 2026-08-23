import { spawnSync } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
const PY=@@PYTHON@@, CTX=@@CTX@@;
const handler=async(event)=>{
  const cwd=event?.context?.workspaceDir || process.cwd(); const session_id=event?.sessionKey || event?.context?.sessionId || "openclaw-runtime";
  const run=(name)=>spawnSync(PY,[CTX,"hook",name,"--host","openclaw"],{input:JSON.stringify({cwd,session_id}),encoding:"utf8",cwd});
  if(event.type==="agent" && event.action==="bootstrap"){
    run("session-start"); const result=spawnSync(PY,[CTX,"--cwd",cwd,"startup"],{encoding:"utf8",cwd});
    if(result.status===0 && result.stdout.trim() && Array.isArray(event.context?.bootstrapFiles)){
      const directory=join(homedir(),".cache","project-context","openclaw"); mkdirSync(directory,{recursive:true});
      const file=join(directory,`${session_id.replace(/[^A-Za-z0-9_.-]/g,"_")}.md`); writeFileSync(file,result.stdout); event.context.bootstrapFiles.push(file);
    }
  }
  if(event.type==="session" && event.action==="compact:before") run("compact-before");
  if(event.type==="session" && event.action==="compact:after") run("compact-after");
  if((event.type==="command" && (event.action==="new"||event.action==="reset")) || (event.type==="session"&&event.action==="auto-reset")) run("session-end");
}; export default handler;
