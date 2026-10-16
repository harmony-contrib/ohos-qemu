/* Copyright (c) 2026 Harmony Contrib
 * SPDX-License-Identifier: Apache-2.0 */
import { contact } from '@kit.ContactsKit';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';
import ResultJournal, { Observation } from './ResultJournal';

export const CASE_IDS: string[] = ['select-promise', 'select-callback', 'options-promise-205',
  'options-callback-205', 'legacy-promise', 'legacy-callback', 'cancel-empty', 'cancel-default',
  'invalid-limit-promise', 'invalid-limit-callback', 'invalid-filter-callback', 'query-no-read',
  'dual-session', 'exit-pending', 'reopen', 'deadline', 'navigation-dismiss'];

export class LaunchInput {
  runId: string = '';
  launchId: string = '';
  caseId: string = '';
  seedIds: number[] = [];
  queryKey: string = '';
}

class Invocation {
  id: string;
  api: string;
  callbacks: number = 0;
  timer: number = -1;
  constructor(id: string, api: string) { this.id = id; this.api = api; }
}

export default class PickerCases {
  private readonly journal: ResultJournal;
  private readonly input: LaunchInput;
  private readonly context: common.UIAbilityContext;
  private readonly changed: (status: string) => void;
  private readonly pending: Map<string, Invocation> = new Map();
  private disposed: boolean = false;

  constructor(input: LaunchInput, context: common.UIAbilityContext, changed: (status: string) => void) {
    this.input = input;
    this.context = context;
    this.changed = changed;
    this.journal = new ResultJournal(context.filesDir, input.runId, input.launchId, input.caseId);
  }

  private observe(call: Invocation, event: string): Observation {
    const observation = new Observation();
    observation.invocation_id = call.id;
    observation.api = call.api;
    observation.event = event;
    observation.callback_count = call.callbacks;
    observation.after_dispose = this.disposed;
    return observation;
  }

  private begin(slot: string, api: string): Invocation {
    const call = new Invocation(this.input.launchId + '/' + slot, api);
    this.pending.set(call.id, call);
    this.journal.append(this.observe(call, 'begin'));
    // Diagnostic only: never resolve/reject the actual public API or synthesize a
    // result on timeout. The independent runner treats missing results as failure.
    const delay = this.input.caseId === 'deadline' ? 660000 : 180000;
    call.timer = setTimeout(() => {
      call.timer = -1;
      this.journal.append(this.observe(call, 'observer_watchdog'));
      if (!this.disposed) { this.changed('No public API result observed yet: ' + call.id); }
    }, delay);
    return call;
  }

  private terminal(call: Invocation, event: string, value: contact.Contact[] | undefined,
    error: BusinessError | undefined): void {
    if (call.timer >= 0) { clearTimeout(call.timer); call.timer = -1; }
    this.pending.delete(call.id);
    const observation = this.observe(call, event);
    observation.value_type = typeof value;
    // Store precisely the public returned value, with no expected-record fill or
    // shape repair. Undefined/null/nonarray values remain independently visible.
    observation.raw_json = JSON.stringify(value) ?? 'undefined';
    observation.error_type = typeof error;
    if (error !== undefined) {
      observation.error_code = error?.code;
      observation.error_message = error?.message ?? String(error);
    }
    this.journal.append(observation);
    if (!this.disposed) { this.changed(event + ': ' + call.id); }
  }

  private promise(slot: string, api: string, launch: () => Promise<contact.Contact[]>): void {
    const call = this.begin(slot, api);
    try {
      const result = launch();
      const returned = this.observe(call, 'return');
      returned.value_type = typeof result;
      returned.raw_json = result === undefined ? 'undefined' : 'Promise';
      this.journal.append(returned);
      result.then(value => this.terminal(call, 'resolve', value, undefined),
        (error: BusinessError) => this.terminal(call, 'reject', undefined, error));
    } catch (error) { this.terminal(call, 'throw', undefined, error as BusinessError); }
  }

  private callback(slot: string, api: string,
    launch: (callback: (error: BusinessError, value: contact.Contact[]) => void) => void): void {
    const call = this.begin(slot, api);
    try {
      const returned = this.observe(call, 'return');
      const result = launch((error: BusinessError, value: contact.Contact[]) => {
        ++call.callbacks;
        this.terminal(call, 'callback', value, error);
      });
      returned.value_type = typeof result;
      returned.raw_json = String(result);
      this.journal.append(returned);
    } catch (error) { this.terminal(call, 'throw', undefined, error as BusinessError); }
  }

  private options(ids: number[], filterType: contact.FilterType = contact.FilterType.SHOW_FILTER_AND_DEFAULT_SELECT):
    contact.ContactSelectionOptions {
    const filterOption: contact.FilterOptions = { filterCondition: contact.FilterCondition.IN, value: ids };
    const clause: contact.FilterClause = { id: [filterOption] };
    const filter: contact.ContactSelectionFilter = { filterClause: clause, filterType: filterType };
    const options: contact.ContactSelectionOptions = {
      isMultiSelect: true, maxSelectable: 205, isDisplayedByName: true, filter: filter
    };
    return options;
  }

  start(): void {
    const ids = this.input.seedIds;
    switch (this.input.caseId) {
      case 'select-promise':
        this.promise('a', 'selectContacts()', () => contact.selectContacts()); break;
      case 'select-callback':
        this.callback('a', 'selectContacts(callback)', cb => contact.selectContacts(cb)); break;
      case 'options-promise-205':
        this.promise('a', 'selectContacts(options)', () => contact.selectContacts(this.options(ids.slice(0, 205)))); break;
      case 'options-callback-205':
        this.callback('a', 'selectContacts(options,callback)', cb => contact.selectContacts(this.options(ids.slice(0, 205)), cb)); break;
      case 'legacy-promise':
        this.promise('a', 'selectContact()', () => contact.selectContact()); break;
      case 'legacy-callback':
        this.callback('a', 'selectContact(callback)', cb => contact.selectContact(cb)); break;
      case 'cancel-empty':
        this.promise('a', 'selectContacts(options)', () => contact.selectContacts({ isMultiSelect: true })); break;
      case 'cancel-default':
        this.promise('a', 'selectContacts(options)', () => contact.selectContacts(
          this.options(ids.slice(0, 3), contact.FilterType.DEFAULT_SELECT))); break;
      case 'invalid-limit-promise':
        this.promise('a', 'selectContacts({maxSelectable:0})', () => contact.selectContacts({ maxSelectable: 0 })); break;
      case 'invalid-limit-callback':
        this.callback('a', 'selectContacts({maxSelectable:0},callback)', cb => contact.selectContacts({ maxSelectable: 0 }, cb)); break;
      case 'invalid-filter-callback':
        this.callback('a', 'selectContacts(invalidFilter,callback)', cb => contact.selectContacts(
          this.options(ids.slice(0, 1), 999 as contact.FilterType), cb)); break;
      case 'query-no-read':
        this.promise('a', 'queryContact(context,key)', async () => {
          // Keep an unexpected successful read visible as the actual returned
          // record. The independent verifier must reject permission escalation.
          const value = await contact.queryContact(this.context, this.input.queryKey);
          return [value];
        }); break;
      case 'dual-session':
        this.promise('a', 'selectContacts(options)', () => contact.selectContacts(this.options(ids.slice(0, 1))));
        this.callback('b', 'selectContacts(options,callback)', cb => contact.selectContacts(this.options(ids.slice(1, 3)), cb)); break;
      case 'exit-pending':
        this.promise('a', 'selectContacts(options)', () => contact.selectContacts(this.options(ids.slice(0, 1)))); break;
      case 'reopen':
        this.promise('a', 'selectContacts(options)', () => contact.selectContacts(this.options(ids.slice(4, 5)))); break;
      case 'deadline':
        this.promise('a', 'selectContacts(options)', () => contact.selectContacts({ isMultiSelect: true })); break;
      case 'navigation-dismiss':
        this.promise('a', 'selectContacts(options)', () => contact.selectContacts({ isAutoDismissOnNavigation: true })); break;
      default:
        throw new Error('Unknown contact runtime case');
    }
  }

  lifecycle(event: string): void {
    const observation = new Observation();
    observation.event = event;
    observation.after_dispose = this.disposed;
    this.journal.append(observation);
  }

  dispose(): void {
    if (this.disposed) { return; }
    this.disposed = true;
    this.lifecycle('caller_dispose');
    for (const call of this.pending.values()) {
      if (call.timer >= 0) { clearTimeout(call.timer); call.timer = -1; }
    }
    this.pending.clear();
    // Public selection has no cancellation API. Retain the original callback's
    // identity for any late observation; never redirect it to a later launch.
  }
}
