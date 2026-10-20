import vpn from '@ohos.net.vpn';
import { RUN } from './Journal';

// Exact rich native-store fixtures reused from the original strict VPN store
// family. These synthetic configuration values never represent a real tunnel.
export class Fixture {
  static readonly types: vpn.SysVpnType[] = [vpn.SysVpnType.OPENVPN,
    vpn.SysVpnType.IKEV2_IPSEC_PSK, vpn.SysVpnType.L2TP_IPSEC_PSK];
  static ownedVpnId(index: number): string {
    const hex = RUN.substring(0, 31) + index.toString();
    return hex.substring(0, 8) + '-' + hex.substring(8, 12) + '-' + hex.substring(12, 16) + '-' +
      hex.substring(16, 20) + '-' + hex.substring(20);
  }
  static config(index: number, revision: number): vpn.SysVpnConfig {
    const config: vpn.SysVpnConfig = {
      vpnId: Fixture.ownedVpnId(index), vpnName: 'audit-' + RUN + '-' + revision,
      vpnType: Fixture.types[index], userName: 'audit-' + RUN, password: 'synthetic-' + RUN,
      saveLogin: true, forwardingRoutes: '198.18.0.0/24',
      addresses: [{ address: { address: '198.18.0.2', family: 1, port: revision === 0 ? 8080 : 65535 }, prefixLength: 24 },
        { address: { address: '2001:db8::2', family: 2, port: revision === 0 ? 65535 : 256 }, prefixLength: 64 }],
      localAddresses: [{ address: { address: '198.18.0.6', family: 1, port: revision === 0 ? 256 : 8080 }, prefixLength: 28 },
        { address: { address: '2001:db8::6', family: 2, port: revision === 0 ? 255 : 0 }, prefixLength: 96 }],
      remoteAddresses: ['198.19.0.1', '2001:db8:1::1'],
      dnsAddresses: ['198.18.0.53', '2001:db8::53'],
      searchDomains: ['a.' + RUN + '.invalid', 'b.' + RUN + '.invalid'],
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
      open.ovpnConfig = 'audit-config-' + RUN; open.askpass = 'synthetic-askpass-' + RUN;
    } else if (index === 1) {
      const ipsec = config as vpn.IpsecVpnConfig;
      ipsec.ipsecPreSharedKey = 'synthetic-psk-' + RUN; ipsec.ipsecIdentifier = 'audit-identifier';
    } else {
      const l2tp = config as vpn.L2tpVpnConfig;
      l2tp.ipsecPreSharedKey = 'synthetic-psk-' + RUN; l2tp.ipsecIdentifier = 'audit-identifier';
      l2tp.l2tpSharedKey = 'synthetic-l2tp-' + RUN;
    }
    return config;
  }
}
