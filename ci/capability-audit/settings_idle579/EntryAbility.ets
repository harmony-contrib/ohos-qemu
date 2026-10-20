import { UIAbility, Want, AbilityConstant } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';
import window from '@ohos.window';
import { Journal, BUNDLE, SERVICE } from '../audit/Journal';

import { nativeFixture } from '../audit/NativeFixture';

export default class EntryAbility extends UIAbility {
  onWindowStageCreate(stage: window.WindowStage): void { void stage.loadContent('pages/Index'); }
  onCreate(want: Want, launchParam: AbilityConstant.LaunchParam): void { void this.dispatch(want); }
  onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): void { void this.dispatch(want); }
  private async dispatch(want: Want): Promise<void> {
    const request = Journal.request(want);
    const actions: string[] = ['remember', 'stale', 'future', 'parameters', 'current',
      'retain-context', 'old-context-attempt', 'heartbeat', 'native-ui', 'native-malformed', 'native-foreign'];
    if (!actions.includes(request.action)) { throw new Error('finite real service challenge required'); }
    if (request.action.startsWith('native-')) {
      try { await nativeFixture(this.context, request); }
      catch (error) {
        const e = error as BusinessError;
        Journal.write(this.context, request, 'native.error', typeof e.code === 'number' ? e.code : -1,
          JSON.stringify({ message: e.message }));
      }
      return;
    }
    Journal.write(this.context, request, 'driver.start.call', 0, JSON.stringify(request));
    try {
      const service: Want = { bundleName: BUNDLE, moduleName: 'entry', abilityName: SERVICE,
        parameters: { run: request.run, boot: request.boot, operation: request.operation, action: request.action } };
      await this.context.startServiceExtensionAbility(service);
      Journal.write(this.context, request, 'driver.start.return', 0, 'null');
    } catch (error) {
      const e = error as BusinessError;
      Journal.write(this.context, request, 'driver.start.error', typeof e.code === 'number' ? e.code : -1,
        JSON.stringify({ message: e.message }));
    }
  }
}
