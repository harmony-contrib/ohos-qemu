import common from '@ohos.app.ability.common';
import config from '@ohos.accessibility.config';
import settings from '@ohos.settings';
import fs from '@ohos.file.fs';
import { RUN, ROLE } from './Journal';

interface SettingsState {
  ignoreRepeat: boolean;
  animationOff: boolean;
  ignoreNotification: string;
  animationNotification: string;
}

export class SettingsProgram {
  private context: common.UIAbilityContext;
  constructor(context: common.UIAbilityContext) { this.context = context; }
  private path(): string { return this.context.getApplicationContext().filesDir + '/apps578-settings-' + RUN + '.json'; }
  private flag(key: string): string {
    return settings.getValueSync(this.context, key, '__missing__', settings.domainName.USER_SECURITY);
  }
  private setFlag(key: string, value: string): void {
    if ((value !== '0' && value !== '1') ||
      !settings.setValueSync(this.context, key, value, settings.domainName.USER_SECURITY) || this.flag(key) !== value) {
      throw new Error('actual owned notification preference did not commit');
    }
  }
  private async state(): Promise<SettingsState> {
    return { ignoreRepeat: await config.ignoreRepeatClick.get(), animationOff: await config.animationOff.get(),
      ignoreNotification: this.flag('ignore_repeat_click_notification'),
      animationNotification: this.flag('transition_animations_notification') };
  }
  async run(action: string): Promise<string> {
    if (action === 'read') { return JSON.stringify(await this.state()); }
    if (action === 'invalid') { await config.ignoreRepeatClick.set(null as boolean); }
    else if (action === 'settings-save') {
      const baseline = await this.state();
      // There is no public delete-value API. Do not create an unremovable
      // preference when this actual fresh image has no initial row.
      if (baseline.ignoreRepeat || baseline.animationOff ||
        !['0','1'].includes(baseline.ignoreNotification) || !['0','1'].includes(baseline.animationNotification)) {
        throw new Error('fresh inactive configuration and restorable existing preference rows required');
      }
      const file = fs.openSync(this.path(), fs.OpenMode.CREATE | fs.OpenMode.EXCL | fs.OpenMode.WRITE_ONLY | fs.OpenMode.NOFOLLOW);
      try { fs.writeSync(file.fd, JSON.stringify(baseline)); } finally { fs.closeSync(file); }
      return JSON.stringify(baseline);
    } else if (action === 'ignore-enable' || action === 'animation-enable') {
      if (ROLE === 'normal' || ROLE === 'system-denied') {
        // A negative caller has no baseline file or private privilege. Reach
        // the real public permission check before any per-role file lookup.
        await config.ignoreRepeatClick.set(true);
        return JSON.stringify(await this.state());
      }
      // Capture the actual pre-state before mutating the real public config.
      fs.statSync(this.path());
      const ignore = action === 'ignore-enable';
      this.setFlag(ignore ? 'ignore_repeat_click_notification' : 'transition_animations_notification', '1');
      if (ignore) { await config.ignoreRepeatClick.set(false); await config.ignoreRepeatClick.set(true); }
      else { await config.animationOff.set(false); await config.animationOff.set(true); }
      return JSON.stringify(await this.state());
    } else if (action === 'settings-restore') {
      const baseline = JSON.parse(fs.readTextSync(this.path())) as SettingsState;
      if (baseline.ignoreRepeat || baseline.animationOff ||
        !['0','1'].includes(baseline.ignoreNotification) || !['0','1'].includes(baseline.animationNotification)) {
        throw new Error('refuse unrelated Settings baseline');
      }
      await config.ignoreRepeatClick.set(false);
      await config.animationOff.set(false);
      this.setFlag('ignore_repeat_click_notification', baseline.ignoreNotification);
      this.setFlag('transition_animations_notification', baseline.animationNotification);
      return JSON.stringify(await this.state());
    } else { throw new Error('fixed actual Settings action required'); }
    return 'null';
  }
}
