/* Actual packaged NAPI calls. The endpoint is a finite virtual modem, not RF.
 * No native success/callback/NetworkRegistry injection or privileged addon. */
import call from '@ohos.telephony.call';
import data from '@ohos.telephony.data';
import radio from '@ohos.telephony.radio';
import observer from '@ohos.telephony.observer';
import sms from '@ohos.telephony.sms';
import net from '@ohos.net.connection';
import socket from '@ohos.net.socket';
import fs from '@ohos.file.fs';
import util from '@ohos.util';
import process from '@ohos.process';
import clock from '@ohos.systemDateTime';

const RUN = '__TELEPHONY579_RUN__';
const ROLE = '__TELEPHONY579_ROLE__';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const valueOf = value => value === undefined ? { value_type: 'undefined' } : value;
const ACTIONS = ['identity', 'state', 'observe', 'unobserve', 'dial', 'answer', 'hangup',
  'sms', 'data-on', 'data-off', 'udp', 'quiet', 'restore', 'invalid-dial', 'invalid-sms', 'invalid-data'];

export default class TelephonyAudit {
  constructor(context) {
    this.context = context; this.seq = 0; this.used = new Set(); this.serial = Promise.resolve();
    this.file = context.filesDir + '/telephony579-' + RUN + '-' + process.pid + '.jsonl';
    this.listeners = []; this.callId = undefined; this.dataBaseline = undefined;
  }
  now() { return clock.getUptime(clock.TimeType.STARTUP, false); }
  append(c, kind, value, code = 0) {
    const row = { schema: 1, run_id: RUN, boot_id: c.boot_id, role: ROLE,
      operation_id: c.operation_id, action: c.action, seq: ++this.seq,
      monotonic_ms: this.now(), pid: process.pid, uid: process.uid,
      files_dir: this.context.filesDir, kind, code, value: valueOf(value) };
    const bytes = new util.TextEncoder().encodeInto(JSON.stringify(row) + '\n');
    const file = fs.openSync(this.file, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY |
      fs.OpenMode.APPEND | fs.OpenMode.NOFOLLOW);
    try {
      let offset = 0;
      while (offset < bytes.length) {
        const n = fs.writeSync(file.fd, bytes.slice(offset).buffer);
        if (n <= 0 || n > bytes.length - offset) throw new Error('short raw journal write');
        offset += n;
      }
      fs.fsyncSync(file.fd);
    } finally { fs.closeSync(file); }
  }
  accept(text) {
    if (typeof text !== 'string' || text.length > 4096) throw new Error('bounded actual request required');
    const c = JSON.parse(text);
    if (c.run_id !== RUN || !/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(c.boot_id) ||
        !/^[a-f0-9]{32}$/.test(c.operation_id) || this.used.has(c.operation_id) ||
        this.used.size >= 512 || !ACTIONS.includes(c.action)) throw new Error('fresh fixed request required');
    this.used.add(c.operation_id);
    this.serial = this.serial.then(() => this.execute(c));
  }
  async state(c) {
    const results = {};
    for (const api of ['getCallState', 'getCellularDataState', 'isCellularDataEnabled', 'getNetworkState']) {
      try {
        let value;
        if (api === 'getCallState') value = await call.getCallState();
        if (api === 'getCellularDataState') value = await data.getCellularDataState();
        if (api === 'isCellularDataEnabled') {
          value = await data.isCellularDataEnabled();
          if (this.dataBaseline === undefined) this.dataBaseline = value;
        }
        if (api === 'getNetworkState') value = await radio.getNetworkState(0);
        results[api] = valueOf(value); this.append(c, 'state', { api, value: valueOf(value) });
      } catch (e) {
        results[api] = { error: Number.isInteger(e.code) ? e.code : -1 };
        this.append(c, 'state-error', { api, message: String(e.message) }, results[api].error);
      }
    }
    return results;
  }
  observe(c) {
    if (this.listeners.length) throw new Error('listeners already owned');
    const add = (api, type) => {
      const callback = value => {
        if (type === 'callDetailsChange' && Number.isInteger(value.callId)) this.callId = value.callId;
        this.append(c, 'callback', { type, value });
      };
      api.on(type, callback); this.listeners.push({ api, type, callback });
      this.append(c, 'listener-on', { type });
    };
    // Ordinary HAP observes the public network in its independent socket path.
    // Privileged telephony listeners belong to actual system callers only.
    add(observer, 'callStateChange');
    add(observer, 'cellularDataConnectionStateChange');
    add(call, 'callDetailsChange');
  }
  async unobserve(c) {
    const errors = [];
    for (const item of this.listeners.slice().reverse()) {
      try {
        if (item.api === call) await call.off(item.type);
        else item.api.off(item.type, item.callback);
        this.listeners.splice(this.listeners.indexOf(item), 1);
        this.append(c, 'listener-off', { type: item.type });
      } catch (e) { errors.push(String(e.message)); this.append(c, 'listener-off-error', { type: item.type }, Number.isInteger(e.code) ? e.code : -1); }
    }
    if (errors.length) { const failure = new Error(errors.join('; ')); failure.unsettledBoundary = 'listeners'; throw failure; }
  }
  async sendSms(c) {
    if (typeof c.nonce !== 'string' || !/^[a-f0-9]{32}$/.test(c.nonce)) throw new Error('fresh payload required');
    const content = 'L22-' + c.nonce; let finish;
    const response = new Promise(resolve => { finish = resolve; });
    let first = true;
    const complete = (error, value) => {
      const code = error && Number.isInteger(error.code) ? error.code : 0;
      this.append(c, 'sms-send-callback', { result: valueOf(value), message: error ? String(error.message) : '' }, code);
      if (first) { first = false; finish({ code, result: valueOf(value) }); }
    };
    // The request's actual native Promise and sendCallback are retained
    // independently: a successful JS return is never a delivery receipt.
    const result = sms.sendShortMessage({ slotId: 0, destinationHost: '5550100', content,
      sendCallback: complete,
      deliveryCallback: (error, value) => this.append(c, 'sms-delivery-callback',
        { result: valueOf(value), message: error ? String(error.message) : '' },
        error && Number.isInteger(error.code) ? error.code : 0) });
    if (result && typeof result.then === 'function') await result;
    this.append(c, 'sms-api-return', valueOf(result));
    const waited = await Promise.race([response, sleep(35000).then(() => ({ timeout: true }))]);
    this.append(c, 'sms-completion', waited);
    return waited;
  }
  async udp(c) {
    if (typeof c.nonce !== 'string' || !/^[a-f0-9]{32}$/.test(c.nonce)) throw new Error('fresh actual packet required');
    const payload = 'L22-' + RUN + '-' + ROLE + '-' + c.nonce;
    const handles = await net.getAllNets(); let selected;
    for (const handle of handles) {
      const caps = await net.getNetCapabilities(handle);
      const properties = await net.getConnectionProperties(handle);
      this.append(c, 'network-candidate', { netId: handle.netId, caps, properties });
      if (caps.bearerTypes.includes(net.NetBearType.BEARER_CELLULAR) && properties.interfaceName === 'usb0') {
        if (selected) throw new Error('ambiguous cellular network');
        selected = handle;
      }
    }
    if (!selected) throw new Error('actual registered usb0 cellular NetHandle unavailable');
    const udp = socket.constructUDPSocketInstance(); let received;
    let settle;
    const response = new Promise(resolve => { settle = resolve; });
    const onMessage = message => {
      const text = new util.TextDecoder().decodeWithStream(new Uint8Array(message.message));
      this.append(c, 'udp-callback', { text, remoteInfo: message.remoteInfo, netId: selected.netId });
      if (received === undefined) { received = text; settle(text); }
    };
    const onError = error => this.append(c, 'udp-error', { message: String(error.message) }, Number.isInteger(error.code) ? error.code : -1);
    try {
      udp.on('message', onMessage); udp.on('error', onError);
      await udp.bind({ address: '0.0.0.0', port: 0, family: 1 });
      // This API requires the actual socket object, not getSocketFd().
      await selected.bindSocket(udp);
      const local = await udp.getState();
      this.append(c, 'udp-bound', { netId: selected.netId, local });
      await udp.send({ data: payload, address: { address: '198.18.22.1', port: 53122, family: 1 } });
      this.append(c, 'udp-sent', { payload, netId: selected.netId });
      const text = await Promise.race([response, sleep(12000).then(() => undefined)]);
      if (text !== 'L22-REPLY:' + payload) throw new Error('fresh independent endpoint reply absent or wrong');
      return { payload, reply: text, netId: selected.netId };
    } finally {
      const cleanupErrors = [];
      for (const type of ['message', 'error']) {
        try { udp.off(type, type === 'message' ? onMessage : onError); }
        catch (e) { cleanupErrors.push('udp-off-' + type); this.append(c, 'cleanup-error',
          { boundary: 'udp-off-' + type, message: String(e.message) }, Number.isInteger(e.code) ? e.code : -1); }
      }
      try { await udp.close(); this.append(c, 'udp-closed', { netId: selected.netId }); }
      catch (e) { cleanupErrors.push('udp-close'); this.append(c, 'cleanup-error',
        { boundary: 'udp-close', message: String(e.message) }, Number.isInteger(e.code) ? e.code : -1); }
      if (cleanupErrors.length) { const failure = new Error(cleanupErrors.join('; '));
        failure.unsettledBoundary = 'socket'; throw failure; }

    }
  }
  async execute(c) {
    this.append(c, 'begin', c); let result;
    try {
      switch (c.action) {
        case 'identity': {
          const stat = fs.statSync(this.file);
          result = { files_dir: this.context.filesDir, inode: stat.ino.toString(), journal_uid: stat.uid };
          await this.state(c); break;
        }
        case 'state': result = await this.state(c); break;
        case 'observe': this.observe(c); break;
        case 'unobserve': await this.unobserve(c); break;
        case 'invalid-dial': result = await call.dialCall(JSON.parse('7'), { accountId: 0 }); break;
        case 'invalid-sms': result = await sms.sendShortMessage({ slotId: 0, destinationHost: JSON.parse('7'), content: JSON.parse('7') }); break;
        case 'invalid-data': result = await data.enableCellularData(JSON.parse('"invalid-callback"')); break;
        case 'dial': result = await call.dialCall('5550100', { accountId: 0 }); break;
        case 'answer': {
          if (!Number.isInteger(this.callId)) throw new Error('real callDetailsChange callId required');
          this.append(c, 'actual-call-id', { callId: this.callId }); result = await call.answerCall(this.callId); break;
        }
        case 'hangup': {
          if (!Number.isInteger(this.callId)) throw new Error('real callDetailsChange callId required');
          this.append(c, 'actual-call-id', { callId: this.callId }); result = await call.hangUpCall(this.callId); break;
        }
        case 'sms': result = await this.sendSms(c); break;
        case 'data-on': result = await data.enableCellularData(); break;
        case 'data-off': result = await data.disableCellularData(); break;
        case 'udp': result = await this.udp(c); break;
        case 'quiet': {
          if (![1000, 2500, 5000].includes(c.wait_ms)) throw new Error('fixed quiet interval required');
          await sleep(c.wait_ms); result = await this.state(c); break;
        }
        case 'restore': {
          // Fresh generation restores the externally bound original setting,
          // not its process-local default or a synthetic reset property.
          if (typeof c.data_baseline !== 'boolean') throw new Error('actual baseline required');
          result = c.data_baseline ? await data.enableCellularData() : await data.disableCellularData();
          await this.unobserve(c); await this.state(c); break;
        }
      }
      this.append(c, 'return', result);
    } catch (error) {
      const boundary = error.unsettledBoundary || (['observe','unobserve','restore'].includes(c.action) ? c.action : undefined);
      if (boundary) this.append(c, 'cleanup-error', { boundary, message: String(error.message) }, Number.isInteger(error.code) ? error.code : -1);
      this.append(c, 'error', { message: String(error.message), unsettled_boundary: boundary || '' }, Number.isInteger(error.code) ? error.code : -1);
    }
    this.append(c, 'end', undefined);
  }
}
