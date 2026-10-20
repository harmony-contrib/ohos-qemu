import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import { Journal } from './Journal';

export class Driver {
  static stage?: window.WindowStage;
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'declarations') {
      Journal.record('exact-labels', JSON.stringify({
        'SystemCapability.FileManagement.File.DistributedFile': canIUse('SystemCapability.FileManagement.File.DistributedFile'),
        'SystemCapability.HiviewDFX.HiDumper': canIUse('SystemCapability.HiviewDFX.HiDumper'),
        'SystemCapability.Security.DataTransitManager': canIUse('SystemCapability.Security.DataTransitManager'),
        'SystemCapability.Security.DeviceAuth': canIUse('SystemCapability.Security.DeviceAuth'),
        'SystemCapability.Security.DeviceSecurityLevel': canIUse('SystemCapability.Security.DeviceSecurityLevel'),
        'SystemCapability.UserIAM.UserAuth.PinAuth': canIUse('SystemCapability.UserIAM.UserAuth.PinAuth')}));
      // Exact retired labels only. Owning service/API behavior is not inferred
      // from this declaration observation and is separately consumed raw.
    } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('unknown fixed historical-label action'); }
    Journal.record('done', 'null', 0, id, action);
  }
}
