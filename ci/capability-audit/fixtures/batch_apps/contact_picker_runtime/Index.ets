/* Copyright (c) 2026 Harmony Contrib
 * SPDX-License-Identifier: Apache-2.0 */
import { common } from '@kit.AbilityKit';
import PickerCases, { CASE_IDS, LaunchInput } from '../model/PickerCases';

class IncomingRequest {
  runId: string = '';
  launchId: string = '';
  caseId: string = '';
  seedIdsJson: string = '[]';
  queryKey: string = '';
}

@Entry({ useSharedStorage: true })
@Component
struct Index {
  @LocalStorageLink('requestJson') @Watch('onLaunchChanged') private requestJson: string = '';
  @LocalStorageLink('lifecycleEvent') @Watch('onLifecycleChanged') private lifecycleEvent: string = '';
  @State private caseName: string = '';
  @State private status: string = 'Waiting for a case';
  private input: LaunchInput = new LaunchInput();
  private valid: boolean = false;
  private visible: boolean = false;
  private started: Set<string> = new Set();
  private runs: PickerCases[] = [];

  aboutToAppear(): void { this.visible = true; this.onLaunchChanged(); }
  aboutToDisappear(): void {
    this.visible = false;
    for (const run of this.runs) { run.dispose(); }
  }

  private onLaunchChanged(): void {
    this.valid = false;
    try {
      const request = JSON.parse(this.requestJson) as IncomingRequest;
      if (typeof request.runId !== 'string' || typeof request.launchId !== 'string' ||
          !/^[A-Za-z0-9_-]{1,64}$/.test(request.runId) ||
          !/^[A-Za-z0-9_-]{1,64}$/.test(request.launchId) || !CASE_IDS.includes(request.caseId)) {
        throw new Error('Invalid case identity');
      }
      const ids = JSON.parse(request.seedIdsJson) as number[];
      if (!Array.isArray(ids) || ids.length === 0 || ids.length > 10000 ||
          ids.some((id: number) => !Number.isSafeInteger(id) || id <= 0) || new Set(ids).size !== ids.length) {
        throw new Error('Invalid seed IDs');
      }
      const minimum = request.caseId.includes('205') ? 205 :
        request.caseId === 'reopen' ? 5 : request.caseId === 'cancel-default' ? 4 : 3;
      if (ids.length < minimum) { throw new Error('Not enough real seed IDs for this case'); }
      if (request.caseId === 'query-no-read' &&
          (typeof request.queryKey !== 'string' || request.queryKey.length === 0)) {
        throw new Error('A real seed query key is required');
      }
      const input = new LaunchInput();
      input.runId = request.runId;
      input.launchId = request.launchId;
      input.caseId = request.caseId;
      input.seedIds = ids;
      input.queryKey = request.queryKey;
      this.input = input;
      this.caseName = input.caseId;
      this.valid = true;
      this.status = 'Ready: ' + input.runId + '/' + input.launchId + '/' + input.caseId;
    } catch (error) { this.status = 'Launch rejected: ' + (error as Error).message; }
  }

  private onLifecycleChanged(): void {
    for (const run of this.runs) { run.lifecycle(this.lifecycleEvent); }
  }

  private startCase(): void {
    if (!this.valid || !this.visible) { return; }
    const input = this.input;
    const identity = input.runId + '/' + input.launchId;
    if (this.started.has(identity)) {
      this.status = 'This launch has already started';
      return;
    }
    this.started.add(identity);
    const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
    try {
      const run = new PickerCases(input, context, (status: string) => {
        if (this.valid && this.visible && this.input === input) { this.status = status; }
      });
      this.runs.push(run);
      this.status = 'Calling public API: ' + input.launchId;
      run.start();
    } catch (error) { this.status = 'Observation failed: ' + (error as Error).message; }
  }

  build() {
    Column({ space: 16 }) {
      Text('Contacts public caller').fontSize(24)
      Text(this.caseName).id('contact_case_id')
      Text(this.status).id('contact_case_status')
      Button('Start case').id('contact_case_start').enabled(this.valid && this.visible).onClick(() => this.startCase())
      Text('Results are recorded for independent review.').fontSize(14)
    }.padding(24).width('100%').height('100%')
  }
}
