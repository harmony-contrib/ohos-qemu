import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import appDomainVerify from '@ohos.bundle.appDomainVerify';
import { BusinessError } from '@ohos.base';
import { Journal, HOST, OTHER_HOST, RUN, TARGET, OTHER } from './Journal';

export class Driver {
  static stage?: window.WindowStage;
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'probe') {
      Journal.record('syscap', 0, JSON.stringify(canIUse('SystemCapability.BundleManager.AppDomainVerify')));
    } else if (action === 'query') {
      const domains = appDomainVerify.queryAssociatedDomains(TARGET);
      const bundles = appDomainVerify.queryAssociatedBundleNames('https://' + HOST);
      const otherDomains = appDomainVerify.queryAssociatedDomains(OTHER);
      const otherBundles = appDomainVerify.queryAssociatedBundleNames('https://' + OTHER_HOST);
      Journal.record('query', 0, JSON.stringify({domains, bundles, otherDomains, otherBundles}));
    } else if (action === 'query-invalid') {
      // Empty input is rejected before any privileged state can be returned.
      const result = appDomainVerify.queryAssociatedDomains('');
      Journal.record('query-invalid-returned', 0, JSON.stringify(result));
    } else if (action === 'open' || action === 'open-http' || action === 'open-other') {
      const host = action === 'open-other' ? OTHER_HOST : HOST;
      const scheme = action === 'open-http' ? 'http' : 'https';
      const uri = scheme + '://' + host + '/services578/' + RUN + '/' + id;
      Journal.record('open-request', 0, JSON.stringify({uri, appLinkingOnly: true}));
      try {
        await context.openLink(uri, {appLinkingOnly: true});
        Journal.record('open-result', 0, JSON.stringify(uri), id, action);
      } catch (error) { Journal.fail('open-result', error as BusinessError, id, action); }
    } else if (action === 'exit') {
      Journal.record('exit-request');
      await context.terminateSelf();
    } else { throw new Error('unknown domain action'); }
    Journal.record('done', 0, 'null', id, action);
  }
}
