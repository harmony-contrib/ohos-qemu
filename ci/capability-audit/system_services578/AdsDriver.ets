import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import advertising from '@ohos.advertising';
import { BusinessError } from '@ohos.base';
import { Journal, RUN } from './Journal';

export class Driver {
  static stage?: window.WindowStage;
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'probe') {
      Journal.record('syscap', 0, JSON.stringify(canIUse('SystemCapability.Advertising.Ads')));
    } else if (action === 'invalid') {
      // Intentional runtime-null boundary. The assertion affects only the
      // compiler; processParamsNull must reject the actual JS null with 401.
      const loader = new advertising.AdLoader(context);
      loader.loadAd(null!, {nonPersonalizedAd: 1}, {
        onAdLoadFailure: (code: number, message: string) =>
          Journal.record('ad-failure', code, JSON.stringify({message}), id, action),
        onAdLoadSuccess: (ads: Array<advertising.Advertisement>) =>
          Journal.record('ad-success', 0, JSON.stringify(ads), id, action)});
      Journal.record('load-returned');
    } else if (action === 'load' || action === 'multi') {
      const loader = new advertising.AdLoader(context);
      const params: advertising.AdRequestParams = {adId: 'qemu578_' + RUN, adType: 3, adCount: 1};
      const options: advertising.AdOptions = {nonPersonalizedAd: 1};
      if (action === 'load') {
        loader.loadAd(params, options, {
          onAdLoadFailure: (code: number, message: string) =>
            Journal.record('ad-failure', code, JSON.stringify({message}), id, action),
          onAdLoadSuccess: (ads: Array<advertising.Advertisement>) =>
            Journal.record('ad-success', 0, JSON.stringify(ads), id, action)});
      } else {
        loader.loadAdWithMultiSlots([params], options, {
          onAdLoadFailure: (code: number, message: string) =>
            Journal.record('ad-failure', code, JSON.stringify({message}), id, action),
          onAdLoadSuccess: (ads: Map<string, Array<advertising.Advertisement>>) =>
            Journal.record('ad-success', 0, JSON.stringify(Array.from(ads.entries())), id, action)});
      }
      Journal.record('load-returned');
    } else if (action === 'invalid-display') {
      // The null is deliberate malformed input, never a creative/provider.
      advertising.showAd(null!, {mute: true}, context);
      Journal.record('invalid-display-returned');
    } else if (action === 'exit') {
      Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('unknown advertising action'); }
    Journal.record('done', 0, 'null', id, action);
  }
}
