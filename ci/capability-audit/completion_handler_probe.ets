// Real SDK constructor/field contract only; not a component-start service test.
import { CompletionHandlerForAbilityStartCallback as Handler, AbilityStartFailureCode }
  from '@ohos.app.ability.CompletionHandlerForAbilityStartCallback';
import fs from '@ohos.file.fs';

class DerivedHandler extends Handler { marker: number = 7; }
interface Row { runId: string; name: string; values: number[]; error: string; }

@Entry
@Component
struct Index {
  @State private note: string = 'Checking completion handler constructor';
  private readonly runId: string = '__COMPLETION_RUN_ID__';
  private readonly logPath: string = '/data/storage/el2/base/files/completion-handler-__COMPLETION_RUN_ID__-results.log';
  private record(name: string, values: number[], error: string = ''): void {
    const row: Row = { runId: this.runId, name, values, error };
    const file = fs.openSync(this.logPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
    this.note = name;
  }
  private run(): void {
    let completed = 0;
    try {
      const first = new Handler();
      const second = new Handler();
      this.record('constructor', [first instanceof Handler ? 1 : 0, second instanceof Handler ? 1 : 0,
        first !== second ? 1 : 0]); completed++;
      this.record('optional', [first.onRequestSuccess === undefined ? 1 : 0,
        first.onRequestFailure === undefined ? 1 : 0]); completed++;
      let successes = 0; let failures = 0; let argumentsMatch = 0;
      const expected = 'org.harmonycontrib.capabilityaudit#entry#EntryAbility';
      first.onRequestSuccess = (name: string): void => {
        successes++; if (name === expected) { argumentsMatch++; }
      };
      first.onRequestFailure = (name: string, code: AbilityStartFailureCode, message: string): void => {
        failures++; if (name === '' && code === AbilityStartFailureCode.FAILURE_CODE_USER_CANCEL &&
          message === this.runId) { argumentsMatch++; }
      };
      first.onRequestSuccess(expected);
      first.onRequestFailure('', AbilityStartFailureCode.FAILURE_CODE_USER_CANCEL, this.runId);
      this.record('callbacks', [successes, failures, argumentsMatch]); completed++;
      this.record('isolation', [second.onRequestSuccess === undefined ? 1 : 0,
        second.onRequestFailure === undefined ? 1 : 0]); completed++;
      first.onRequestSuccess = undefined; first.onRequestFailure = undefined;
      this.record('mutation', [first.onRequestSuccess === undefined ? 1 : 0,
        first.onRequestFailure === undefined ? 1 : 0]); completed++;
      const derived = new DerivedHandler();
      this.record('subclass', [derived instanceof Handler ? 1 : 0, derived instanceof DerivedHandler ? 1 : 0,
        derived.marker]); completed++;
      let count = 0;
      for (let i = 0; i < 64; i++) {
        const item = new Handler();
        item.onRequestSuccess = (name: string): void => { if (name === this.runId) { count++; } };
        item.onRequestSuccess(this.runId);
      }
      this.record('repeated', [count, AbilityStartFailureCode.FAILURE_CODE_SYSTEM_MALFUNCTION,
        AbilityStartFailureCode.FAILURE_CODE_USER_CANCEL]); completed++;
    } catch (error) { this.record('failed', [], (error as Error).message || 'constructor failure'); }
    this.record('summary', [completed, completed === 7 ? 0 : 1]);
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.logPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file); this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
