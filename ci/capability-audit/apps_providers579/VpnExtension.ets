import VpnExtensionAbility from '@ohos.app.ability.VpnExtensionAbility';
import Want from '@ohos.app.ability.Want';
import vpn from '@ohos.net.vpnExtension';
import fs from '@ohos.file.fs';
import { BusinessError } from '@ohos.base';
import { Journal } from './Journal';

// A real ordinary test VPN consumer, not a replacement authorization provider.
// The strict original Network peer family independently validates TLS/data.
export default class OwnedVpnExtension extends VpnExtensionAbility {
  private connection?: vpn.VpnConnection;
  private fd: number = -1;
  onCreate(want: Want): void {
    Journal.request(want);
    Journal.record('vpn-extension-create', JSON.stringify(want));
    this.create().catch((error: BusinessError) => Journal.fail('vpn-extension-error', error));
  }
  private async create(): Promise<void> {
    this.connection = vpn.createVpnConnection(this.context);
    const id = await this.connection.generateVpnId();
    this.fd = await this.connection.create({vpnId: id,
      addresses: [{address: {address: '198.18.79.2', family: 1}, prefixLength: 24}],
      mtu: 1400, isIPv4Accepted: true, isIPv6Accepted: false, isInternal: false, isBlocking: false});
    Journal.record('vpn-tun-created', JSON.stringify({vpnId: id, fd: this.fd, stat: fs.statSync(this.fd)}));
  }
  onRequest(want: Want, startId: number): void { Journal.record('vpn-extension-request', JSON.stringify({want, startId})); }
  onDestroy(): void {
    Journal.record('vpn-extension-destroy');
    if (this.connection) {
      this.connection.destroy().then(() => {
        Journal.record('vpn-tun-destroyed');
      }).catch((error: BusinessError) => Journal.fail('vpn-destroy-error', error));
    }
  }
}
