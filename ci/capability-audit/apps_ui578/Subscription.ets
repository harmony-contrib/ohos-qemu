import NotificationSubscriberExtensionAbility from '@ohos.application.NotificationSubscriberExtensionAbility';
import subscription from '@ohos.notificationExtensionSubscription';
import { observe } from '../common/Observer';
// Real subscriber endpoint required by the public settings API. Actual received
// messages/cancellations remain raw observations; no synthetic callback success.
export default class Subscriber578 extends NotificationSubscriberExtensionAbility {
  onReceiveMessage(info: subscription.NotificationInfo): void { observe('subscription.message', JSON.stringify(info)); }
  onCancelMessages(hashes: Array<string>): void { observe('subscription.cancel', JSON.stringify(hashes)); }
  onDestroy(): void { observe('subscription.destroyed', 'null'); }
}
