import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import wifi from '@ohos.wifiManager';
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
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    if (action === 'identity') { await Journal.identity();
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
