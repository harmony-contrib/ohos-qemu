import ChildProcess from '@ohos.app.ability.ChildProcess';
import fs from '@ohos.file.fs';
import process from '@ohos.process';
export default class Worker extends ChildProcess {
 onStart():void {
  const file=fs.openSync('/data/storage/el2/base/files/child-profile-__RUN__-worker.log',fs.OpenMode.CREATE|fs.OpenMode.WRITE_ONLY|fs.OpenMode.APPEND);
  try {fs.writeSync(file.fd,JSON.stringify({runId:'__RUN__',uid:process.uid,pid:process.pid})+'\n');}finally {fs.closeSync(file);}
 }
}
