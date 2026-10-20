import EnterpriseAdminExtensionAbility from '@ohos.enterprise.EnterpriseAdminExtensionAbility';
import { observe } from '../common/Observer';
export default class Admin578 extends EnterpriseAdminExtensionAbility {
  onAdminEnabled(): void { observe('admin.enabled.callback', 'null'); }
  onAdminDisabled(): void { observe('admin.disabled.callback', 'null'); }
}
