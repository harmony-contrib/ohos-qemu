"""Execute the exact caller's async lifecycle; never invent guest media events."""
from pathlib import Path
import shutil
import subprocess
import unittest

TEMPLATE=Path(__file__).with_name('web_factory_probe.ets')

class WebFactoryLifecycleTests(unittest.TestCase):
    def test_navigation_and_summary_wait_for_actual_create_and_release_events(self):
        text=TEMPLATE.read_text()
        method=text.split('  private async checkPage(): Promise<void> {',1)[1].split('  aboutToAppear(): void {',1)[0]
        # Erase only the known ArkTS annotations in this single method; the
        # actual control flow remains byte-for-byte the caller implementation.
        method=method.replace(': string', '').replace(': number','').replace(': boolean','').replace(
            'Promise<void>','Promise').replace('(error as BusinessError).message','error.message')
        method='async function checkPage() {'+method
        source=r'''
const assert=require('node:assert/strict');
const queue=[];
global.setTimeout=(callback,delay)=>{queue.push({callback,delay});};
async function tick(){const next=queue.shift();assert(next,'missing actual awaited timer');
 next.callback();await Promise.resolve();await Promise.resolve();}
function caller(generation){
 const value={runId:'nonce',generation,finished:false,failures:0,pageChecking:false,
  mediaCreated:[false,false],mediaReleased:[false,false],rows:[],loads:[]};
 value.record=(name,text='',values=[],error='')=>value.rows.push({name,text,values,error});
 value.checkPage=()=>checkPage.call(value);
 value.controller={getTitle:()=>`OK-nonce:${value.generation}:stream-body`,
  loadUrl:(url)=>value.loads.push(url)};
 return value;
}
'''+method+r'''
(async()=>{
 const first=caller(0);let done=false;
 const task=first.checkPage().then(()=>{done=true;});
 for(let i=0;i<5;i++){await tick();assert(!done);assert.equal(first.loads.length,0);}
 first.mediaCreated[0]=true;await tick();await task;
 assert(done);assert.deepEqual(first.loads,['auditweb://audit.local/main?generation=1']);
 assert(!first.finished);assert(!first.rows.some(row=>row.name==='summary'));
 // The next-generation timer is deliberately not executed: its own exact
 // method is tested below with an independent deterministic callback history.
 queue.length=0;
 const second=caller(1);second.mediaCreated[0]=true;done=false;
 const secondTask=second.checkPage().then(()=>{done=true;});
 for(let i=0;i<5;i++){await tick();assert(!done);assert.equal(second.loads.length,0);}
 second.mediaCreated[1]=true;await tick();
 assert.deepEqual(second.loads,['about:blank']);assert(!done);assert(!second.finished);
 for(let i=0;i<5;i++){await tick();assert(!done);assert(!second.rows.some(row=>row.name==='summary'));}
 second.mediaReleased[0]=true;await tick();assert(!done);
 second.mediaReleased[1]=true;await tick();await secondTask;
 assert(second.finished);assert.deepEqual(second.rows.at(-1).values,[2,0]);
 queue.length=0;
 for(const failure of ['missing-create','missing-release']){
  const value=caller(1);if(failure==='missing-release')value.mediaCreated=[true,true];
  let completed=false;const task=value.checkPage().then(()=>{completed=true;});
  for(let i=0;i<650 && !completed;i++)await tick();await task;
  assert(completed);assert.equal(value.failures,1);assert.deepEqual(value.rows.at(-1).values,[2,1]);
  assert.match(value.rows.find(row=>row.name==='page.failed').error,/actual native media/);
  if(failure==='missing-create')assert.equal(value.loads.length,0);
  queue.length=0;
 }
 const cancelled=caller(1);const cancelTask=cancelled.checkPage();
 cancelled.finished=true;await tick();await cancelTask;assert.equal(cancelled.rows.length,0);
})().catch(error=>{process.stderr.write(String(error.stack));process.exitCode=1;});
'''
        node=shutil.which('node')
        self.assertIsNotNone(node,'Node is required to execute exact async lifecycle fixtures')
        result=subprocess.run([node,'-'],input=source,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_callback_generation_uses_real_source_and_never_next_navigation_counter(self):
        text=TEMPLATE.read_text().split('this.controller.onCreateNativeMediaPlayer(',1)[1].split(
            "    this.record('setup');",1)[0]
        self.assertNotIn('const generation = this.generation',text)
        self.assertIn("source.source === 'auditweb://audit.local/media-0.mp4'",text)
        self.assertIn("source.source === 'auditweb://audit.local/media-1.mp4'",text)
        self.assertIn('if (generation < 0) { throw new Error(',text)
        self.assertIn('this.mediaCreated[generation] = true;',text)
        self.assertIn("if (name === 'release') { this.mediaReleased[generation] = true; }",text)

if __name__=='__main__':unittest.main()
