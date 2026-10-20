import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import vpn from '@ohos.net.vpn';
import fs from '@ohos.file.fs';
import { BusinessError } from '@ohos.base';
import { Journal, RUN } from './Journal';
import { Fixture } from './SysVpnConfig';

export class Driver {
  static stage?: window.WindowStage;
  static async snapshots(index: number, revision: number, phase: string, id: string, action: string): Promise<void> {
    const value = await vpn.getSysVpnConfig(Fixture.ownedVpnId(index));
    Journal.record(phase + '-get-' + index, JSON.stringify(value), revision, id, action);
    const all = await vpn.getSysVpnConfigList();
    const own = all.filter((item: vpn.SysVpnConfig) => item.vpnId === Fixture.ownedVpnId(index));
    if (own.length !== 1) { throw new Error('actual owned VPN store row missing or duplicated'); }
    Journal.record(phase + '-list-' + index, JSON.stringify(own[0]), revision, id, action);
  }
  static async boundary(method: string, id: string, action: string): Promise<void> {
    Journal.record('vpn-boundary-method', JSON.stringify(method), 0, id, action);
    try {
      if (method === 'addSysVpnConfig') { await vpn.addSysVpnConfig(Fixture.config(0, 0)); }
      else if (method === 'deleteSysVpnConfig') { await vpn.deleteSysVpnConfig(Fixture.ownedVpnId(0)); }
      else if (method === 'getSysVpnConfig') { await vpn.getSysVpnConfig(Fixture.ownedVpnId(0)); }
      else if (method === 'getSysVpnConfigList') { await vpn.getSysVpnConfigList(); }
      else if (method === 'getConnectedSysVpnConfig') { await vpn.getConnectedSysVpnConfig(); }
      else if (method === 'getConnectedVpnAppInfo') { await vpn.getConnectedVpnAppInfo(); }
      else { throw new Error('unknown compiled VPN method'); }
      Journal.record('vpn-boundary-returned', JSON.stringify(method), 0, id, action);
    } catch (error) { Journal.fail('vpn-boundary-error', error as BusinessError, id, action); }
  }
  static async invalid(config: vpn.SysVpnConfig, name: string, id: string, action: string): Promise<void> {
    Journal.record('invalid-input', JSON.stringify(name), 0, id, action);
    try {
      await vpn.addSysVpnConfig(config);
      Journal.record('invalid-returned', JSON.stringify(name), 0, id, action);
    } catch (error) { Journal.fail('invalid-error', error as BusinessError, id, action); }
  }
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    const marker = context.filesDir + '/apps579-sysvpn-owned-' + RUN + '.txt';
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'boundaries') {
      for (const method of ['addSysVpnConfig', 'deleteSysVpnConfig', 'getSysVpnConfig', 'getSysVpnConfigList',
        'getConnectedSysVpnConfig', 'getConnectedVpnAppInfo']) { await Driver.boundary(method, id, action); }
    } else if (action === 'connected') {
      // Disconnected behavior is recorded here. Positive connected values come
      // only from the original strict Network peer after actual tunnel setup.
      for (const method of ['getConnectedSysVpnConfig', 'getConnectedVpnAppInfo']) {
        try {
          const value = method === 'getConnectedSysVpnConfig' ? await vpn.getConnectedSysVpnConfig() :
            await vpn.getConnectedVpnAppInfo();
          Journal.record('connected-method', JSON.stringify(method), 0, id, action);
          Journal.record('connected-result', JSON.stringify(value), 0, id, action);
        } catch (error) {
          Journal.record('connected-method', JSON.stringify(method), 0, id, action);
          Journal.fail('connected-error', error as BusinessError, id, action);
        }
      }
    } else if (action === 'seed') {
      if (fs.accessSync(marker)) { throw new Error('owned VPN marker already exists; restore before reseed'); }
      const baseline = await vpn.getSysVpnConfigList();
      Journal.record('store-before', JSON.stringify(baseline), 0, id, action);
      const collided = baseline.filter((item: vpn.SysVpnConfig) => [Fixture.ownedVpnId(0), Fixture.ownedVpnId(1),
        Fixture.ownedVpnId(2)].includes(item.vpnId));
      if (collided.length !== 0) { throw new Error('nonce VPN rows pre-exist; refuse foreign mutation'); }
      const file = fs.openSync(marker, fs.OpenMode.CREATE | fs.OpenMode.EXCL | fs.OpenMode.WRITE_ONLY);
      try { fs.writeSync(file.fd, RUN); } finally { fs.closeSync(file); }
      for (let index: number = 0; index < 3; index++) {
        await vpn.addSysVpnConfig(Fixture.config(index, 0));
        await Driver.snapshots(index, 0, 'seed', id, action);
        await vpn.addSysVpnConfig(Fixture.config(index, 1));
        await Driver.snapshots(index, 1, 'replace', id, action);
      }
      for (let field: number = 0; field < 4; field++) {
        for (const family of [-1, 0, 3, 257, 258, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
          const invalid = Fixture.config(0, 1);
          if (invalid.localAddresses === undefined || invalid.routes === undefined) { throw new Error('rich fixture missing'); }
          if (field === 0) { invalid.addresses[0].address.family = family; }
          else if (field === 1) { invalid.localAddresses[0].address.family = family; }
          else if (field === 2) { invalid.routes[0].destination.address.family = family; }
          else { invalid.routes[0].gateway.family = family; }
          await Driver.invalid(invalid, 'family-' + field + '-' + String(family), id, action);
        }
        for (const port of [-1, 65536, 65537, 8080.5, 4294967297, Number.NaN, Number.POSITIVE_INFINITY]) {
          const invalid = Fixture.config(0, 1);
          if (invalid.localAddresses === undefined || invalid.routes === undefined) { throw new Error('rich fixture missing'); }
          if (field === 0) { invalid.addresses[0].address.port = port; }
          else if (field === 1) { invalid.localAddresses[0].address.port = port; }
          else if (field === 2) { invalid.routes[0].destination.address.port = port; }
          else { invalid.routes[0].gateway.port = port; }
          await Driver.invalid(invalid, 'port-' + field + '-' + String(port), id, action);
        }
      }
      for (const prefix of [-1, 0, 257, 2.5, Number.NaN, Number.POSITIVE_INFINITY]) {
        const invalid = Fixture.config(0, 1); invalid.addresses[0].prefixLength = prefix;
        await Driver.invalid(invalid, 'prefix-' + String(prefix), id, action);
      }
      for (let family: number = 0; family < 2; family++) {
        for (const prefix of [-1, family === 0 ? 33 : 129, 257, 2.5, Number.NaN, Number.POSITIVE_INFINITY]) {
          const invalid = Fixture.config(0, 1);
          if (invalid.routes === undefined) { throw new Error('rich fixture missing'); }
          invalid.routes[family].destination.prefixLength = prefix;
          await Driver.invalid(invalid, 'route-' + family + '-' + String(prefix), id, action);
        }
      }
      await Driver.snapshots(0, 1, 'after-invalid', id, action);
    } else if (action === 'verify-persisted') {
      if (fs.readTextSync(marker) !== RUN) { throw new Error('actual owned VPN marker missing after restart'); }
      for (let index: number = 0; index < 3; index++) { await Driver.snapshots(index, 1, 'restart', id, action); }
    } else if (action === 'cleanup') {
      const all = await vpn.getSysVpnConfigList();
      const owned = all.filter((item: vpn.SysVpnConfig) => [Fixture.ownedVpnId(0), Fixture.ownedVpnId(1),
        Fixture.ownedVpnId(2)].includes(item.vpnId));
      if (owned.length && (!fs.accessSync(marker) || fs.readTextSync(marker) !== RUN)) {
        throw new Error('refuse to delete unowned VPN store rows');
      }
      for (const item of owned) { await vpn.deleteSysVpnConfig(item.vpnId); }
      const after = await vpn.getSysVpnConfigList();
      Journal.record('store-after', JSON.stringify(after), 0, id, action);
      if (after.some((item: vpn.SysVpnConfig) => [Fixture.ownedVpnId(0), Fixture.ownedVpnId(1),
        Fixture.ownedVpnId(2)].includes(item.vpnId))) { throw new Error('owned store row survived deletion'); }
      if (fs.accessSync(marker)) { fs.unlinkSync(marker); }
    } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('unknown compiled VPN store action'); }
    Journal.record('done', 'null', 0, id, action);
  }
}
