import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import osAccount from '@ohos.account.osAccount';
import fs from '@ohos.file.fs';
import { Journal, RUN } from './Journal';

interface OwnedAccount { localId: number; localName: string; original: number; }
export class Driver {
  static stage?: window.WindowStage;
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    const manager = osAccount.getAccountManager();
    const marker = context.filesDir + '/network-whole579-account-' + RUN + '.json';
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'accounts') {
      Journal.record('accounts', JSON.stringify(await manager.queryAllCreatedOsAccounts()));
      Journal.record('foreground-account', JSON.stringify(await manager.getForegroundOsAccountLocalId()));
      Journal.record('self-account', JSON.stringify(await manager.getOsAccountLocalId()));
    } else if (action === 'account-create') {
      const before = await manager.queryAllCreatedOsAccounts();
      if (before.some((item: osAccount.OsAccountInfo) => item.localName === 'whole579_' + RUN) || fs.accessSync(marker)) {
        throw new Error('refuse pre-existing account or owned marker');
      }
      const original = await manager.getForegroundOsAccountLocalId();
      if (original !== 100) { throw new Error('original account100 must be foreground'); }
      Journal.record('accounts-before', JSON.stringify(before));
      const created = await manager.createOsAccount('whole579_' + RUN, osAccount.OsAccountType.GUEST);
      const owned: OwnedAccount = {localId: created.localId, localName: created.localName, original};
      const file = fs.openSync(marker, fs.OpenMode.CREATE | fs.OpenMode.EXCL | fs.OpenMode.WRITE_ONLY);
      try { fs.writeSync(file.fd, JSON.stringify(owned)); } finally { fs.closeSync(file); }
      Journal.record('account-created', JSON.stringify(created));
    } else if (action === 'account-activate' || action === 'account-restore' || action === 'account-remove') {
      const owned = JSON.parse(fs.readTextSync(marker)) as OwnedAccount;
      const all = await manager.queryAllCreatedOsAccounts();
      const same = all.filter((item: osAccount.OsAccountInfo) => item.localId === owned.localId && item.localName === owned.localName);
      if (owned.original !== 100 || owned.localName !== 'whole579_' + RUN || same.length !== 1) { throw new Error('actual owned account identity lost'); }
      if (action === 'account-activate') { await manager.activateOsAccount(owned.localId); }
      else if (action === 'account-restore') { await manager.activateOsAccount(owned.original); }
      else {
        if (await manager.getForegroundOsAccountLocalId() !== 100) { throw new Error('restore foreground before deleting owned guest account'); }
        if (await manager.isOsAccountActived(owned.localId)) { await manager.deactivateOsAccount(owned.localId); }
        await manager.removeOsAccount(owned.localId); fs.unlinkSync(marker);
      }
      Journal.record(action, JSON.stringify({owned, accounts: await manager.queryAllCreatedOsAccounts(),
        foreground: await manager.getForegroundOsAccountLocalId()}));
    } else { throw new Error('fixed public account action required'); }
    Journal.record('done', 'null', 0, id, action);
  }
}
