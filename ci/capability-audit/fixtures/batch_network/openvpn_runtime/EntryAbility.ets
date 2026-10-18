import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
import vpn from '@ohos.net.vpn';
import fs from '@ohos.file.fs';
import process from '@ohos.process';
import bundleManager from '@ohos.bundle.bundleManager';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import { BusinessError } from '@ohos.base';

interface Request { run_id: string; boot_id: string; operation_id: string; action: string; }
interface Row {
  schema_version: number; run_id: string; boot_id: string; operation_id: string; action: string;
  sequence: number; uid: number; pid: number; token_id: number; event: string; code: number; value: string;
}


interface StoredRecord { vpn_id: string; vpn_name: string; vpn_type: number; user_id: number; }
interface ConfigObservation { stage: string; vpn_id: string; rows: StoredRecord[]; profile_equal: boolean; expected_type: number; }
interface ApiFailure { code: number; message: string; name: string; phase: string; }

export default class EntryAbility extends UIAbility {
  private connection?: vpn.VpnConnection;
  private sequence: number = 0;
  private chain: Promise<void> = Promise.resolve();
  private operation: string = '';
  private token: number = 0;
  private boot: string = '';
  private diagnostic: LocalStorage = new LocalStorage();

  private apiPhase: string = 'request-validation';
  private baseline?: StoredRecord[];
  private addAttempted: boolean = false;
  private stored: boolean = false;

  private config(): vpn.OpenVpnConfig {
    return { addresses: [], userId: 100, vpnId: '__VPN_ID__', vpnName: 'qa-__RUN__',
      vpnType: vpn.SysVpnType.OPENVPN, ovpnConfig: '__PROFILE_BASE64__', ovpnPort: '__PORT__', ovpnProtocol: 0,
      ovpnAuthType: 0, isIPv4Accepted: true, isIPv6Accepted: false, isBlocking: false };
  }
  private failure(error: BusinessError): ApiFailure {
    return { code: typeof error.code === 'number' ? error.code : -1,
      message: typeof error.message === 'string' ? error.message : String(error),
      name: typeof error.name === 'string' ? error.name : 'unknown', phase: this.apiPhase };
  }
  private async records(): Promise<StoredRecord[]> {
    this.apiPhase = 'getSysVpnConfigList';
    const configs = await vpn.getSysVpnConfigList();
    this.apiPhase = 'validate-public-list';
    if (!Array.isArray(configs) || configs.length > 128) { throw new Error('Complete bounded public config list required'); }
    const rows: StoredRecord[] = [];
    const ids: string[] = [];
    for (const item of configs) {
      if (typeof item.vpnId !== 'string' || !/^[A-Za-z0-9_.:-]{1,128}$/.test(item.vpnId) || ids.includes(item.vpnId) ||
        typeof item.vpnName !== 'string' || item.vpnName.length > 1024 ||
        typeof item.vpnType !== 'number' || !Number.isInteger(item.vpnType) || item.vpnType < 0 || item.vpnType > 65535 ||
        typeof item.userId !== 'number' || item.userId !== 100) { throw new Error('Malformed/foreign-account public config list'); }
      ids.push(item.vpnId);
      rows.push({ vpn_id: item.vpnId, vpn_name: item.vpnName, vpn_type: item.vpnType, user_id: item.userId });
    }
    return rows.sort((a: StoredRecord, b: StoredRecord) => a.vpn_id < b.vpn_id ? -1 : a.vpn_id > b.vpn_id ? 1 : 0);
  }
  private observeConfig(r: Request, stage: string, rows: StoredRecord[], equal: boolean = false): void {
    const observation: ConfigObservation = { stage: stage, vpn_id: '__VPN_ID__', rows: rows, profile_equal: equal, expected_type: vpn.SysVpnType.OPENVPN };
    this.row(r, 'config-state', 0, JSON.stringify(observation)); // Metadata only; never serialize credentials/profile.
  }
  private async exactOwnConfig(): Promise<void> {
    this.apiPhase = 'getSysVpnConfig';
    const actual = await vpn.getSysVpnConfig('__VPN_ID__') as vpn.OpenVpnConfig;
    const expected = this.config();
    this.apiPhase = 'validate-owned-config';
    if (actual === undefined || actual.vpnId !== expected.vpnId || actual.vpnName !== expected.vpnName ||
      actual.userId !== 100 || actual.vpnType !== expected.vpnType || actual.ovpnConfig !== expected.ovpnConfig ||
      actual.ovpnPort !== expected.ovpnPort || actual.ovpnProtocol !== expected.ovpnProtocol ||
      actual.ovpnAuthType !== expected.ovpnAuthType) { throw new Error('Public stored config differs from this owned run'); }
  }
  private async storeConfig(r: Request): Promise<void> {
    this.apiPhase = 'store-ownership';
    if (this.addAttempted || this.baseline !== undefined) { throw new Error('No adoption, upsert or repeated store'); }
    const before = await this.records(); this.observeConfig(r, 'before-store', before);
    this.apiPhase = 'fresh-UUID-absence';
    if (before.some((item: StoredRecord) => item.vpn_id === '__VPN_ID__')) { throw new Error('Fresh owned UUID already exists; preserve it'); }
    this.baseline = before;
    this.addAttempted = true; // Retain this cut even if the actual public add rejects after a partial write.
    this.apiPhase = 'addSysVpnConfig';
    await vpn.addSysVpnConfig(this.config());
    const after = await this.records();
    const own = after.filter((item: StoredRecord) => item.vpn_id === '__VPN_ID__');
    const others = after.filter((item: StoredRecord) => item.vpn_id !== '__VPN_ID__');
    this.apiPhase = 'validate-store-metadata';
    if (own.length !== 1 || JSON.stringify(others) !== JSON.stringify(this.baseline)) { throw new Error('Public add changed foreign records or omitted owned UUID'); }
    await this.exactOwnConfig();
    this.observeConfig(r, 'after-store', after, true); this.stored = true;
  }
  private async removeConfig(r: Request): Promise<void> {
    this.apiPhase = 'remove-config-ownership';
    if (!this.addAttempted || this.baseline === undefined) { throw new Error('No proved owned add attempt; preserve unknown config'); }
    const before = await this.records(); this.observeConfig(r, 'before-remove', before);
    const own = before.filter((item: StoredRecord) => item.vpn_id === '__VPN_ID__');
    const others = before.filter((item: StoredRecord) => item.vpn_id !== '__VPN_ID__');
    this.apiPhase = 'validate-remove-metadata';
    if (own.length > 1 || JSON.stringify(others) !== JSON.stringify(this.baseline)) { throw new Error('Unknown public config change; preserve all records'); }
    if (own.length === 1) {
      await this.exactOwnConfig();
      this.apiPhase = 'deleteSysVpnConfig';
      await vpn.deleteSysVpnConfig('__VPN_ID__'); // Only this fresh UUID, never the database or another owner.
    }
    const after = await this.records();
    this.apiPhase = 'validate-public-absence';
    if (JSON.stringify(after) !== JSON.stringify(this.baseline)) { throw new Error('Owned UUID deletion or foreign-record preservation unproved'); }
    this.observeConfig(r, 'after-remove', after); this.stored = false;
  }

  private row(r: Request, event: string, code: number = 0, value: string = ''): void {
    const row: Row = { schema_version: 1, run_id: '__RUN__', boot_id: r.boot_id,
      operation_id: r.operation_id, action: r.action, sequence: ++this.sequence, uid: process.uid,
      pid: process.pid, token_id: this.token, event: event, code: code, value: value };
    const file = fs.openSync(this.context.getApplicationContext().filesDir + '/openvpn-__RUN__.jsonl',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND | fs.OpenMode.NOFOLLOW);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
  }

  private async call(r: Request): Promise<void> {
    if (r.run_id !== '__RUN__' || !/^[a-f0-9]{32}$/.test(r.operation_id) ||
      !/^[a-f0-9-]{36}$/.test(r.boot_id) || r.operation_id === this.operation ||
      !['store', 'setup', 'destroy', 'remove-config', 'inspect'].includes(r.action) || (this.boot !== '' && this.boot !== r.boot_id)) {
      throw new Error('Foreign or repeated OpenVPN QA operation');
    }
    this.operation = r.operation_id; this.boot = r.boot_id;
    this.diagnostic.setOrCreate('diagnostic', 'Actual request ' + r.action + ' ' + r.operation_id);
    this.token = bundleManager.getBundleInfoForSelfSync(
      bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_APPLICATION).appInfo.accessTokenId;
    this.row(r, 'begin');
    try {
      this.apiPhase = 'checkAccessTokenSync';
      const grant = abilityAccessCtrl.createAtManager().checkAccessTokenSync(this.token, 'ohos.permission.MANAGE_VPN');
      this.row(r, 'permission', grant);
      if (grant !== 0) { throw new Error('MANAGE_VPN is not actually granted'); }
      if (r.action === 'store') {
        await this.storeConfig(r); this.row(r, 'resolved');
      } else if (r.action === 'remove-config') {
        await this.removeConfig(r); this.row(r, 'resolved');
      } else if (r.action === 'setup') {
        this.apiPhase = 'setup-ownership';
        if (!this.stored) { throw new Error('Actual public config save required before ordinary setup'); }
        await this.exactOwnConfig();
        if (this.connection === undefined) { this.apiPhase = 'createVpnConnection'; this.connection = vpn.createVpnConnection(this.context); }
        this.apiPhase = 'setUp';
        const result = await this.connection.setUp(this.config());
        this.row(r, 'resolved', 0, JSON.stringify(result)); // Acceptance is never CONNECTED.
      } else if (r.action === 'destroy') {
        this.apiPhase = 'destroy-ownership';
        if (this.connection === undefined) { throw new Error('No owned connection object'); }
        this.apiPhase = 'destroy';
        await this.connection.destroy();
        this.row(r, 'resolved');
      } else { this.row(r, 'resolved'); }
    } catch (error) {
      const detail = this.failure(error as BusinessError);
      this.row(r, 'rejected', detail.code, JSON.stringify(detail));
    }
    try {
      this.apiPhase = 'getConnectedSysVpnConfig';
      const config = await vpn.getConnectedSysVpnConfig();
      this.apiPhase = 'getConnectedVpnAppInfo';
      const apps = await vpn.getConnectedVpnAppInfo();
      this.row(r, 'getters', 0, JSON.stringify({ config_undefined: config === undefined, apps: apps }));
    } catch (error) { const detail = this.failure(error as BusinessError); this.row(r, 'getter-error', detail.code, JSON.stringify(detail)); }
    this.row(r, 'complete');
  }

  private receive(want: Want): void {
    const serialized = want.parameters?.request;
    if (typeof serialized !== 'string') { throw new Error('Exact request string required'); }
    const request = JSON.parse(serialized) as Request;
    this.chain = this.chain.then(() => this.call(request));
    this.chain.catch((error: BusinessError) => {
      this.diagnostic.setOrCreate('diagnostic', 'Failed ' + String(error.code) + ' ' + String(error).slice(0, 512));
      // Observe rejection only: the original chain stays rejected. No API completion or recovery.
    });
  }
  onCreate(want: Want): void { this.receive(want); }
  onNewWant(want: Want): void { this.receive(want); }
  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index', this.diagnostic); }
}
