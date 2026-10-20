import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import location from '@ohos.geoLocationManager';
import fs from '@ohos.file.fs';
import { Journal, RUN } from './Journal';

interface State { enabled: boolean; confirmed: boolean; }
export class Driver {
  static stage?: window.WindowStage;
  static original?: State;
  static snapshot(): State {
    return {enabled: location.isLocationEnabled(), confirmed:
      location.isLocationPrivacyConfirmed(location.LocationPrivacyType.STARTUP)};
  }
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'snapshot') { Journal.record('location-state', JSON.stringify(Driver.snapshot()));
    } else if (action === 'reset-own-fixture') {
      const path = context.filesDir + '/apps579-location-before-' + RUN + '.json';
      if (!Driver.original) {
        if (fs.accessSync(path)) { Driver.original = JSON.parse(fs.readTextSync(path)) as State; }
        else {
          Driver.original = Driver.snapshot();
          const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.EXCL);
          try { fs.writeSync(file.fd, JSON.stringify(Driver.original)); } finally { fs.closeSync(file); }
        }
      }
      await location.disableLocation();
      location.setLocationPrivacyConfirmStatus(location.LocationPrivacyType.STARTUP, false);
      Journal.record('fixture-state', JSON.stringify({before: Driver.original, after: Driver.snapshot()}));
    } else if (action === 'enable') {
      // Native EnableAbility opens the real LocationPrivacyExtAbility when
      // STARTUP is false, and returns 3301000 while waiting for that UI.
      await location.enableLocation();
      Journal.record('enable-returned', JSON.stringify(Driver.snapshot()));
    } else if (action === 'restore') {
      if (!Driver.original) {
        Driver.original = JSON.parse(fs.readTextSync(context.filesDir + '/apps579-location-before-' + RUN + '.json')) as State;
      }
      if (!Driver.original) { throw new Error('actual original location state missing'); }
      location.setLocationPrivacyConfirmStatus(location.LocationPrivacyType.STARTUP, Driver.original.confirmed);
      if (Driver.original.enabled) { await location.enableLocation(); } else { await location.disableLocation(); }
      Journal.record('restored-state', JSON.stringify(Driver.snapshot()));
    } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('unknown fixed location action'); }
    Journal.record('done', 'null', 0, id, action);
  }
}
