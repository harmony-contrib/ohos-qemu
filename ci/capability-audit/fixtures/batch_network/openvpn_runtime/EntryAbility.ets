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

export default class EntryAbility extends UIAbility {
  private connection?: vpn.VpnConnection;
  private sequence: number = 0;
  private chain: Promise<void> = Promise.resolve();
  private operation: string = '';
  private token: number = 0;
  private boot: string = '';
  private diagnostic: LocalStorage = new LocalStorage();

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
      !['setup', 'destroy', 'inspect'].includes(r.action) || (this.boot !== '' && this.boot !== r.boot_id)) {
      throw new Error('Foreign or repeated OpenVPN QA operation');
    }
    this.operation = r.operation_id; this.boot = r.boot_id;
    this.diagnostic.setOrCreate('diagnostic', 'Actual request ' + r.action + ' ' + r.operation_id);
    this.token = bundleManager.getBundleInfoForSelfSync(
      bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_APPLICATION).appInfo.accessTokenId;
    this.row(r, 'begin');
    try {
      const grant = abilityAccessCtrl.createAtManager().checkAccessTokenSync(this.token, 'ohos.permission.MANAGE_VPN');
      this.row(r, 'permission', grant);
      if (grant !== 0) { throw new Error('MANAGE_VPN is not actually granted'); }
      if (r.action === 'setup') {
        if (this.connection === undefined) { this.connection = vpn.createVpnConnection(this.context); }
        const config: vpn.OpenVpnConfig = {
          addresses: [], userId: 100, vpnId: '__VPN_ID__', vpnName: 'qa-__RUN__', vpnType: vpn.SysVpnType.OPENVPN,
          ovpnConfig: '__PROFILE_BASE64__', ovpnPort: '__PORT__', ovpnProtocol: 0, ovpnAuthType: 0,
          isIPv4Accepted: true, isIPv6Accepted: false, isBlocking: false
        };
        const result = await this.connection.setUp(config);
        this.row(r, 'resolved', 0, JSON.stringify(result)); // Acceptance is never CONNECTED.
      } else if (r.action === 'destroy') {
        if (this.connection === undefined) { throw new Error('No owned connection object'); }
        await this.connection.destroy();
        this.row(r, 'resolved');
      } else { this.row(r, 'resolved'); }
    } catch (error) {
      const code = (error as BusinessError).code;
      this.row(r, 'rejected', typeof code === 'number' ? code : -1, String(error));
    }
    try {
      const config = await vpn.getConnectedSysVpnConfig();
      const apps = await vpn.getConnectedVpnAppInfo();
      this.row(r, 'getters', 0, JSON.stringify({ config_undefined: config === undefined, apps: apps }));
    } catch (error) { this.row(r, 'getter-error', -1, String(error)); }
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
