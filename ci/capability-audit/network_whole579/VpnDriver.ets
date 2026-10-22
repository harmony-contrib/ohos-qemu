import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import vpn from '@ohos.net.vpn';
import connection from '@ohos.net.connection';
import socket from '@ohos.net.socket';
import account from '@ohos.account.osAccount';
import util from '@ohos.util';
import fs from '@ohos.file.fs';
import { BusinessError } from '@ohos.base';
import { Journal, RUN, ROLE } from './Journal';

// The actual original peer profile is injected by the normal source builder.
// Neither the profile nor credentials are journalled.
const PROFILE: string = __PROFILE_TEXT_JSON__;
const PEER_RUN: string = '__PEER_RUN__';
interface ConnectState { isConnected: boolean; }
interface MultiState { isConnected: boolean; bundleName: string; vpnId: string; }
interface PublicConfig { defined: boolean; vpnId?: string; userId?: number; addresses?: connection.LinkAddress[];
  routes?: connection.RouteInfo[]; dnsAddresses?: string[]; mtu?: number; }

export class Driver {
  static stage?: window.WindowStage;
  static connection?: vpn.VpnConnection;
  static connected: boolean = false;
  static watch?: (state: ConnectState) => void;
  static multi?: (state: MultiState) => void;
  static ident(): string { return RUN + '-' + ROLE; }
  static async config(option: string = ''): Promise<vpn.OpenVpnConfig> {
    const user = await account.getAccountManager().getOsAccountLocalId();
    const encoder = new util.TextEncoder();
    return {addresses: [], vpnId: Driver.ident(), vpnName: 'whole579-' + RUN + '-' + ROLE,
      userId: user, vpnType: vpn.SysVpnType.OPENVPN,
      ovpnConfig: new util.Base64Helper().encodeToStringSync(encoder.encodeInto(PROFILE + option)),
      ovpnPort: '54124', ovpnProtocol: 0, ovpnAuthType: 0,
      isIPv4Accepted: true, isIPv6Accepted: true, isBlocking: false};
  }
  static async state(id: string, action: string): Promise<void> {
    const current = await vpn.getConnectedSysVpnConfig();
    const value: PublicConfig = current === undefined ? {defined: false} : {
      defined: true, vpnId: current.vpnId, userId: current.userId, addresses: current.addresses,
      routes: current.routes, dnsAddresses: current.dnsAddresses, mtu: current.mtu};
    Journal.record('connected-config', JSON.stringify(value), 0, id, action);
    Journal.record('connected-app', JSON.stringify(await vpn.getConnectedVpnAppInfo()), 0, id, action);
    Journal.record('actual-account', JSON.stringify(await account.getAccountManager().getOsAccountLocalId()), 0, id, action);
    for (const net of await connection.getAllNets()) {
      const caps = await connection.getNetCapabilities(net);
      if (caps.bearerTypes.includes(connection.NetBearType.BEARER_VPN)) {
        Journal.record('vpn-properties', JSON.stringify({netId: net.netId, capabilities: caps,
          properties: await connection.getConnectionProperties(net)}), 0, id, action);
      }
    }
  }
  static async traffic(family: number, id: string, action: string, administration: string = ''): Promise<void> {
    const peer = family === 1 ? '10.73.0.1' : 'fd73:579::1';
    const client = util.generateRandomUUID(false).replace(/-/g, '');
    const operation = util.generateRandomUUID(false).replace(/-/g, '');
    const prefix = PEER_RUN + ' ' + operation + ' ' + client;
    const udp = socket.constructUDPSocketInstance();
    let timer: number = -1;
    try {
      let finish: (value: string) => void = (value: string): void => {};
      const response = new Promise<string>((resolve) => { finish = resolve; });
      let server: string = '';
      udp.on('error', (error: BusinessError) => { Journal.fail('socket-error', error, id, action); finish('error'); });
      udp.on('message', (info: socket.SocketMessageInfo) => {
        const bytes = new Uint8Array(info.message);
        if (bytes.length > 512 || info.remoteInfo.port !== 46074 || info.remoteInfo.address !== peer) {
          finish('foreign'); return;
        }
        let text = ''; for (const b of bytes) { text += String.fromCharCode(b); }
        Journal.record('nonce-rx', JSON.stringify({family, peer, text}), 0, id, action);
        const fields = text.split(' ');
        if (fields.length !== 5 || fields.slice(1, 4).join(' ') !== prefix || !/^[a-f0-9]{32}$/.test(fields[4])) {
          finish('foreign'); return;
        }
        if (fields[0] === 'VPN1' && (server === '' || server === fields[4])) {
          server = fields[4];
          udp.send({data: 'VPN2 ' + prefix + ' ' + server, address: {address: peer, port: 46074, family}})
            .catch((error: BusinessError) => { Journal.fail('socket-error', error, id, action); finish('error'); });
        } else if (fields[0] === 'VPN3' && fields[4] === server) { finish(text); }
        else { finish('foreign'); }
      });
      await udp.bind({address: family === 1 ? '0.0.0.0' : '::', port: 0, family});
      Journal.record('nonce-bound', JSON.stringify(await udp.getLocalAddress()), 0, id, action);
      timer = setTimeout(() => { finish('timeout'); }, 5000);
      Journal.record('nonce-tx', JSON.stringify({family, peer, operation, client, text: 'VPN1 ' + prefix}), 0, id, action);
      await udp.send({data: 'VPN1 ' + prefix, address: {address: peer, port: 46074, family}});
      const actual = await response;
      Journal.record('nonce-result', JSON.stringify({family, peer, actual}), 0, id, action);
      if ((administration === 'VPNR' || administration === 'VPNQ') && actual === 'VPN3 ' + prefix + ' ' + server) {
        const request = administration + ' ' + prefix + ' ' + server;
        await udp.send({data: request, address: {address: peer, port: 46074, family}});
        Journal.record('peer-reconfigure-requested', JSON.stringify(request), 0, id, action);
      }
    } finally {
      if (timer >= 0) { clearTimeout(timer); }
      udp.off('message'); udp.off('error'); await udp.close(); Journal.record('socket-closed', 'null', 0, id, action);
    }
  }
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'watch') {
      if (Driver.watch !== undefined || Driver.multi !== undefined) { throw new Error('duplicate callback registration'); }
      Driver.watch = (state: ConnectState) => Journal.record('vpn-connect', JSON.stringify(state), 0, id, action);
      Driver.multi = (state: MultiState) => Journal.record('vpn-connect-multi', JSON.stringify(state), 0, id, action);
      vpn.on('connect', Driver.watch); vpn.on('connectMulti', Driver.multi); Journal.record('watch-registered');
    } else if (action === 'off') {
      if (Driver.watch !== undefined) { vpn.off('connect', Driver.watch); }
      if (Driver.multi !== undefined) { vpn.off('connectMulti', Driver.multi); }
      Driver.watch = undefined; Driver.multi = undefined; Journal.record('watch-removed');
    } else if (action === 'setup' || action === 'option' || action === 'failure-setup') {
      const option = Journal.payload.option;
      const options: Record<string, string> = __OPTION_MAP_JSON__;
      if (action === 'option' && (typeof option !== 'string' || options[option] === undefined)) { throw new Error('fixed option variant required'); }
      try {
        if (Driver.connection === undefined) { Driver.connection = vpn.createVpnConnection(context); }
        let config = await Driver.config(action === 'option' ? options[option as string] : '');
        if (action === 'failure-setup') {
          const failing = PROFILE.replace('verify-x509-name qemu-owned-peer name', 'verify-x509-name wrong-whole579-peer name') + '\ntls-exit\nhand-window 3\n';
          config.ovpnConfig = new util.Base64Helper().encodeToStringSync(new util.TextEncoder().encodeInto(failing));
        }
        // Public SystemVpn consumes its stored configuration. An extension's
        // in-memory profile path is deliberately not used for these owners.
        if (config.userId === 100) {
          const marker = context.filesDir + '/network-whole579-store-' + RUN + '-' + ROLE;
          const all = await vpn.getSysVpnConfigList();
          const own = all.filter((item: vpn.SysVpnConfig) => item.vpnId === Driver.ident());
          if (own.length > 1 || (own.length === 1 && (!fs.accessSync(marker) || fs.readTextSync(marker) !== Driver.ident()))) {
            throw new Error('refuse unrelated public SystemVpn store row');
          }
          if (!fs.accessSync(marker)) {
            Journal.record('store-baseline', JSON.stringify(all.map((item: vpn.SysVpnConfig) => item.vpnId)));
            const f = fs.openSync(marker, fs.OpenMode.CREATE | fs.OpenMode.EXCL | fs.OpenMode.WRITE_ONLY);
            try { fs.writeSync(f.fd, Driver.ident()); } finally { fs.closeSync(f); }
          }
          await vpn.addSysVpnConfig(config);
          Journal.record('stored-profile', JSON.stringify({vpnId: config.vpnId, userId: config.userId,
            variant: action === 'option' ? option : action === 'failure-setup' ? 'bad-peer-name' : 'normal'}));
        }
        Journal.record('setup-entered', JSON.stringify({vpnId: config.vpnId, userId: config.userId}));
        const fd = await Driver.connection.setUp(config);
        Journal.record('setup-returned', JSON.stringify({fd, vpnId: Driver.ident(), option: action === 'option' ? option : ''}));
      } catch (error) { Journal.fail('setup-error', error as BusinessError, id, action); }
    } else if (action === 'state') { await Driver.state(id, action);
    } else if (action === 'destroy') {
      if (Driver.connection === undefined) { Driver.connection = vpn.createVpnConnection(context); }
      try { await Driver.connection.destroy(); Journal.record('destroy-returned'); }
      catch (error) { Journal.fail('destroy-error', error as BusinessError, id, action); }
    } else if (action === 'reconfigure') { await Driver.traffic(1, id, action, 'VPNR');
    } else if (action === 'restore-peer') { await Driver.traffic(1, id, action, 'VPNQ');
    } else if (action === 'traffic4' || action === 'traffic6') { await Driver.traffic(action === 'traffic4' ? 1 : 2, id, action);
    } else if (action === 'dns' || action === 'dns-outside' || action === 'dns-bad-cert') {
      const name = 'n' + RUN + '.' + id.replace(/_/g, '-') + (action === 'dns-outside' ? '.outside579.invalid' : '.whole579.invalid');
      Journal.record('dns-question', JSON.stringify(name));
      if (action === 'dns-bad-cert') {
        try { Journal.record('dns-answer', JSON.stringify(await connection.getAddressesByName(name))); }
        catch (error) { Journal.fail('dns-error', error as BusinessError, id, action); }
      } else { Journal.record('dns-answer', JSON.stringify(await connection.getAddressesByName(name))); }
    } else if (action === 'cleanup') {
      if (Driver.watch !== undefined) { vpn.off('connect', Driver.watch); }
      if (Driver.multi !== undefined) { vpn.off('connectMulti', Driver.multi); }
      Driver.watch = undefined; Driver.multi = undefined;
      if (Driver.connection !== undefined) { await Driver.connection.destroy(); }
      const marker = context.filesDir + '/network-whole579-store-' + RUN + '-' + ROLE;
      if (fs.accessSync(marker)) {
        if (fs.readTextSync(marker) !== Driver.ident()) { throw new Error('owned public store marker mismatch'); }
        const all = await vpn.getSysVpnConfigList();
        if (all.some((item: vpn.SysVpnConfig) => item.vpnId === Driver.ident())) { await vpn.deleteSysVpnConfig(Driver.ident()); }
        const remaining = await vpn.getSysVpnConfigList();
        if (remaining.some((item: vpn.SysVpnConfig) => item.vpnId === Driver.ident())) { throw new Error('owned config remains'); }
        Journal.record('store-cleanup', JSON.stringify(remaining.map((item: vpn.SysVpnConfig) => item.vpnId)));
        fs.unlinkSync(marker);
      }
      Journal.record('cleanup-returned');
    } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('fixed SystemVpn action required'); }
    Journal.record('done', 'null', 0, id, action);
  }
}
