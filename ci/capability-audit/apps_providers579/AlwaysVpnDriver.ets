import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import vpn from '@ohos.net.vpnExtension';
import fs from '@ohos.file.fs';
import { BusinessError } from '@ohos.base';
import { Journal, BUNDLE, RUN } from './Journal';

export class Driver {
  static stage?: window.WindowStage;
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    const path = context.filesDir + '/apps579-always-before-' + RUN + '.txt';
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'boundaries') {
      for (const method of ['isAlwaysOnVpnEnabled', 'setAlwaysOnVpnEnabled']) {
        for (const name of [BUNDLE]) {
          try {
            if (method === 'isAlwaysOnVpnEnabled') { await vpn.isAlwaysOnVpnEnabled(name); }
            else { await vpn.setAlwaysOnVpnEnabled(false, name); }
            Journal.record('policy-boundary-returned', JSON.stringify({method, name}), 0, id, action);
          } catch (error) {
            Journal.record('policy-boundary-method', JSON.stringify({method, name}), 0, id, action);
            Journal.fail('policy-boundary-error', error as BusinessError, id, action);
          }
        }
      }
    } else if (action === 'seed') {
      const before = await vpn.isAlwaysOnVpnEnabled(BUNDLE);
      Journal.record('policy-before', JSON.stringify(before));
      if (before || fs.accessSync(path)) { throw new Error('unexpected owned policy baseline'); }
      const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.EXCL | fs.OpenMode.WRITE_ONLY);
      try { fs.writeSync(file.fd, 'false'); } finally { fs.closeSync(file); }
      for (let round: number = 0; round < 2; round++) {
        await vpn.setAlwaysOnVpnEnabled(true, BUNDLE);
        Journal.record('policy-enabled', JSON.stringify({round, value: await vpn.isAlwaysOnVpnEnabled(BUNDLE)}));
        await vpn.setAlwaysOnVpnEnabled(false, BUNDLE);
        Journal.record('policy-disabled', JSON.stringify({round, value: await vpn.isAlwaysOnVpnEnabled(BUNDLE)}));
      }
      await vpn.setAlwaysOnVpnEnabled(true, BUNDLE);
      Journal.record('policy-seeded', JSON.stringify(await vpn.isAlwaysOnVpnEnabled(BUNDLE)));
    } else if (action === 'verify-persisted') {
      Journal.record('policy-persisted', JSON.stringify(await vpn.isAlwaysOnVpnEnabled(BUNDLE)));
    } else if (action === 'cleanup') {
      if (!fs.accessSync(path)) {
        if (await vpn.isAlwaysOnVpnEnabled(BUNDLE)) { throw new Error('unowned policy enabled; retain for repair'); }
      } else if (fs.readTextSync(path) !== 'false') { throw new Error('actual owned baseline missing'); }
      await vpn.setAlwaysOnVpnEnabled(false, BUNDLE);
      Journal.record('policy-restored', JSON.stringify(await vpn.isAlwaysOnVpnEnabled(BUNDLE)));
    } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('unknown fixed VPN policy action'); }
    Journal.record('done', 'null', 0, id, action);
  }
}
