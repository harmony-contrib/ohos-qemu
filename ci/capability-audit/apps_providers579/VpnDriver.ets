import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import vpn from '@ohos.net.vpnExtension';
import { Journal, BUNDLE } from './Journal';

export class Driver {
  static stage?: window.WindowStage;
  static observer?: vpn.VpnObserver;
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'authorize') {
      Driver.observer = vpn.createVpnObserver();
      Driver.observer.onAuthorizationResult((allowed: boolean) =>
        Journal.record('vpn-authorization', JSON.stringify(allowed), 0, id, action));
      Journal.record('vpn-start-request');
      await vpn.startVpnExtensionAbility({bundleName: BUNDLE, abilityName: 'OwnedVpnExtension',
        parameters: {run_id: '__APPS579_RUN__', request_id: id, action, payload: '{}'}});
      Journal.record('vpn-start-returned');
    } else if (action === 'stop-vpn') {
      await vpn.stopVpnExtensionAbility({bundleName: BUNDLE, abilityName: 'OwnedVpnExtension'});
      Journal.record('vpn-stop-returned');
      if (Driver.observer) { Driver.observer.offAuthorizationResult(); Driver.observer = undefined; }
    } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('unknown fixed VPN action'); }
    Journal.record('done', 'null', 0, id, action);
  }
}
