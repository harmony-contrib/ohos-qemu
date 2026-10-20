import osAccount from '@ohos.account.osAccount';
import fs from '@ohos.file.fs';
import common from '@ohos.app.ability.common';
import { Journal, RUN, ROLE } from './Journal';

// One real public-API program starts while u100 is foreground and continues
// across its own switch. Root only acknowledges captured real UI phases through
// this nonce-private file. It cannot supply account IDs or executable commands.
export class AccountProgram {
  private context: common.UIAbilityContext;
  constructor(context: common.UIAbilityContext) { this.context = context; }
  private async wait(phase: string): Promise<void> {
    Journal.record('account.wait.' + phase, 0, 'null', 'acct.program');
    const path: string = this.context.getApplicationContext().filesDir + '/account578-' + RUN + '-ack';
    for (let i: number = 0; i < 400; ++i) {
      try {
        if (fs.readTextSync(path) === RUN + ':' + phase) { return; }
      } catch (_) { /* An absent owner acknowledgement is not a successful phase. */ }
      await new Promise<void>((resolve) => { setTimeout(resolve, 100); });
    }
    throw new Error('actual account UI phase acknowledgement timed out: ' + phase);
  }
  private async read(operation: string): Promise<void> {
    const manager = osAccount.getAccountManager();
    Journal.record('call.account-read', 0, 'null', operation);
    Journal.record('return.account-read', 0, JSON.stringify({
      foreground: await manager.getForegroundOsAccountLocalId(), accounts: await manager.queryAllCreatedOsAccounts()
    }), operation);
  }
  private async activate(id: number, operation: string): Promise<void> {
    Journal.record('call.account-switch', 0, JSON.stringify(id), operation);
    await osAccount.getAccountManager().activateOsAccount(id);
    Journal.record('return.account-switch', 0, 'null', operation);
  }
  async run(): Promise<void> {
    if (ROLE !== 'account') { throw new Error('dedicated signed account operator required'); }
    const manager = osAccount.getAccountManager();
    const original = await manager.getForegroundOsAccountLocalId();
    const before = await manager.queryAllCreatedOsAccounts();
    if (original !== 100 || before.some((a: osAccount.OsAccountInfo) => a.localName === 'apps578-' + RUN)) {
      throw new Error('fresh u100 and unused nonce account required');
    }
    let owned: number = -1;
    try {
      await this.read('acct.before');
      Journal.record('call.account-create', 0, JSON.stringify('apps578-' + RUN), 'acct.create');
      const created = await manager.createOsAccount('apps578-' + RUN, osAccount.OsAccountType.NORMAL);
      owned = created.localId;
      Journal.record('return.account-create', 0, JSON.stringify({ original, id: owned, name: created.localName }), 'acct.create');
      await this.read('acct.created');
      await this.activate(owned, 'acct.baseline-away');
      await this.read('acct.baseline-read');
      await this.wait('baseline');
      await this.activate(original, 'acct.baseline-back');
      await this.wait('active');
      await this.activate(owned, 'acct.away');
      await this.read('acct.away-read');
      await this.wait('away');
      await this.activate(original, 'acct.back');
      await this.read('acct.back-read');
      await this.wait('return');
    } finally {
      // Cleanup still uses actual public APIs. Failure remains a failed stage,
      // and the original root finally also checks the exact nonce inventory.
      if (await manager.getForegroundOsAccountLocalId() !== original) {
        await this.activate(original, 'acct.finally-back');
      }
      const current = await manager.queryAllCreatedOsAccounts();
      const matches = current.filter((a: osAccount.OsAccountInfo) => a.localName === 'apps578-' + RUN);
      if (matches.length > 1 || (matches.length === 1 && (matches[0].localId !== owned || owned <= 100))) {
        throw new Error('nonce account identity changed; unrelated accounts are preserved');
      }
      if (matches.length === 1) {
        Journal.record('call.account-remove', 0, JSON.stringify(owned), 'acct.remove');
        await manager.removeOsAccount(owned);
        Journal.record('return.account-remove', 0, 'null', 'acct.remove');
      }
      await this.read('acct.after');
    }
  }
}
