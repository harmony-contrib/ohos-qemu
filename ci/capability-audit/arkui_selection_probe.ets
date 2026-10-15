// Real SelectionContainer modifiers, native menu copy/veto and controller cleanup.
import { SelectionContainer, SelectionContainerAttribute, SelectionContainerController,
  SelectionContainerTextJoinStyle } from '@ohos.arkui.components.SelectionContainer';
import pasteboard from '@ohos.pasteboard';
import fs from '@ohos.file.fs';
import process from '@ohos.process';
import abilityAccessCtrl, { PermissionRequestResult } from '@ohos.abilityAccessCtrl';
import common from '@ohos.app.ability.common';
import { BusinessError } from '@ohos.base';

interface Observation { runId: string; cycle: number; phase: number; name: string; values: number[]; data: string; }
interface ClipboardInfo { text: string; html: string; mimeTypes: string[]; records: number;
  textPresent: boolean; htmlPresent: boolean; mimeTypesPresent: boolean; }
class Journal {
  static cycle: number = 0;
  static phase: number = 0;
  static record(name: string, values: number[] = [], data: string = ''): void {
    const row: Observation = { runId: '__RUN__', cycle: Journal.cycle, phase: Journal.phase, name, values, data };
    const file = fs.openSync('/data/storage/el2/base/files/arkui-selection-__RUN__-results.log',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
  }
}
const CALLER_ROLE: string = '__ROLE__';
function clipboardInfo(data: pasteboard.PasteData): ClipboardInfo {
  const text = data.getPrimaryText(); const html = data.getPrimaryHtml(); const mime = data.getMimeTypes();
  return { text: typeof text === 'string' ? text : '', html: typeof html === 'string' ? html : '',
    mimeTypes: Array.isArray(mime) ? mime : [], records: data.getRecordCount(),
    textPresent: typeof text === 'string', htmlPresent: typeof html === 'string', mimeTypesPresent: Array.isArray(mime) };
}
class SelectionModifier implements AttributeModifier<SelectionContainerAttribute> {
  applyNormalAttribute(instance: SelectionContainerAttribute): void {
    try {
      const reset = instance.copyOption(undefined).caretColor(undefined).selectedBackgroundColor(undefined)
        .enableHapticFeedback(undefined).textJoinStyle(undefined).onWillCopy(undefined).onCopy(undefined) === instance;
      const chained = instance.width(360).height(160).copyOption(CopyOptions.LocalDevice).caretColor('#cc1122')
        .selectedBackgroundColor('#ffee22').enableHapticFeedback(false)
        .textJoinStyle(SelectionContainerTextJoinStyle.NEWLINE) === instance;
      Journal.record('modifier.selection', [reset ? 1 : 0, chained ? 1 : 0]);
    } catch (error) { Journal.record('failed', [], String(error)); }
  }
}
@Entry
@ComponentV2
struct Index {
  @Local active: boolean = false;
  @Local allowCopy: boolean = false;
  @Local directJoin: boolean = false;
  @Local displayState: string = 'idle __RUN__';
  private cycle: number = -1;
  private creating: boolean = false;
  private controller: SelectionContainerController | undefined = undefined;
  private readonly modifier: SelectionModifier = new SelectionModifier();
  private copied(text: string): void {
    Journal.record('copied', [1], text);
    pasteboard.getSystemPasteboard().getData().then((data: pasteboard.PasteData) => {
      Journal.record('pasteboard.read', [1], JSON.stringify(clipboardInfo(data)));
    }).catch((error: BusinessError) => { Journal.record('pasteboard.read.reject', [error.code], error.message); });
  }
  private async readClipboard(): Promise<void> {
    try {
      const data = await pasteboard.getSystemPasteboard().getData();
      Journal.record('pasteboard.deferred.read', [1], JSON.stringify(clipboardInfo(data)));
    } catch (error) {
      const business = error as BusinessError;
      Journal.record('pasteboard.deferred.reject', [business.code], business.message);
    }
    try {
      const data = pasteboard.getSystemPasteboard().getDataSync();
      Journal.record('pasteboard.sync.read', [1], JSON.stringify(clipboardInfo(data)));
    } catch (error) {
      const business = error as BusinessError;
      Journal.record('pasteboard.sync.reject', [business.code], business.message);
    }
    pasteboard.getSystemPasteboard().getData((error: BusinessError, data: pasteboard.PasteData) => {
      if (error) {
        Journal.record('pasteboard.callback.reject', [error.code], error.message);
      } else {
        Journal.record('pasteboard.callback.read', [1], JSON.stringify(clipboardInfo(data)));
      }
    });
  }
  private async createSelection(): Promise<void> {
    try {
      if (this.active || this.creating || this.cycle >= 1) { throw new Error('only two separate selection creation cycles allowed'); }
      this.creating = true;
      this.cycle += 1; Journal.cycle = this.cycle; Journal.phase = 0;
      this.allowCopy = false; this.directJoin = false;
      Journal.record('identity', [process.uid, process.euid, process.pid]);
      Journal.record('permission.state', [abilityAccessCtrl.createAtManager()
        .getSelfPermissionStatus('ohos.permission.READ_PASTEBOARD')]);
      if (CALLER_ROLE === 'reader') {
        await pasteboard.getSystemPasteboard().setData(pasteboard.createData(pasteboard.MIMETYPE_TEXT_PLAIN,
          '__RUN__ seed:' + this.cycle));
        const data = await pasteboard.getSystemPasteboard().getData();
        Journal.record('seed.completed', [1], JSON.stringify(clipboardInfo(data)));
      }
      this.controller = new SelectionContainerController(); this.active = true;
      this.displayState = 'active __RUN__:' + this.cycle; Journal.record('create.request', [1]);
    } catch (error) { Journal.record('failed', [], String(error)); }
    finally { this.creating = false; }
  }
  private async grantRead(): Promise<void> {
    try {
      const context=this.getUIContext().getHostContext() as common.UIAbilityContext;
      const result: PermissionRequestResult = await abilityAccessCtrl.createAtManager()
        .requestPermissionsFromUser(context, ['ohos.permission.READ_PASTEBOARD']);
      Journal.record('permission.result', result.authResults, JSON.stringify(result.permissions));
    } catch (error) {
      const business=error as BusinessError; Journal.record('permission.reject', [business.code], business.message);
    }
  }
  build() {
    Column({ space: 12 }) {
      Text('__RUN__').id('selection-ready')
      Text(CALLER_ROLE).id('selection-role')
      Text(this.displayState).id('selection-state')
      if (CALLER_ROLE === 'reader') {
        Button('Grant clipboard read').id('selection-grant').onClick(() => { this.grantRead(); })
      }
      Button('Create selection').id('selection-start').onClick(() => {
        this.createSelection();
      })
      if (this.active && this.controller !== undefined) {
        SelectionContainer({ controller: this.controller }) {
          Column({ space: 8 }) {
            Text('__RUN__ alpha').id('selection-alpha').fontSize(18)
            Text('__RUN__ beta').id('selection-beta').fontSize(18)
          }
        }.attributeModifier(this.modifier).id('selection-factory')
          .textJoinStyle(this.directJoin ? SelectionContainerTextJoinStyle.DIRECT : SelectionContainerTextJoinStyle.NEWLINE)
          .onWillCopy((text: string): boolean => {
            Journal.record('willCopy', [this.allowCopy ? 1 : 0], text); return this.allowCopy;
          }).onCopy((text: string) => { this.copied(text); })
        Button('Allow copy').id('selection-allow').onClick(() => {
          Journal.phase = 1; this.allowCopy = true; Journal.record('allow.request', [1]);
        })
        Button('Direct join').id('selection-join').onClick(() => {
          Journal.phase = 2; this.directJoin = true; Journal.record('join.request', [1]);
        })
        Button('Clear selection').id('selection-clear').onClick(() => {
          try {
            this.controller?.closeSelectionMenu(); this.controller?.clearTextSelection(); Journal.record('clear.request', [1]);
          } catch (error) { Journal.record('failed', [], String(error)); }
        })
        Button('Read copied data').id('selection-read').onClick(() => { this.readClipboard(); })
        Button('Remove selection').id('selection-remove').onClick(() => {
          try {
            this.controller?.closeSelectionMenu(); this.controller?.clearTextSelection();
            this.active = false; this.controller = undefined;
            this.displayState = 'removed __RUN__:' + this.cycle; Journal.record('remove.request', [1]);
          } catch (error) { Journal.record('failed', [], String(error)); }
        })
      }
    }.width('100%').height('100%')
  }
}
