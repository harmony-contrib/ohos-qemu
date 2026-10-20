import VpnExtensionAbility from '@ohos.app.ability.VpnExtensionAbility';
import Want from '@ohos.app.ability.Want';
import { Journal } from './Journal';

// This consumer exists only to give policy APIs an actual installed VPN
// extension identity. No TUN/provider/transport behavior is claimed here.
export default class PolicyVpnExtension extends VpnExtensionAbility {
  onCreate(want: Want): void { Journal.record('policy-extension-create', JSON.stringify(want)); }
  onDestroy(): void { Journal.record('policy-extension-destroy'); }
}
