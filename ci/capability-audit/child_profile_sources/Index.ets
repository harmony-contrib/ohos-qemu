import childProcessManager from '@ohos.app.ability.childProcessManager';
import fs from '@ohos.file.fs';
import process from '@ohos.process';
import { BusinessError } from '@ohos.base';
import native from 'libprofile.so';
interface Row {runId:string;name:string;values:number[];data:string;}
@Entry
@Component
struct Index {
  @State note:string='Child profile diagnostic';
  private record(name:string,values:number[]=[],data:string=''):void {
    const row:Row={runId:'__RUN__',name,values,data};
    const file=fs.openSync('/data/storage/el2/base/files/child-profile-__RUN__-results.log',fs.OpenMode.CREATE|fs.OpenMode.WRITE_ONLY|fs.OpenMode.APPEND);
    try {fs.writeSync(file.fd,JSON.stringify(row)+'\n');}finally {fs.closeSync(file);}
    this.note=name;
  }
  private async run():Promise<void> {
    try {
      this.record('identity',[process.uid,process.euid,process.pid]);
      this.record('typed.const.enum',[childProcessManager.StartMode.SELF_FORK,childProcessManager.StartMode.APP_SPAWN_FORK]);
      this.record('supported',[childProcessManager.isArkChildProcessSupported()?1:0,childProcessManager.isNativeChildProcessSupported()?1:0]);
      this.record('C_API',[],JSON.stringify(native.run()));
      for(const mode of [childProcessManager.StartMode.SELF_FORK,childProcessManager.StartMode.APP_SPAWN_FORK]) {
        try {const pid=await childProcessManager.startChildProcess('./ets/child/Worker.ets',mode);this.record('legacy.promise.'+mode,[pid]);}
        catch(error) {const business=error as BusinessError;this.record('legacy.promise.reject.'+mode,[business.code],typeof business.code+':'+business.message);}
        await new Promise<void>((resolve)=>{
          childProcessManager.startChildProcess('./ets/child/Worker.ets',mode,(error:BusinessError,pid:number)=>{
            if(error) this.record('legacy.callback.reject.'+mode,[error.code],typeof error.code+':'+error.message);
            else this.record('legacy.callback.'+mode,[pid]);
            resolve();
          });
        });
      }
      try {const pid=await childProcessManager.startArkChildProcess('./ets/child/Worker.ets',{entryParams:'__RUN__'});this.record('ark.start',[pid]);}
      catch(error) {const business=error as BusinessError;this.record('ark.reject',[business.code],typeof business.code+':'+business.message);}
      try {const pid=await childProcessManager.startNativeChildProcess('libprofile.so:Main',{entryParams:'__RUN__'});this.record('native.start',[pid]);}
      catch(error) {const business=error as BusinessError;this.record('native.reject',[business.code],typeof business.code+':'+business.message);}
      try {await childProcessManager.startNativeChildProcess('invalid-entry',{entryParams:'__RUN__'});this.record('invalid.entry.unexpected');}
      catch(error) {const business=error as BusinessError;this.record('invalid.entry.reject',[business.code],typeof business.code+':'+business.message);}
      this.record('summary',[1]);
    }catch(error) {this.record('failed',[],String(error));}
  }
  aboutToAppear():void {this.run();}
  build(){Column(){Text(this.note).id('child-profile-state')}.width('100%').height('100%')}
}
