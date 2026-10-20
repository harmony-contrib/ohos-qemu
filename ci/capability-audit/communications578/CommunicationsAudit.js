/* Actual guest public-framework caller. No native callback/publisher injection. */
import call from '@ohos.telephony.call';
import observer from '@ohos.telephony.observer';
import sim from '@ohos.telephony.sim';
import radio from '@ohos.telephony.radio';
import data from '@ohos.telephony.data';
import sms from '@ohos.telephony.sms';
import connection from '@ohos.bluetooth.connection';
import access from '@ohos.bluetooth.access';
import fs from '@ohos.file.fs';
import util from '@ohos.util';
import process from '@ohos.process';
import clock from '@ohos.systemDateTime';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';

const RUN = '__COMMUNICATIONS578_RUN__';
const RTT_ON = ['onRttModifyInd', 'onRttErrCause', 'onReceiveRttMessage'];
const RTT_OFF = ['offRttModifyInd', 'offRttErrCause', 'offReceiveRttMessage'];
const PUBLIC = [...RTT_ON, ...RTT_OFF, 'startRtt', 'stopRtt', 'setRttCapability', 'sendRttMessage'];
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const encoded = value => value === undefined ? { value_type: 'undefined' } : value;

export default class CommunicationsAudit {
  constructor(context) {
    this.context = context; this.seq = 0; this.used = new Set();
    this.serial = Promise.resolve(); this.listeners = new Map(); this.owned = new Map();
    this.bt = undefined; this.current = undefined;
    this.dataBaseline = undefined;
    this.rttCapabilityDirty = false;
  }
  now() { return clock.getUptime(clock.TimeType.STARTUP, false); }
  append(c, kind, value, code = 0, phase = 'sync') {
    const row = { schema: 1, run_id: RUN, boot_id: c.boot_id, operation_id: c.operation_id,
      case_id: c.case_id, action: c.action, api: c.api, seq: ++this.seq,
      monotonic_ms: this.now(), pid: process.pid, uid: process.uid,
      files_dir: this.context.filesDir,
      kind, code, phase, value: encoded(value) };
    const bytes = new util.TextEncoder().encodeInto(JSON.stringify(row) + '\n');
    const file = fs.openSync(this.context.filesDir + '/communications578-' + RUN + '.jsonl',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND | fs.OpenMode.NOFOLLOW);
    try {
      let n = 0;
      while (n < bytes.length) {
        const count = fs.writeSync(file.fd, bytes.slice(n).buffer);
        if (count <= 0 || count > bytes.length - n) throw new Error('Raw short write');
        n += count;
      }
    } finally { fs.closeSync(file); }
  }
  accept(value) {
    if (typeof value !== 'string' || value.length > 8192) throw new Error('Bounded request required');
    const c = JSON.parse(value);
    if (c.run_id !== RUN || !/^[a-f0-9-]{36}$/.test(c.boot_id) ||
        !/^[a-f0-9]{32}$/.test(c.operation_id) || this.used.has(c.operation_id) || this.used.size >= 1024 ||
        !/^[a-z0-9_-]{1,80}$/.test(c.case_id) || !['exports', 'consent', 'invoke', 'quiet', 'cleanup', 'identity'].includes(c.action)) {
      throw new Error('Invalid/fresh command required');
    }
    this.used.add(c.operation_id);
    this.serial = this.serial.then(() => this.execute(c));
  }
  callback(c) {
    const key = c.api + ':' + c.slot + ':' + c.listener;
    if (!this.listeners.has(key)) {
      const origin = { ...c };
      this.listeners.set(key, value => this.append(origin, 'callback',
        { listener: origin.listener, slot: origin.slot, payload: value }, 0, 'callback'));
    }
    return this.listeners.get(key);
  }
  functionFor(api) {
    if (PUBLIC.includes(api)) return [call, call[api]];
    if (['onCommunicationStateChange', 'offCommunicationStateChange'].includes(api)) return [observer, observer[api]];
    if (api === 'startPairOutOfBand') return [connection, connection.startPairOutOfBand];
    if (['enableBluetooth', 'disableBluetooth', 'getState'].includes(api)) return [access, access[api]];
    if (api === 'dialCall') return [call, call.dialCall];
    if (api === 'sendShortMessage') return [sms, sms.sendShortMessage];
    if (['enableCellularData', 'disableCellularData'].includes(api)) return [data, data[api]];
    throw new Error('Unlisted public API');
  }
  args(c) {
    let callback = this.callback(c);
    if (c.api.startsWith('offRtt')) {
      callback = this.callback({ ...c, api: 'on' + c.api.slice(3) });
    } else if (c.api === 'offReceiveRttMessage') {
      callback = this.callback({ ...c, api: 'onReceiveRttMessage' });
    } else if (c.api === 'offCommunicationStateChange') {
      callback = this.callback({ ...c, api: 'onCommunicationStateChange' });
    }
    if (c.form === 'missing') return [];
    if (c.form === 'undefined') return [undefined];
    if (c.form === 'null') return [null];
    if (c.form === 'nonfunction') return [7];
    if (c.form === 'extra') return [callback, undefined, 7];
    if (c.api.includes('CommunicationStateChange')) {
      if (c.form === 'fraction-slot') return [callback, { slotId: 0.5 }];
      if (c.form === 'negative-slot') return [callback, { slotId: -1 }];
      if (c.form === 'large-slot') return [callback, { slotId: 2147483647 }];
      if (c.form === 'undefined-options') return [callback, undefined];
      if (c.form === 'default-slot') return [callback];
      return [callback, { slotId: c.slot }];
    }
    if (RTT_ON.includes(c.api) || RTT_OFF.includes(c.api)) return [callback];
    if (['startRtt', 'stopRtt'].includes(c.api)) {
      return c.form === 'wrong-type' ? ['invalid', 1] : [c.call_id, c.api === 'startRtt' ? 1 : 0];
    }
    if (c.api === 'setRttCapability') return c.form === 'wrong-type' ? [0, 'invalid'] : [c.slot, c.enabled];
    if (c.api === 'sendRttMessage') return c.form === 'wrong-type' ? [c.call_id, 7] : [c.call_id, 'QEMU RTT no-session ' + RUN + ' 中文'];
    if (c.api === 'dialCall') return ['5550100', { accountId: 0 }];
    if (c.api === 'sendShortMessage') return [{ slotId: 0, destinationHost: '5550100', content: 'QEMU no-modem ' + RUN,
      sendCallback: (error, value) => this.append(c, 'sms-send',
        { error: encoded(error), info: encoded(value) }, error && error.code ? error.code : 0, 'callback'),
      deliveryCallback: (error, value) => this.append(c, 'sms-delivery',
        { error: encoded(error), info: encoded(value) }, error && error.code ? error.code : 0, 'callback') }];
    if (c.api === 'startPairOutOfBand') {
      const raw = { address: c.address, addressType: 2, rawAddressType: 0 };
      const oob = { deviceId: raw, confirmationHash: new Uint8Array(16).fill(0x19),
        randomizerHash: new Uint8Array(16).fill(0x34) };
      if (c.form === 'bad-address') return ['invalid', 0, oob];
      if (c.form === 'bad-transport') return [c.address, 0.5, oob];
      if (c.form === 'missing-oob') return [c.address, 0, undefined, undefined];
      if (c.form === 'short-confirmation') oob.confirmationHash = new Uint8Array(15);
      if (c.form === 'short-randomizer') oob.randomizerHash = new Uint8Array(15);
      if (c.form === 'omitted-randomizer') delete oob.randomizerHash;
      if (c.form === 'extra-oob-arg') return [c.address, 0, oob, undefined, 7];
      if (c.form === 'le-p192') return [c.address, 1, oob];
      if (c.form === 'p256') return [c.address, 0, undefined, oob];
      return [c.address, 0, oob];
    }
    return [];
  }
  async invoke(c) {
    const [receiver, fn] = this.functionFor(c.api);
    if (typeof fn !== 'function') throw new Error('Missing actual export: ' + c.api);
    let value;
    try { value = fn.apply(receiver, this.args(c)); }
    catch (e) { this.append(c, 'throw', { message: String(e.message) }, Number.isInteger(e.code) ? e.code : -1); return; }
    if (value && typeof value.then === 'function') {
      try { value = await value; }
      catch (e) { this.append(c, 'reject', { message: String(e.message) }, Number.isInteger(e.code) ? e.code : -1, 'promise'); return; }
    }
    if (c.api === 'setRttCapability') this.rttCapabilityDirty = c.enabled === true;
    if (RTT_ON.includes(c.api) || c.api === 'onCommunicationStateChange') {
      this.owned.set(c.api + ':' + c.slot + ':' + c.listener, { ...c });
    }
    if (c.api === 'onCommunicationStateChange' && c.form === 'queued-off') {
      // Keep this real JS environment busy while the root's actual AT peer
      // drives a native notification. The public off executes before the JS
      // event loop can dispatch that queued generation; callbacks still log
      // unconditionally, so late native dispatch cannot be hidden by the app.
      this.append(c, 'armed', { listener: c.listener, slot: c.slot, busy_ms: 5000 });
      const until = this.now() + 5000;
      while (this.now() < until) { /* bounded event-loop queue challenge */ }
      observer.offCommunicationStateChange(this.callback(c), { slotId: c.slot });
      this.append(c, 'cleanup-step', { api: 'offCommunicationStateChange', listener: c.listener, slot: c.slot });
    }
    this.append(c, 'return', value, 0, 'settled');
  }
  async state(c) {
    const slots = [0, 1];
    for (const slot of slots) {
      for (const api of ['hasSimCard', 'getSimState', 'getNetworkState', 'isRadioOn']) {
        try {
          let value;
          if (api === 'hasSimCard') value = await sim.hasSimCard(slot);
          if (api === 'getSimState') value = await sim.getSimState(slot);
          if (api === 'getNetworkState') value = await radio.getNetworkState(slot);
          if (api === 'isRadioOn') value = await radio.isRadioOn(slot);
          this.append(c, 'state', { slot, api, value: encoded(value) });
        } catch (e) { this.append(c, 'state', { slot, api, message: String(e.message) }, Number.isInteger(e.code) ? e.code : -1); }
      }
    }
    for (const api of ['hasCall', 'getCellularDataFlowType', 'getCellularDataState', 'isCellularDataEnabled']) {
      try {
        let value;
        if (api === 'hasCall') value = await call.hasCall();
        if (api === 'getCellularDataFlowType') value = await data.getCellularDataFlowType();
        if (api === 'getCellularDataState') value = await data.getCellularDataState();
        if (api === 'isCellularDataEnabled') {
          value = await data.isCellularDataEnabled();
          if (this.dataBaseline === undefined) this.dataBaseline = value;
        }
        this.append(c, 'state', { slot: -1, api, value: encoded(value) });
      } catch (e) { this.append(c, 'state', { slot: -1, api, message: String(e.message) }, Number.isInteger(e.code) ? e.code : -1); }
    }
  }
  async execute(c) {
    this.current = c; this.append(c, 'begin', c);
    try {
      switch (c.action) {
        case 'exports': {
          const map = {};
          for (const api of [...PUBLIC, 'onCommunicationStateChange', 'offCommunicationStateChange', 'startPairOutOfBand']) {
            map[api] = typeof this.functionFor(api)[1];
          }
          this.append(c, 'return', map); break;
        }
        case 'consent': {
          const grant = await abilityAccessCtrl.createAtManager().requestPermissionsFromUser(this.context, ['ohos.permission.ACCESS_BLUETOOTH']);
          this.append(c, 'return', { permissions: grant.permissions, authResults: grant.authResults }); break;
        }
        case 'identity': {
          const stat = fs.statSync(this.context.filesDir + '/communications578-' + RUN + '.jsonl');
          await this.state(c);
          this.append(c, 'return', { files_dir: this.context.filesDir, inode: stat.ino.toString(), journal_uid: stat.uid }); break;
        }
        case 'invoke': await this.invoke(c); break;
        case 'quiet': {
          if (!Number.isInteger(c.wait_ms) || c.wait_ms < 1000 || c.wait_ms > 30000) throw new Error('Bounded quiet required');
          if (c.api === 'bluetooth-state' && this.bt === undefined) {
            this.bt = value => this.append(c, 'bt-callback', value, 0, 'callback');
            access.on('stateChange', this.bt);
          }
          const until = this.now() + c.wait_ms;
          while (this.now() < until) {
            if (c.api === 'bluetooth-state') {
              this.append(c, 'bt-sample', { state: access.getState(), paired: connection.getPairedDevices() });
            }
            await sleep(100);
          }
          this.append(c, 'return', undefined); break;
        }
        case 'cleanup': {
          let failures = 0;
          if (this.rttCapabilityDirty) {
            try {
              await call.setRttCapability(0, false);
              this.rttCapabilityDirty = false;
              this.append(c, 'cleanup-step', { api: 'restoreRttCapabilityOff', slot: 0 });
            } catch (e) { ++failures; this.append(c, 'cleanup-step', { api: 'restoreRttCapabilityOff', message: String(e.message) }, Number.isInteger(e.code) ? e.code : -1); }
          }
          if (this.dataBaseline !== undefined) {
            try {
              if (this.dataBaseline) await data.enableCellularData(); else await data.disableCellularData();
              this.append(c, 'cleanup-step', { api: 'restoreCellularDataPolicy', baseline: this.dataBaseline,
                actual: await data.isCellularDataEnabled() });
            } catch (e) { ++failures; this.append(c, 'cleanup-step', { api: 'restoreCellularDataPolicy', message: String(e.message) }, Number.isInteger(e.code) ? e.code : -1); }
          }
          for (const owned of this.owned.values()) {
            const api = owned.api === 'onCommunicationStateChange' ? 'offCommunicationStateChange' : 'off' + owned.api.slice(2);
            const clean = { ...owned, api, form: 'callback' };
            try {
              const [receiver, fn] = this.functionFor(api);
              await fn.apply(receiver, this.args(clean));
              this.append(c, 'cleanup-step', { api, listener: owned.listener, slot: owned.slot });
            } catch (e) { ++failures; this.append(c, 'cleanup-step', { api, message: String(e.message) }, Number.isInteger(e.code) ? e.code : -1); }
          }
          if (!failures) this.owned.clear();
          if (this.bt !== undefined) { access.off('stateChange', this.bt); this.bt = undefined; }
          if (failures) throw new Error('Actual listener release failed');
          this.append(c, 'return', undefined); break;
        }
      }
    } catch (e) { this.append(c, 'throw', { message: String(e.message) }, Number.isInteger(e.code) ? e.code : -1); }
    this.append(c, 'end', undefined);
  }
}
