import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
import socket from '@ohos.net.socket';
import fs from '@ohos.file.fs';
import process from '@ohos.process';
import bundleManager from '@ohos.bundle.bundleManager';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import { BusinessError } from '@ohos.base';

interface Request { run_id: string; boot_id: string; operation_id: string; action: string; nonce: string; }
interface Row { run_id: string; boot_id: string; operation_id: string; action: string;
  sequence: number; uid: number; pid: number; token: number; event: string; code: number; value: string; }

export default class EntryAbility extends UIAbility {
  private chain: Promise<void> = Promise.resolve();
  private sequence: number = 0;
  private token: number = 0;
  private boot: string = '';
  private operations: string[] = [];
  private row(r: Request, event: string, code: number = 0, value: string = ''): void {
    const row: Row = { run_id: '__RUN__', boot_id: r.boot_id, operation_id: r.operation_id, action: r.action,
      sequence: ++this.sequence, uid: process.uid, pid: process.pid, token: this.token, event: event, code: code, value: value };
    const file = fs.openSync(this.context.getApplicationContext().filesDir + '/nonce-__RUN__.jsonl',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND | fs.OpenMode.NOFOLLOW);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
  }
  private async call(r: Request): Promise<void> {
    if (r.run_id !== '__RUN__' || !/^[a-f0-9]{32}$/.test(r.operation_id) ||
      !/^[a-f0-9]{32}$/.test(r.nonce) || !/^[a-f0-9-]{36}$/.test(r.boot_id) ||
      this.operations.includes(r.operation_id) || !['before', 'connected', 'after'].includes(r.action) ||
      (this.boot !== '' && this.boot !== r.boot_id)) { throw new Error('Foreign/replayed nonce operation'); }
    this.boot = r.boot_id; this.operations.push(r.operation_id);
    this.token = bundleManager.getBundleInfoForSelfSync(
      bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_APPLICATION).appInfo.accessTokenId;
    this.row(r, 'begin');
    let udp: socket.UDPSocket | undefined;
    let timer: number = -1;
    try {
      const grant = abilityAccessCtrl.createAtManager().checkAccessTokenSync(this.token, 'ohos.permission.INTERNET');
      this.row(r, 'permission', grant);
      if (grant !== 0) { throw new Error('Actual INTERNET grant required'); }
      udp = socket.constructUDPSocketInstance();
      const active = udp;
      let finish: (value: string) => void = (value: string): void => {};
      const reply = new Promise<string>((resolve) => { finish = resolve; });
      let server: string = '';
      let networkError: number = 0;
      const prefix = '__RUN__ ' + r.operation_id + ' ' + r.nonce;
      active.on('error', (error: BusinessError) => { networkError = error.code; finish('socket-error'); });
      active.on('message', (info: socket.SocketMessageInfo) => {
        const bytes = new Uint8Array(info.message);
        if (bytes.length > 512 || info.remoteInfo.size !== bytes.length || info.remoteInfo.family !== 'IPv4' ||
          info.remoteInfo.address !== '10.73.0.1' || info.remoteInfo.port !== 46073) {
          finish('foreign-response'); return;
        }
        let text = '';
        for (let i = 0; i < bytes.length && i < 512; ++i) { text += String.fromCharCode(bytes[i]); }
        const fields = text.split(' ');
        if (fields.length !== 5 || fields.slice(1, 4).join(' ') !== prefix || !/^[a-f0-9]{32}$/.test(fields[4])) {
          finish('foreign-response'); return;
        }
        if (fields[0] === 'VPN1' && (server === '' || server === fields[4])) {
          server = fields[4]; this.row(r, 'server-challenge', 0, text);
          active.send({ data: 'VPN2 ' + prefix + ' ' + server,
            address: { address: '10.73.0.1', port: 46073, family: 1 } }).catch((error: BusinessError) => {
              networkError = error.code; finish('socket-error');
            });
        } else if (fields[0] === 'VPN3' && server === fields[4]) { finish(text); }
        else { finish('foreign-response'); }
      });
      await active.bind({ address: '0.0.0.0', port: 0, family: 1 });
      this.row(r, 'bound', 0, JSON.stringify(await active.getLocalAddress()));
      timer = setTimeout(() => { finish('timeout'); }, 5000);
      await active.send({ data: 'VPN1 ' + prefix, address: { address: '10.73.0.1', port: 46073, family: 1 } });
      this.row(r, 'udp-sent', 0, 'VPN1 ' + prefix);
      const result = await reply;
      if (networkError !== 0) { this.row(r, 'socket-error', networkError); }
      if (r.action === 'connected' && result === 'VPN3 ' + prefix + ' ' + server && server !== '') {
        this.row(r, 'confirmed', 0, result);
      } else if (r.action !== 'connected' && result === 'timeout') { this.row(r, 'unreachable-timeout'); }
      else { this.row(r, 'unexpected-result', -1, result); }
    } catch (error) {
      const code = (error as BusinessError).code;
      this.row(r, 'error', typeof code === 'number' ? code : -1, String(error));
    } finally {
      if (timer >= 0) { clearTimeout(timer); }
      if (udp !== undefined) {
        udp.off('message'); udp.off('error');
        try { await udp.close(); this.row(r, 'closed'); }
        catch (error) { this.row(r, 'close-error', -1, String(error)); }
      }
    }
    this.row(r, 'complete');
  }
  private receive(want: Want): void {
    const serialized = want.parameters?.request;
    if (typeof serialized !== 'string') { throw new Error('Exact request string required'); }
    const request = JSON.parse(serialized) as Request;
    this.chain = this.chain.then(() => this.call(request));
  }
  onCreate(want: Want): void { this.receive(want); }
  onNewWant(want: Want): void { this.receive(want); }
  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index'); }
}
