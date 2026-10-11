// Real system VPN CRUD and caller-restart persistence. No tunnel/traffic claim.
import vpn from '@ohos.net.vpn';
import fs from '@ohos.file.fs';
import process from '@ohos.process';
import { BusinessError } from '@ohos.base';

interface Row {
  runId: string; role: string; name: string; values: number[]; config: string; error: string;
}

@Entry
@Component
struct Index {
  @State private note: string = 'System VPN store regression';
  private readonly nonce: string = '__SYSVPN_RUN__';
  private readonly role: string = '__SYSVPN_ROLE__';
  private readonly path: string = '/data/storage/el2/base/files/sys-vpn-store-__SYSVPN_RUN__-results.log';
  private readonly marker: string = '/data/storage/el2/base/files/sys-vpn-store-__SYSVPN_RUN__-seed';
  private readonly types: vpn.SysVpnType[] = [vpn.SysVpnType.OPENVPN,
    vpn.SysVpnType.IKEV2_IPSEC_PSK, vpn.SysVpnType.L2TP_IPSEC_PSK];

  private record(name: string, values: number[] = [], config: string = '', error: string = ''): void {
    const row: Row = { runId: this.nonce, role: this.role, name, values, config, error };
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
    this.note = name;
  }
  private ownedVpnId(index: number): string {
    const hex = this.nonce.substring(0, 31) + index.toString();
    return hex.substring(0, 8) + '-' + hex.substring(8, 12) + '-' + hex.substring(12, 16) + '-' +
      hex.substring(16, 20) + '-' + hex.substring(20);
  }
  private config(index: number, revision: number): vpn.SysVpnConfig {
    const config: vpn.SysVpnConfig = {
      vpnId: this.ownedVpnId(index), vpnName: 'audit-' + this.nonce + '-' + revision,
      vpnType: this.types[index], userName: 'audit-' + this.nonce, password: 'synthetic-' + this.nonce,
      saveLogin: true, forwardingRoutes: '198.18.0.0/24',
      addresses: [{ address: { address: '198.18.0.2', family: 1, port: revision === 0 ? 8080 : 65535 }, prefixLength: 24 },
        { address: { address: '2001:db8::2', family: 2, port: revision === 0 ? 65535 : 256 }, prefixLength: 64 }],
      localAddresses: [{ address: { address: '198.18.0.6', family: 1, port: revision === 0 ? 256 : 8080 }, prefixLength: 28 },
        { address: { address: '2001:db8::6', family: 2, port: revision === 0 ? 255 : 0 }, prefixLength: 96 }],
      remoteAddresses: ['198.19.0.1', '2001:db8:1::1'],
      dnsAddresses: ['198.18.0.53', '2001:db8::53'],
      searchDomains: ['a.' + this.nonce + '.invalid', 'b.' + this.nonce + '.invalid'],
      mtu: 1400 + revision, isIPv4Accepted: true, isIPv6Accepted: true, isLegacy: false, isBlocking: true,
      trustedApplications: revision === 0 ? ['org.harmonycontrib.capabilityaudit', 'org.harmonycontrib.other'] : [],
      blockedApplications: revision === 1 ? ['org.harmonycontrib.blocked', 'org.harmonycontrib.blocked2'] : [],
      routes: [{ interface: 'vpn-tun', destination: {
        address: { address: '198.18.1.0', family: 1, port: revision === 0 ? 65535 : 8080 },
        prefixLength: index === 0 ? (revision === 0 ? 0 : 32) : 24 },
        gateway: { address: '198.18.0.1', family: 1, port: revision === 0 ? 8080 : 65535 },
        hasGateway: true, isDefaultRoute: index === 0 && revision === 0, isExcludedRoute: false },
        { interface: 'vpn-tun', destination: {
          address: { address: '2001:db8:2::', family: 2, port: revision === 0 ? 256 : 65535 },
          prefixLength: index === 0 ? (revision === 0 ? 0 : 128) : 64 },
          gateway: { address: '2001:db8::1', family: 2, port: revision === 0 ? 65535 : 255 },
          hasGateway: false, isDefaultRoute: index === 0 && revision === 0, isExcludedRoute: true }]
    };
    if (index === 0) {
      const open = config as vpn.OpenVpnConfig;
      open.ovpnPort = '1194'; open.ovpnProtocol = 0; open.ovpnAuthType = 0;
      open.ovpnConfig = 'audit-config-' + this.nonce; open.askpass = 'synthetic-askpass-' + this.nonce;
    } else if (index === 1) {
      const ipsec = config as vpn.IpsecVpnConfig;
      ipsec.ipsecPreSharedKey = 'synthetic-psk-' + this.nonce; ipsec.ipsecIdentifier = 'audit-identifier';
    } else {
      const l2tp = config as vpn.L2tpVpnConfig;
      l2tp.ipsecPreSharedKey = 'synthetic-psk-' + this.nonce; l2tp.ipsecIdentifier = 'audit-identifier';
      l2tp.l2tpSharedKey = 'synthetic-l2tp-' + this.nonce;
    }
    return config;
  }
  private async rejected(method: number, config: vpn.SysVpnConfig, id: string): Promise<number[]> {
    try {
      if (method === 0) { await vpn.addSysVpnConfig(config); }
      else if (method === 1) { await vpn.getSysVpnConfig(id); }
      else if (method === 2) { await vpn.getSysVpnConfigList(); }
      else { await vpn.deleteSysVpnConfig(id); }
      return [0, 0, 0];
    } catch (error) {
      const code = (error as BusinessError).code;
      return [1, code, typeof code === 'number' ? 1 : 0];
    }
  }
  private async roundTrip(index: number, revision: number, phase: string): Promise<void> {
    const config = await vpn.getSysVpnConfig(this.ownedVpnId(index));
    this.record(phase + '.get.' + index, [revision], JSON.stringify(config));
    const list = await vpn.getSysVpnConfigList();
    const owned = list.filter((item: vpn.SysVpnConfig) => item.vpnId === this.ownedVpnId(index));
    if (owned.length !== 1) { throw new Error('owned config is missing/duplicated in native list'); }
    this.record(phase + '.list.' + index, [revision], JSON.stringify(owned[0]));
  }
  private async defaultFamily(explicitUndefined: boolean): Promise<void> {
    const config = this.config(0, 1);
    if (config.localAddresses === undefined || config.routes === undefined) {
      throw new Error('real local addresses and routes required');
    }
    config.addresses[0].address = { address: '198.18.0.2', port: 65535 };
    config.localAddresses[0].address = { address: '198.18.0.6', port: 8080 };
    config.routes[0].destination.address = { address: '198.18.1.0', port: 8080 };
    config.routes[0].gateway = { address: '198.18.0.1', port: 65535 };
    if (explicitUndefined) {
      config.addresses[0].address.family = undefined;
      config.localAddresses[0].address.family = undefined;
      config.routes[0].destination.address.family = undefined;
      config.routes[0].gateway.family = undefined;
    }
    await vpn.addSysVpnConfig(config);
    await this.roundTrip(0, 1, explicitUndefined ? 'undefined-family' : 'default-family');
  }
  private async cleanup(): Promise<void> {
    for (let index = 0; index < 3; index++) { await vpn.deleteSysVpnConfig(this.ownedVpnId(index)); }
    const remaining = (await vpn.getSysVpnConfigList()).filter((item: vpn.SysVpnConfig) =>
      item.vpnId === this.ownedVpnId(0) || item.vpnId === this.ownedVpnId(1) || item.vpnId === this.ownedVpnId(2));
    this.record('cleanup', [remaining.length]);
    if (remaining.length !== 0) { throw new Error('owned configuration cleanup failed'); }
    if (fs.accessSync(this.marker)) { fs.unlinkSync(this.marker); }
  }
  private async defaultPort(explicitUndefined: boolean): Promise<void> {
    const config = this.config(0, 1);
    if (config.localAddresses === undefined || config.routes === undefined) {
      throw new Error('real local addresses and routes required');
    }
    config.addresses[0].address = { address: '198.18.0.2', family: 1 };
    config.localAddresses[0].address = { address: '198.18.0.6', family: 1 };
    config.routes[0].destination.address = { address: '198.18.1.0', family: 1 };
    config.routes[0].gateway = { address: '198.18.0.1', family: 1 };
    if (explicitUndefined) {
      config.addresses[0].address.port = undefined;
      config.localAddresses[0].address.port = undefined;
      config.routes[0].destination.address.port = undefined;
      config.routes[0].gateway.port = undefined;
    }
    await vpn.addSysVpnConfig(config);
    await this.roundTrip(0, 1, explicitUndefined ? 'undefined-port' : 'default-port');
  }
  private async run(): Promise<void> {
    let seeded = false;
    let completed = false;
    let ownsRows = false;
    try {
      this.record('identity', [process.uid, process.euid, process.pid]);
      if (this.role !== 'system') {
        for (let method = 0; method < 4; method++) {
          this.record('denied.' + method, await this.rejected(method, this.config(0, 0), this.ownedVpnId(0)));
        }
      } else if (fs.accessSync(this.marker)) {
        ownsRows = true;
        for (let index = 0; index < 3; index++) { await this.roundTrip(index, 1, 'restart'); }
        await this.cleanup(); ownsRows = false;
      } else {
        const initial = await vpn.getSysVpnConfigList();
        this.record('initial', [initial.length]);
        if (initial.length !== 0) { throw new Error('not a fresh disposable VPN store'); }
        for (let index = 0; index < 3; index++) {
          ownsRows = true;
          await vpn.addSysVpnConfig(this.config(index, 0));
          await this.roundTrip(index, 0, 'seed');
          await vpn.addSysVpnConfig(this.config(index, 1));
          await this.roundTrip(index, 1, 'replace');
        }
        await this.defaultFamily(false);
        await this.defaultFamily(true);
        await this.defaultPort(false);
        await this.defaultPort(true);
        await vpn.addSysVpnConfig(this.config(0, 1));
        await this.roundTrip(0, 1, 'ports-restored');
        for (let field = 0; field < 4; field++) {
          for (const family of [-1, 0, 3, 257, 258, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
            const invalid = this.config(0, 1);
            if (invalid.localAddresses === undefined || invalid.routes === undefined) {
              throw new Error('real local addresses and routes required');
            }
            if (field === 0) { invalid.addresses[0].address.family = family; }
            else if (field === 1) { invalid.localAddresses[0].address.family = family; }
            else if (field === 2) { invalid.routes[0].destination.address.family = family; }
            else { invalid.routes[0].gateway.family = family; }
            this.record('invalid.family.' + field, await this.rejected(0, invalid, this.ownedVpnId(0)));
          }
        }
        for (let field = 0; field < 4; field++) {
          for (const port of [-1, 65536, 65537, 8080.5, 4294967297, Number.NaN, Number.POSITIVE_INFINITY]) {
            const invalid = this.config(0, 1);
            if (invalid.localAddresses === undefined || invalid.routes === undefined) {
              throw new Error('real local addresses and routes required');
            }
            if (field === 0) { invalid.addresses[0].address.port = port; }
            else if (field === 1) { invalid.localAddresses[0].address.port = port; }
            else if (field === 2) { invalid.routes[0].destination.address.port = port; }
            else { invalid.routes[0].gateway.port = port; }
            this.record('invalid.port.' + field, await this.rejected(0, invalid, this.ownedVpnId(0)));
          }
        }
        for (const prefix of [-1, 0, 257, 2.5, Number.NaN, Number.POSITIVE_INFINITY]) {
          const invalid = this.config(0, 1); invalid.addresses[0].prefixLength = prefix;
          this.record('invalid.prefix', await this.rejected(0, invalid, this.ownedVpnId(0)));
        }
        for (let family = 0; family < 2; family++) {
          const invalidPrefixes: number[] = [-1, family === 0 ? 33 : 129, 257, 2.5,
            Number.NaN, Number.POSITIVE_INFINITY];
          for (const prefix of invalidPrefixes) {
            const invalid = this.config(0, 1);
            if (invalid.routes === undefined) { throw new Error('real routes required'); }
            invalid.routes[family].destination.prefixLength = prefix;
            this.record('invalid.route.' + family, await this.rejected(0, invalid, this.ownedVpnId(0)));
          }
        }
        await this.roundTrip(0, 1, 'after-invalid');
        const marker = fs.openSync(this.marker, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY);
        try { fs.writeSync(marker.fd, this.nonce); } finally { fs.closeSync(marker); }
        seeded = true;
      }
      completed = true;
    } catch (error) {
      this.record('failed', [], '', (error as Error).message || 'system VPN store failure');
    } finally {
      if (ownsRows && !seeded) {
        try { await this.cleanup(); }
        catch (error) { completed = false; this.record('cleanup.failed', [], '', String(error)); }
      }
      this.record('summary', [completed ? 1 : 0, seeded ? 1 : 0]);
    }
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file); this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
