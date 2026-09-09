import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm,realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
// @ts-ignore Native plugin source is intentionally dependency-free JavaScript.
import plugin from '../../docs/session-workspace.mjs';

test('session hook defaults tool directories and rejects mistyped session IDs',async()=>{
 const root=await realpath(await mkdtemp(path.join(tmpdir(),'cloud-session-')));
 try{
  const hook=(await plugin({directory:root}))['tool.execute.before'];
  const output={args:{} as Record<string,string>};
  await hook({tool:'bash',sessionID:'ses_f7b123'},output);
  assert.equal(output.args.workdir,path.join(root,'sessions','ses_f7b123'));
  const write={args:{filePath:'outputs/report.txt'}};
  await hook({tool:'write',sessionID:'ses_f7b123'},write);
  assert.equal(write.args.filePath,path.join(root,'sessions','ses_f7b123','outputs','report.txt'));
  await assert.rejects(()=>hook({tool:'write',sessionID:'ses_f7b123'},
   {args:{filePath:path.join(root,'sessions','ses_fb123','inputs','report.txt')}}),/Wrong session path/);
  const other={args:{} as Record<string,string>};
  await hook({tool:'bash',sessionID:'ses_other'},other);
  assert.notEqual(other.args.workdir,output.args.workdir);
 }finally{await rm(root,{recursive:true,force:true})}
});
