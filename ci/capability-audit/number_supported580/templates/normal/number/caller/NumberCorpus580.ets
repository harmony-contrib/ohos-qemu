import common from '@ohos.app.ability.common';
import fs from '@ohos.file.fs';
import util from '@ohos.util';
import { BusinessError } from '@kit.BasicServicesKit';
import { observeNapiToken411 } from './NapiToken411';
import { request580, invoke580, context580 } from './LegacyNumberCorpus580.js';

class Raw580 {
  schema: string = 'number580-corpus-raw/v1';
  run: string = ''; ownerRun: string = ''; phase: string = 'corpus580'; caseId: string = '';
  seq: number = 0; time: number = 0; event: string = ''; step: string = ''; valueJSON: string = '';
  codeKnown: boolean = false; code: number = 0; codeJSON: string = ''; message: string = '';
  runtimePass: boolean = false; wholeAggregateClosed: boolean = false;
}
function need(value: boolean, message: string): void { if (!value) { throw new Error(message); } }
export class NumberCorpus580 {
  private readonly context: common.UIAbilityContext;
  private readonly runId: string; private readonly ownerRun: string; private readonly caseId: string;
  private readonly role: string; private readonly request: string; private readonly file: string; private seq: number = 0;
  constructor(context: common.UIAbilityContext, run: string, owner: string, caseId: string, number: string, role: string) {
    need(/^[0-9a-f]{32}$/.test(run) && /^[0-9a-f]{32}$/.test(owner) && run !== owner &&
      /^\+?[0-9]{7,20}$/.test(number), 'fresh independent corpus/owner run and unused number required');
    need(role==='system-granted' || role==='system-readonly' || role==='ordinary', 'fixed role steering only');
    this.role=role; this.context=context; this.runId=run; this.ownerRun=owner; this.caseId=caseId;
    this.request=request580(caseId, number, owner);
    this.file=context.filesDir + '/number-corpus580-' + run + '.jsonl';
    need(!fs.accessSync(this.file), 'refuse existing Number580 journal');
  }
  private row(event: string, step: string = '', value: string = '', known: boolean = false,
    code: number = 0, codeJSON: string = '', message: string = ''): void {
    const row=new Raw580(); row.run=this.runId; row.ownerRun=this.ownerRun; row.caseId=this.caseId;
    row.seq=this.seq++; row.time=Date.now(); row.event=event; row.step=step; row.valueJSON=value;
    row.codeKnown=known; row.code=code; row.codeJSON=codeJSON; row.message=message;
    const text=JSON.stringify(row); const bytes=new util.TextEncoder().encodeInto(text+'\n');
    const handle=fs.openSync(this.file, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND | fs.OpenMode.NOFOLLOW);
    try { let offset: number=0; while (offset < bytes.byteLength) {
      const amount=fs.writeSync(handle.fd, bytes.slice(offset).buffer);
      need(Number.isInteger(amount) && amount>0 && amount<=bytes.byteLength-offset, 'short actual journal write'); offset+=amount;
    } } finally { fs.closeSync(handle); }
    console.info('NUMBER_CORPUS580 '+text);
  }
  private error(event: string, step: string, value: BusinessError): void {
    const known=typeof value.code === 'number' && Number.isInteger(value.code);
    const raw=JSON.stringify(value.code);
    this.row(event,step,'',known,known?value.code:0,typeof raw==='string'?raw:'<undefined>',
      typeof value.message==='string'?value.message:String(value));
  }
  private async call(step: string): Promise<void> {
    this.row('call',step); let dispatched: boolean=false;
    try {
      const result=invoke580(this.context,this.request,this.ownerRun,step);
      dispatched=true; this.row('dispatched',step);
      this.row('resolved',step,await result);
    } catch (error) { this.error(dispatched?'rejected':'threw',step,error as BusinessError); }
  }
  async run(): Promise<void> {
    this.row('begin','',JSON.stringify(this.context.filesDir)); this.row('request','',this.request);
    try {
      observeNapiToken411(this.context,this.runId,'napi-before');
      if (this.role!=='ordinary') { this.row('context','before',await context580()); }
      if (this.caseId==='mark-create-read' || this.caseId==='mark-update-read' || this.caseId==='mark-delete-read') {
        await this.call('write');
      }
      await this.call('read');
      if (this.role!=='ordinary') { this.row('context','after',await context580()); }
      observeNapiToken411(this.context,this.runId,'napi-after'); this.row('end');
    } catch (error) { this.error('probe-error','',error as BusinessError); }
    this.row('summary','','"raw_recorded_NOT_acceptance"');
  }
}
