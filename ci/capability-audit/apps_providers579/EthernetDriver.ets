import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import ethernet from '@ohos.net.ethernet';
import fs from '@ohos.file.fs';
import { BusinessError } from '@ohos.base';
import { Journal, RUN } from './Journal';

export class Driver {
  static stage?: window.WindowStage;
  static snapshot(name: string, id: string, action: string): boolean {
    const enabled = ethernet.isEthernetEnabled();
    const raw = fs.readTextSync('/sys/class/net/eth0/flags').trim();
    if (!/^0x[0-9a-fA-F]+$/.test(raw)) { throw new Error('actual eth0 kernel flags missing'); }
    Journal.record(name, JSON.stringify({enabled, flags: parseInt(raw.substring(2), 16), raw}), 0, id, action);
    return enabled;
  }
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    const id = Journal.requestId;
    const path = context.filesDir + '/apps579-ethernet-before-' + RUN + '.txt';
    if (action === 'identity') { await Journal.identity();
    } else if (action === 'snapshot') {
      const before = Driver.snapshot('ethernet-before', id, action);
      if (!fs.accessSync(path)) {
        const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.EXCL | fs.OpenMode.WRITE_ONLY);
        try { fs.writeSync(file.fd, before ? 'true' : 'false'); } finally { fs.closeSync(file); }
      }
    } else if (action === 'cycle') {
      const before = fs.readTextSync(path);
      if (before !== 'true') { throw new Error('refuse mutation of disabled/foreign Ethernet baseline'); }
      // Let the actual aa-start transport finish before a brief, real public
      // interface transition. Recovery lives inside this same guest caller.
      await new Promise<void>((resolve) => setTimeout(resolve, 1000));
      try {
        for (let round: number = 0; round < 2; round++) {
          await ethernet.disableEthernetInterface(); Driver.snapshot('ethernet-disabled', id, action);
          await ethernet.disableEthernetInterface(); Driver.snapshot('ethernet-disabled-again', id, action);
          await ethernet.enableEthernetInterface(); Driver.snapshot('ethernet-enabled', id, action);
          await ethernet.enableEthernetInterface(); Driver.snapshot('ethernet-enabled-again', id, action);
        }
      } finally { await ethernet.enableEthernetInterface(); Driver.snapshot('ethernet-restored', id, action); }
    } else if (action === 'boundaries') {
      for (const method of ['disableEthernetInterface', 'enableEthernetInterface', 'isEthernetEnabled']) {
        try {
          if (method === 'disableEthernetInterface') { await ethernet.disableEthernetInterface(); }
          else if (method === 'enableEthernetInterface') { await ethernet.enableEthernetInterface(); }
          else { ethernet.isEthernetEnabled(); }
          Journal.record('ethernet-unexpected-return', JSON.stringify(method), 0, id, action);
        } catch (error) {
          Journal.record('ethernet-denied-method', JSON.stringify(method), 0, id, action);
          Journal.fail('ethernet-denied', error as BusinessError, id, action);
        }
      }
    } else if (action === 'restore') {
      const before = fs.readTextSync(path);
      if (before === 'true') { await ethernet.enableEthernetInterface(); }
      else if (before === 'false') { await ethernet.disableEthernetInterface(); }
      else { throw new Error('actual saved Ethernet baseline missing'); }
      Driver.snapshot('ethernet-restored', id, action);
    } else if (action === 'exit') { Journal.record('exit-request'); await context.terminateSelf();
    } else { throw new Error('unknown fixed Ethernet action'); }
    Journal.record('done', 'null', 0, id, action);
  }
}
