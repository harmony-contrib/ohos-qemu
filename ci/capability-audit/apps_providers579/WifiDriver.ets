import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import wifi from '@ohos.wifiManager';
import process from '@ohos.process';
import policy from '@ohos.net.policy';
import statistics from '@ohos.net.statistics';
import http from '@ohos.net.http';
import { BusinessError } from '@ohos.base';
import connection from '@ohos.net.connection';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import fs from '@ohos.file.fs';
import { Journal, RUN } from './Journal';

interface Before { enabled: boolean; config: wifi.HotspotConfig; }

export class Driver {
  static stage?: window.WindowStage;
  static originalConfig?: wifi.HotspotConfig;
  static originalEnabled?: boolean;
  static network: number = -1;
  static async removeOwned(context: common.UIAbilityContext): Promise<void> {
    const path = context.filesDir + '/apps579-wifi-network-' + RUN + '.txt';
    if (fs.accessSync(path)) { Driver.network = Number(fs.readTextSync(path)); }
    if (Driver.network >= 0) {
      const owned = wifi.getDeviceConfigs().filter((config: wifi.WifiDeviceConfig) => config.networkId === Driver.network);
      if (owned.length > 1 || (owned.length === 1 && owned[0].ssid !== 'apps579_' + RUN.substring(0, 12))) {
        throw new Error('refuse unrelated saved WLAN configuration mutation');
      }
      if (owned.length === 1) { wifi.removeDevice(Driver.network); }
      let remaining = wifi.getDeviceConfigs().filter((config: wifi.WifiDeviceConfig) => config.networkId === Driver.network);
      for (let attempt: number = 0; remaining.length && attempt < 20; attempt++) {
        await new Promise<void>((resolve) => { setTimeout(resolve, 250); });
        remaining = wifi.getDeviceConfigs().filter((config: wifi.WifiDeviceConfig) => config.networkId === Driver.network);
      }
      Journal.record('owned-network-removed', JSON.stringify({networkId: Driver.network, remaining}));
      if (remaining.length) { throw new Error('native owned saved WLAN configuration still retained'); }
      Driver.network = -1;
      if (fs.accessSync(path)) { fs.unlinkSync(path); }
    }
  }
  static p2pPeer: string = '';
  static p2pGroups: wifi.WifiP2pGroupInfo[] = [];
  static p2pWatch: boolean = false;
  static p2pConnection?: (value: wifi.WifiP2pLinkedInfo) => void;
  static p2pPeers?: (value: wifi.WifiP2pDevice[]) => void;
  static p2pDiscovery?: (value: number) => void;
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    if (action === 'p2p-snapshot') {
      Driver.p2pGroups = await wifi.getP2pGroups();
      Journal.record('p2p-before', JSON.stringify({groups: Driver.p2pGroups, linked: await wifi.getP2pLinkedInfo()}));
    } else if (action === 'p2p-watch') {
      if (Driver.p2pWatch) { throw new Error('duplicate P2P watcher'); }
      Driver.p2pConnection = (value: wifi.WifiP2pLinkedInfo) => Journal.record('p2p-connection', JSON.stringify(value), 0, id, action);
      Driver.p2pPeers = (value: wifi.WifiP2pDevice[]) => Journal.record('p2p-peers', JSON.stringify(value), 0, id, action);
      Driver.p2pDiscovery = (value: number) => Journal.record('p2p-discovery', JSON.stringify(value), 0, id, action);
      wifi.on('p2pConnectionChange', Driver.p2pConnection);
      wifi.on('p2pPeerDeviceChange', Driver.p2pPeers);
      wifi.on('p2pDiscoveryChange', Driver.p2pDiscovery); Driver.p2pWatch = true;
      wifi.enableWifi();
      // Public WiFi enable is asynchronous. Every unsuccessful native read is
      // retained; only actual successful P2P reads make this request complete.
      for (let attempt: number = 0; attempt < 40; attempt++) {
        try {
          await wifi.getP2pLinkedInfo(); await wifi.getP2pGroups(); break;
        } catch (error) {
          Journal.fail('p2p-start-pending', error as BusinessError, id, action);
          if (attempt === 39) { throw error; }
          await new Promise<void>((resolve) => { setTimeout(resolve, 250); });
        }
      }
      Journal.record('p2p-watched');
    } else if (action === 'p2p-discover') {
      wifi.startDiscoverDevices(); Journal.record('p2p-discovery-requested');
    } else if (action === 'p2p-state') {
      const linked = await wifi.getP2pLinkedInfo();
      // Actual GetCurrentGroup rejects when disconnected. Omit the group in
      // that state instead of treating a disconnected state as an API failure.
      const group: wifi.WifiP2pGroupInfo | undefined = linked.connectState === wifi.P2pConnectState.CONNECTED ?
        await wifi.getCurrentGroup() : undefined;
      Journal.record('p2p-state', JSON.stringify({linked, peers: await wifi.getP2pPeerDevices(),
        local: await wifi.getP2pLocalDevice(), group, groups: await wifi.getP2pGroups()}));
    } else if (action === 'p2p-connect') {
      const peer = Journal.payload.peer_mac;
      if (typeof peer !== 'string' || !/^[0-9a-f]{2}(:[0-9a-f]{2}){5}$/.test(peer)) { throw new Error('actual independent P2P peer MAC required'); }
      const actual = await wifi.getP2pPeerDevices();
      if (!actual.some((item: wifi.WifiP2pDevice) => item.deviceAddress.toLowerCase() === peer)) { throw new Error('peer is absent from real public P2P discovery'); }
      Driver.p2pPeer = peer;
      wifi.p2pConnect({deviceAddress: peer, deviceAddressType: wifi.DeviceAddressType.REAL_DEVICE_ADDRESS, netId: -1, passphrase: '', groupName: '', goBand: wifi.GroupOwnerBand.GO_BAND_2GHZ});
      Journal.record('p2p-connect-requested', JSON.stringify(peer));
    } else if (action === 'p2p-remove') {
      wifi.removeGroup(); Journal.record('p2p-remove-requested');
    } else if (action === 'p2p-create') {
      wifi.createGroup({deviceAddress: '', netId: -1, passphrase: 'whole579_' + RUN.substring(0, 16),
        groupName: 'DIRECT-whole579_' + RUN.substring(0, 8), goBand: wifi.GroupOwnerBand.GO_BAND_2GHZ});
      Journal.record('p2p-create-requested');
    } else if (action === 'p2p-off') {
      wifi.stopDiscoverDevices(); wifi.p2pCancelConnect();
      if (Driver.p2pConnection !== undefined) { wifi.off('p2pConnectionChange', Driver.p2pConnection); }
      if (Driver.p2pPeers !== undefined) { wifi.off('p2pPeerDeviceChange', Driver.p2pPeers); }
      if (Driver.p2pDiscovery !== undefined) { wifi.off('p2pDiscoveryChange', Driver.p2pDiscovery); }
      Driver.p2pWatch = false;
      Journal.record('p2p-unwatched');
    } else if (action === 'p2p-restore') {
      wifi.stopDiscoverDevices(); wifi.p2pCancelConnect();
      if ((await wifi.getP2pLinkedInfo()).connectState === wifi.P2pConnectState.CONNECTED) { wifi.removeGroup(); }
      const after = await wifi.getP2pGroups();
      for (const item of after) {
        if (Driver.p2pGroups.some((old: wifi.WifiP2pGroupInfo) => old.networkId === item.networkId)) { continue; }
        if (item.groupName !== 'DIRECT-whole579_' + RUN.substring(0, 8) &&
          item.ownerInfo.deviceAddress.toLowerCase() !== Driver.p2pPeer) { throw new Error('refuse unrelated persistent group removal'); }
        if (item.networkId >= 0) { wifi.deletePersistentGroup(item.networkId); }
      }
      Journal.record('p2p-restored', JSON.stringify(await wifi.getP2pGroups()));
    } else if (action === 'identity') { await Journal.identity();
    } else if (action === 'permissions') {
      Journal.record('permission-result', JSON.stringify(await abilityAccessCtrl.createAtManager()
        .requestPermissionsFromUser(context, ['ohos.permission.LOCATION', 'ohos.permission.APPROXIMATELY_LOCATION'])));
    } else if (action === 'snapshot') {
      const path = context.filesDir + '/apps579-wifi-before-' + RUN + '.json';
      if (fs.accessSync(path)) {
        const before = JSON.parse(fs.readTextSync(path)) as Before;
        Driver.originalEnabled = before.enabled; Driver.originalConfig = before.config;
      } else {
        Driver.originalEnabled = wifi.isWifiActive(); Driver.originalConfig = wifi.getHotspotConfig();
        const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.EXCL);
        try { fs.writeSync(file.fd, JSON.stringify({enabled: Driver.originalEnabled, config: Driver.originalConfig})); }
        finally { fs.closeSync(file); }
      }
      Journal.record('wifi-before', JSON.stringify({enabled: Driver.originalEnabled,
        hotspot: wifi.isHotspotActive(), config: Driver.originalConfig,
        linked: Driver.originalEnabled ? await wifi.getLinkedInfo() : undefined}));
    } else if (action === 'sta-start') {
      wifi.on('wifiConnectionChange', (state: number) => Journal.record('wifi-connection', JSON.stringify(state), 0, id, action));
      wifi.enableWifi();
      Driver.network = await wifi.addDeviceConfig({ssid: 'apps579_' + RUN.substring(0, 12),
        preSharedKey: 'apps579_' + RUN.substring(0, 16), securityType: wifi.WifiSecurityType.WIFI_SEC_TYPE_PSK});
      const marker = fs.openSync(context.filesDir + '/apps579-wifi-network-' + RUN + '.txt',
        fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.EXCL);
      try { fs.writeSync(marker.fd, String(Driver.network)); } finally { fs.closeSync(marker); }
      wifi.connectToNetwork(Driver.network);
      Journal.record('sta-requested', JSON.stringify({networkId: Driver.network}));
    } else if (action === 'sta-state') {
      Journal.record('sta-linked', JSON.stringify(await wifi.getLinkedInfo()));
      Journal.record('sta-ip-info', JSON.stringify(wifi.getIpInfo()));
    } else if (action === 'networks') {
      const handles = await connection.getAllNets();
      for (const handle of handles) {
        const caps = await connection.getNetCapabilities(handle);
        if (caps.bearerTypes.indexOf(connection.NetBearType.BEARER_WIFI) >= 0) {
          Journal.record('actual-wifi-network', JSON.stringify({netId: handle.netId, capabilities: caps,
            properties: await connection.getConnectionProperties(handle)}));
        }
      }
    } else if (action === 'detect') {
      wifi.startWifiDetection(); Journal.record('actual-detection-requested');
    } else if (action === 'sta-stop') {
      wifi.disconnect();
      await Driver.removeOwned(context);
      wifi.off('wifiConnectionChange'); Journal.record('sta-stopped');
    } else if (action === 'ap-start') {
      wifi.on('hotspotStateChange', (state: number) => Journal.record('hotspot-state', JSON.stringify(state), 0, id, action));
      wifi.on('hotspotStaJoin', (station: wifi.StationInfo) => Journal.record('hotspot-join', JSON.stringify(station), 0, id, action));
      wifi.on('hotspotStaLeave', (station: wifi.StationInfo) => Journal.record('hotspot-leave', JSON.stringify(station), 0, id, action));
      wifi.setHotspotConfig({ssid: 'apps579_ap_' + RUN.substring(0, 12),
        securityType: wifi.WifiSecurityType.WIFI_SEC_TYPE_PSK, band: 1, channel: 1,
        preSharedKey: 'apps579_' + RUN.substring(0, 16), maxConn: 1});
      wifi.enableHotspot(); Journal.record('ap-requested');
    } else if (action === 'ap-state') {
      Journal.record('ap-state', JSON.stringify({active: wifi.isHotspotActive(), stations: wifi.getStations(), config: wifi.getHotspotConfig()}));
    } else if (action === 'ap-stop') {
      wifi.disableHotspot(); wifi.off('hotspotStateChange'); wifi.off('hotspotStaJoin'); wifi.off('hotspotStaLeave');
      Journal.record('ap-stopped');
    } else if (action === 'network579-state') {
      Journal.record('network579-state', JSON.stringify({connected: wifi.isConnected(),
        linked: await wifi.getLinkedInfo(), ip: wifi.getIpInfo(), configs: wifi.getDeviceConfigs()}), 0, id, action);
    } else if (action === 'network579-policy-read') {
      Journal.record('network579-policy', JSON.stringify(await policy.getNetworkAccessPolicy(process.uid)), 0, id, action);
    } else if (action === 'network579-policy-before') {
      const path: string = context.filesDir + '/network579-policy-' + RUN + '.json';
      if (fs.accessSync(path)) { throw new Error('refuse preexisting network policy baseline'); }
      const value: policy.NetworkAccessPolicy = await policy.getNetworkAccessPolicy(process.uid);
      const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.EXCL);
      try { fs.writeSync(file.fd, JSON.stringify(value)); } finally { fs.closeSync(file); }
      Journal.record('network579-policy-before', JSON.stringify(value), 0, id, action);
    } else if (action === 'network579-policy-deny' || action === 'network579-policy-allow') {
      const path: string = context.filesDir + '/network579-policy-' + RUN + '.json';
      const saved: policy.NetworkAccessPolicy = JSON.parse(fs.readTextSync(path)) as policy.NetworkAccessPolicy;
      const selected: policy.NetworkAccessPolicy = {allowWiFi: action === 'network579-policy-allow',
        allowCellular: saved.allowCellular, alwaysAllowWiFi: action === 'network579-policy-deny' ? false : saved.alwaysAllowWiFi,
        alwaysAllowCellular: saved.alwaysAllowCellular};
      await policy.setNetworkAccessPolicy(process.uid, selected, true);
      Journal.record('network579-policy-after', JSON.stringify(await policy.getNetworkAccessPolicy(process.uid)), 0, id, action);
    } else if (action === 'network579-policy-restore') {
      const path: string = context.filesDir + '/network579-policy-' + RUN + '.json';
      const saved: policy.NetworkAccessPolicy = JSON.parse(fs.readTextSync(path)) as policy.NetworkAccessPolicy;
      await policy.setNetworkAccessPolicy(process.uid, saved, true);
      Journal.record('network579-policy-restored', JSON.stringify(await policy.getNetworkAccessPolicy(process.uid)), 0, id, action);
    } else if (action === 'network579-traffic') {
      const client = http.createHttp();
      const beforeRx: number = await statistics.getUidRxBytes(process.uid);
      const beforeTx: number = await statistics.getUidTxBytes(process.uid);
      Journal.record('network579-traffic-before', JSON.stringify({rx: beforeRx, tx: beforeTx}), 0, id, action);
      const originalNet: connection.NetHandle = await connection.getAppNet();
      Journal.record('network579-network-before', JSON.stringify({netId: originalNet.netId}), 0, id, action);
      try {
        const handles: Array<connection.NetHandle> = await connection.getAllNets();
        const matching: Array<connection.NetHandle> = [];
        for (const handle of handles) {
          const capabilities: connection.NetCapabilities = await connection.getNetCapabilities(handle);
          if (capabilities.bearerTypes.indexOf(connection.NetBearType.BEARER_WIFI) >= 0) {
            const properties: connection.ConnectionProperties = await connection.getConnectionProperties(handle);
            if (properties.interfaceName === 'wlan0' && properties.linkAddresses.some((address: connection.LinkAddress) =>
              address.address.address === '192.0.2.2')) { matching.push(handle); }
          }
        }
        if (matching.length !== 1) { throw new Error('one actual owned WLAN handle required'); }
        await connection.setAppNet(matching[0]);
        Journal.record('network579-network-bound', JSON.stringify({netId: matching[0].netId,
          actual: (await connection.getAppNet()).netId,
          capabilities: await connection.getNetCapabilities(matching[0]),
          properties: await connection.getConnectionProperties(matching[0])}), 0, id, action);
        const headers: Record<string, string> = {'X-Network579-Request': id};
        const options: http.HttpRequestOptions = {method: http.RequestMethod.GET, header: headers,
          connectTimeout: 5000, readTimeout: 5000, usingCache: false, expectDataType: http.HttpDataType.STRING};
        try {
          const response: http.HttpResponse = await client.request('http://192.0.2.1/login/' + RUN, options);
          Journal.record('network579-http-response', JSON.stringify({status: response.responseCode,
            body: response.result, headers: response.header}), 0, id, action);
        } catch (error) {
          Journal.fail('network579-http-error', error as BusinessError, id, action);
        }
      } finally {
        client.destroy();
        await connection.setAppNet(originalNet);
        Journal.record('network579-network-restored', JSON.stringify({netId: (await connection.getAppNet()).netId}), 0, id, action);
      }
      const afterRx: number = await statistics.getUidRxBytes(process.uid);
      const afterTx: number = await statistics.getUidTxBytes(process.uid);
      Journal.record('network579-traffic-after', JSON.stringify({rx: afterRx, tx: afterTx}), 0, id, action);
    } else if (action === 'restore') {
      if (Driver.originalConfig === undefined || Driver.originalEnabled === undefined) {
        const before = JSON.parse(fs.readTextSync(context.filesDir + '/apps579-wifi-before-' + RUN + '.json')) as Before;
        Driver.originalEnabled = before.enabled; Driver.originalConfig = before.config;
      }
      if (Driver.originalConfig === undefined || Driver.originalEnabled === undefined) { throw new Error('actual WiFi before state missing'); }
      wifi.disconnect(); await Driver.removeOwned(context);
      wifi.disableHotspot();
      wifi.setHotspotConfig(Driver.originalConfig);
      if (Driver.originalEnabled) { wifi.enableWifi(); } else { wifi.disableWifi(); }
      Journal.record('wifi-restored', JSON.stringify({enabled: wifi.isWifiActive(), hotspot: wifi.isHotspotActive(), config: wifi.getHotspotConfig()}));
    } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('unknown fixed WLAN action'); }
    Journal.record('done', 'null', 0, id, action);
  }
}
