#!/usr/bin/env python3
"""Generate exact lifecycle patches from immutable provider source fixtures."""
from pathlib import Path
import base64, difflib, gzip, hashlib, json

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / 'ci/capability-audit/fixtures/batch_apps/provider_lifecycle'
META = json.loads((FIX / 'inspection.json').read_text())
CONTACTS = 'applications/standard/contacts'
THEME = 'applications/standard/theme'


def original(project, relative):
    record = META['files'].get(project + '/' + relative)
    if record is None:
        return None
    raw = gzip.decompress(base64.b64decode(record['gzip_base64']))
    assert hashlib.sha256(raw).hexdigest() == record['sha256']
    return raw


def change(text, old, new, count=1):
    assert text.count(old) == count, old[:100]
    return text.replace(old, new)


SESSION = '''/* Copyright (c) 2026 Harmony Contrib
 * SPDX-License-Identifier: Apache-2.0 */
import UIExtensionContentSession from '@ohos.app.ability.UIExtensionContentSession';
import { common } from '@kit.AbilityKit';
import ability from '@ohos.ability.ability';
import type { UiExtentionParam } from './ContactUiExtentionAbility';
import WorkerWrapper, { WorkerRequestScope } from '../workers/base/WorkerWrapper';

interface PickerSessionStorage {
  uiExtentionSession: UIExtensionContentSession;
  parameters: UiExtentionParam;
  pickerSession: PickerSession;
  isGettingPickerData: boolean;
  isShowBindSheet: boolean;
  isPickerSearch: boolean;
  isShowAccountants: boolean;
  isFromSaveContactPicker: boolean;
  isSaveExistContact: boolean;
}

// No module/global result destination. Every callback retains this exact session.
export default class PickerSession {
  private static sequence: number = 0;
  public readonly id: number = ++PickerSession.sequence;
  public readonly scope: WorkerRequestScope = new WorkerRequestScope();
  public readonly storage: LocalStorage;
  private resultClaimed: boolean = false;
  private closing: boolean = false;
  private pendingResult: ability.AbilityResult | undefined = undefined;
  public readonly session: UIExtensionContentSession;
  public readonly context: common.UIExtensionContext;
  public readonly worker: WorkerWrapper;
  public params: UiExtentionParam;

  constructor(session: UIExtensionContentSession, context: common.UIExtensionContext,
    params: UiExtentionParam, worker: WorkerWrapper) {
    this.session = session;
    this.context = context;
    this.params = params;
    this.worker = worker;
    const initialStorage: PickerSessionStorage = {
      uiExtentionSession: session, parameters: params, pickerSession: this,
      isGettingPickerData: false, isShowBindSheet: false, isPickerSearch: false,
      isShowAccountants: false, isFromSaveContactPicker: params.isSaveContact,
      isSaveExistContact: params.isSaveExistContact
    };
    this.storage = new LocalStorage(initialStorage);
    if (params.contact !== undefined) { this.storage.setOrCreate('contactFromPicker', params.contact); }
  }

  get active(): boolean { return this.scope.active; }

  addCleanup(cleanup: () => void): () => void {
    return this.scope.onDispose(cleanup);
  }

  delay(action: () => void, milliseconds: number): number {
    let remove: () => void = () => {};
    const timer = setTimeout(() => {
      remove();
      if (this.active) { action(); }
    }, milliseconds);
    remove = this.addCleanup(() => clearTimeout(timer));
    return timer;
  }

  dispose(): void {
    this.scope.dispose();
  }

  async finish(result: ability.AbilityResult): Promise<boolean> {
    if (!this.active || this.closing) { return false; }
    this.resultClaimed = true;
    // Retry only the terminal frame, never resend already delivered chunks.
    this.pendingResult = this.pendingResult ?? result;
    this.closing = true;
    try {
      await this.session.terminateSelfWithResult(this.pendingResult);
      this.dispose();
      return true;
    } catch (error) {
      console.error('Contact picker result delivery failed: ' + error?.message);
      return false;
    } finally {
      this.closing = false;
    }
  }

  async deliver(chunks: Record<string, Object>[], result: ability.AbilityResult): Promise<boolean> {
    if (!this.active) { return false; }
    if (this.resultClaimed) {
      return this.pendingResult !== undefined ? this.finish(this.pendingResult) : false;
    }
    this.resultClaimed = true;
    try {
      for (const chunk of chunks) {
        if (!this.active) { return false; }
        this.session.sendData(chunk);
      }
    } catch (error) {
      console.error('Contact picker chunk delivery failed: ' + error?.message);
      return this.finish({ resultCode: -1 });
    }
    return this.finish(result);
  }
}
'''

SCOPE = '''// Optional request ownership; disposing one scope never closes a shared worker.
export class WorkerRequestScope {
  public active: boolean = true;
  private cleanups: Set<() => void> = new Set();

  onDispose(cleanup: () => void): () => void {
    if (!this.active) { cleanup(); return () => {}; }
    this.cleanups.add(cleanup);
    return () => { this.cleanups.delete(cleanup); };
  }

  dispose(): void {
    if (!this.active) { return; }
    this.active = false;
    const cleanups = Array.from(this.cleanups).reverse();
    this.cleanups.clear();
    for (const cleanup of cleanups) {
      try { cleanup(); } catch (error) {
        HiLog.e(TAG, 'Request cleanup failed: ' + error?.message);
      }
    }
  }
}

'''

SCOPED_WORK = '''  private async sendScopedRequest(request: string, requestData: LooseObject | undefined,
    callBack: Function | undefined, scope: WorkerRequestScope): Promise<void> {
    let target: Function | undefined = callBack;
    let key: string | undefined = undefined;
    let complete: boolean = false;
    let remove: () => void = () => {};
    remove = scope.onDispose(() => {
      target = undefined;
      if (key !== undefined) { this.callBacks.delete(key); }
    });
    const reply = (data: Object | undefined): void => {
      if (complete || !scope.active) { return; }
      complete = true;
      const callback = target;
      target = undefined;
      remove();
      if (key !== undefined) { this.callBacks.delete(key); }
      callback?.(data);
    };
    // Drop the original closure even while audit logging is pending.
    callBack = undefined;
    if (!scope.active) { return; }
    try {
      const log = await assembleLogUtils(request, requestData);
      if (!scope.active) { return; }
      if (!this.useWorker) {
        const task = WorkFactory.getTask(this.getWorkerType());
        if (task === undefined) { throw new Error('Contact data task unavailable'); }
        task.runInWorker(request, reply, requestData);
      } else if (this.mWorker) {
        const message = new WorkerMessage();
        message.request = request;
        message.callBackId = this.requestIndex++;
        message.type = this.getWorkerType();
        message.param = requestData;
        message.log = log;
        key = this.getCallBackKey(message);
        this.callBacks.set(key, reply);
        this.mWorker.postMessage(message);
      } else {
        await this.sendRequestUiThread(request, requestData, reply);
      }
    } catch (error) {
      HiLog.e(TAG, 'Scoped contact query failed: ' + error?.message);
      reply(undefined);
    }
  }

'''

worker = original(CONTACTS, 'entry/src/main/ets/workers/base/WorkerWrapper.ets').decode()
worker = change(worker, 'export default class WorkerWrapper {', SCOPE + 'export default class WorkerWrapper {')
worker = change(worker, 'public async sendRequest (request: string, requestData?: LooseObject, callBack?: Function) {',
'''public async sendRequest (request: string, requestData?: LooseObject, callBack?: Function,
    scope?: WorkerRequestScope) {
    if (scope !== undefined) {
      return this.sendScopedRequest(request, requestData, callBack, scope);
    }''')
worker = change(worker, '  public async close () {', SCOPED_WORK + '  public async close () {')

presenter = original(CONTACTS, 'entry/src/main/ets/presenter/contact/batchselectcontacts/ContactsPickerPresenter.ets').decode()
presenter = change(presenter, "import WorkerWrapper from '../../../workers/base/WorkerWrapper';", "import WorkerWrapper, { WorkerRequestScope } from '../../../workers/base/WorkerWrapper';\nimport type PickerSession from '../../../uiExtentionAbility/PickerSession';")
presenter = change(presenter, '''  public uiExtentionParam = ContactsGlobalThisHelper.GetGlobalThis()
    .getValue<UiExtentionParam>(ContactsGlobalThisHelper.UiExtentionAbilityParams);''', '''  public uiExtentionParam: UiExtentionParam | undefined = undefined;''')
presenter = change(presenter, '  private constructor() {', '''  private static sequence: number = 0;
  public readonly selectionChangedEvent: string = 'ContactPickerSelection.' + (++ContactsPickerPresenter.sequence);
  public resultPending: boolean = false;
  private disposed: boolean = false;
  private generation: number = 0;
  private searchGeneration: number = 0;
  private resultGeneration: number = 0;
  private request?: PickerSession;
  private queryScope: WorkerRequestScope = new WorkerRequestScope();
  private resultScope?: WorkerRequestScope;
  private tasks: Set<taskpool.Task> = new Set();

  public static createForSession(request: PickerSession): ContactsPickerPresenter {
    const presenter = new ContactsPickerPresenter();
    presenter.request = request;
    presenter.uiExtentionParam = request.params;
    // Existing save/edit UI still resolves its presenter through this accessor.
    // Public selection sessions never replace that legacy navigation instance.
    if (request.params.isSaveContact || request.params.isSaveExistContact) {
      ContactsPickerPresenter.sInstance = presenter;
    }
    request.addCleanup(() => presenter.dispose());
    return presenter;
  }

  public isActive(): boolean {
    return !this.disposed && (this.request === undefined || this.request.active);
  }

  private getContext(): common.UIAbilityContext | common.UIExtensionContext {
    return this.request?.context ?? ContactsGlobalThisHelper.GetGlobalThis().getDefaultUIContext();
  }

  private getWorker(): WorkerWrapper {
    return this.request?.worker ?? ContactsGlobalThisHelper.GetGlobalThis()
      .getValue<WorkerWrapper>(ContactsGlobalThisHelper.DataWorkerName);
  }

  private setBusy(value: boolean): void {
    this.resultPending = value;
    if (this.request !== undefined) {
      this.request.storage.setOrCreate('isGettingPickerData', value);
    } else {
      AppStorage.setOrCreate('isGettingPickerData', value);
    }
    this.refreshUI();
  }

  private queryFailed(): void {
    if (!this.isActive()) { return; }
    this.setBusy(false);
    if (this.request !== undefined) {
      this.request.finish({ resultCode: -1 });
    }
  }

  public dispose(): void {
    if (this.disposed) { return; }
    this.disposed = true;
    this.generation++;
    this.searchGeneration++;
    this.resultGeneration++;
    this.queryScope.dispose();
    this.resultScope?.dispose();
    for (const task of this.tasks) {
      try { taskpool.cancel(task); } catch (error) { HiLog.w(TAG, 'Query already running'); }
    }
    this.tasks.clear();
    this.refreshUI = () => {};
    this.clearAllData();
    this.favoriteContactIdSet.clear();
    this.defaultSelectContactMap.clear();
    this.contactSearchList = [];
    this.inputKeyword = '';
    this.selectedCount = 0;
    this.contactsSource = new ContactPickerDataSource();
    this.favoriteSource = new ContactPickerDataSource();
    this.selectedSource = new ContactPickerDataSource();
    this.searchContactsSource = new ContactPickerDataSource();
  }

  private constructor() {''')
presenter = change(presenter, '    this.clearAllData();\n  }\n\n  initNavPaths', '    if (this.request === undefined) { this.dispose(); }\n  }\n\n  initNavPaths')
presenter = change(presenter, '    this.preInitContactList(this.userId);', '    if (!this.isActive()) { return; }\n    this.preInitContactList(this.userId);')
presenter = presenter.replace('emitter.emit(ContactsPickerPresenter.BATCH_SELECT_ITEM_CHECKED', 'emitter.emit(this.selectionChangedEvent')
presenter = change(presenter, "    AppStorage.setOrCreate('isGettingPickerData', false);", '    this.setBusy(false);', 2)
# Query state and destinations never resolve a later global UI session.
presenter = presenter.replace('ContactsGlobalThisHelper.GetGlobalThis().getDefaultUIContext()', 'this.getContext()')
# Restore the fallback getter itself, which intentionally serves ordinary app pages.
presenter = change(presenter, 'return this.request?.context ?? this.getContext();', 'return this.request?.context ?? ContactsGlobalThisHelper.GetGlobalThis().getDefaultUIContext();')
start = presenter.index('  confirm(')
end = presenter.index('  // 从批量选择', start)
old = presenter[start:end]
old = old.replace('  confirm(', '  async confirm(').replace('    try {', '    if (!this.isActive()) { return; }\n    try {', 1)
old = old.replace("      if (!this.isContactsPicker) {", "      const chunks: Record<string, Object>[] = [];\n      if (!this.isContactsPicker) {")
old = old.replace('ContactsGlobalThisHelper.GetGlobalThis().getUIExtensionContentSession()?.sendData(resultData);', 'chunks.push(resultData);')
old = old.replace('ContactsGlobalThisHelper.GetGlobalThis().getUIExtensionContentSession()?.sendData(parameters);', 'chunks.push(parameters);')
a = old.index('      // 兼容 通过 startAbility')
b = old.index('      // 点击完成', a)
old = old[:a] + '''      if (this.request !== undefined) {
        const delivered = await this.request.deliver(chunks, result);
        if (!delivered) { return; }
      } else {
        const session = ContactsGlobalThisHelper.GetGlobalThis().getUIExtensionContentSession();
        for (const chunk of chunks) { session?.sendData(chunk); }
        await this.getContext()?.terminateSelfWithResult(result);
      }

''' + old[b:]
old = old.replace('      this.setBusy(false);', '      if (this.isActive()) { this.setBusy(false); }')
old = old.replace('      HiLog.e(TAG, `confirm error: ${error?.message}`);', '      HiLog.e(TAG, `confirm error: ${error?.message}`);\n      this.queryFailed();')
presenter = presenter[:start] + old + presenter[end:]
# Replace promise-with-async-executor (which never rejected) with awaited tasks.
start = presenter.index('  async preInitContactList(')
end = presenter.index('  refreshContactPickerList(', start)
presenter = presenter[:start] + '''  async preInitContactList(userId: number) {
    const generation = ++this.generation;
    this.queryScope.dispose();
    this.queryScope = new WorkerRequestScope();
    this.searchGeneration++;
    for (const task of this.tasks) {
      try { taskpool.cancel(task); } catch (error) { HiLog.w(TAG, 'Prior query already running'); }
    }
    this.tasks.clear();
    this.clearAllData();
    try {
      const count = await ContactAbilityModel.getAllContactSizeSync(userId, true) as CountAlphabetIndex;
      if (!this.isActive() || generation !== this.generation) { return; }
      const pageCount = Math.ceil(count.count / 10000);
      const queries: Promise<PickerContactList>[] = [];
      for (let page = 0; page < pageCount; page++) {
        const task = this.filter !== undefined ?
          new taskpool.Task(getPickerContactsByFilter, this.isDisplayByName, this.filter, userId,
            page, false, page === 0, this.getContext()) :
          new taskpool.Task(getPickerContactsNoFilter, this.isDisplayByName, userId,
            page, false, page === 0, this.getContext());
        this.tasks.add(task);
        queries.push(taskpool.execute(task).then((data: Object) => data as PickerContactList)
          .finally(() => { this.tasks.delete(task); }));
      }
      const pages = await Promise.all(queries);
      if (!this.isActive() || generation !== this.generation) { return; }
      const result: PickerContactList = { contactList: [], defaultSelectContactMap: new Map(), isEnd: true };
      for (const page of pages) {
        result.contactList.push(...page.contactList);
        page.defaultSelectContactMap.forEach((value, key) => result.defaultSelectContactMap.set(key, value));
      }
      this.refreshContactPickerList(result);
    } catch (error) {
      if (generation === this.generation && this.isActive()) {
        HiLog.e(TAG, 'Contact query failed: ' + error?.message);
        this.queryFailed();
      }
    }
  }

''' + presenter[end:]
presenter = change(presenter, "    HiLog.w(TAG, 'getSearchContactResultFromDb start!!');", "    if (!this.isActive()) { return; }\n    this.searchGeneration++;\n    HiLog.w(TAG, 'getSearchContactResultFromDb start!!');")
presenter = change(presenter, '  contactSearchTaskFromDb() {', '  contactSearchTaskFromDb() {\n    if (!this.isActive()) { return; }\n    const generation = this.searchGeneration;')
presenter = change(presenter, '\n    taskpool.executeDelayed(DELAY_TIME, this.task, taskpool.Priority.HIGH).then((searchResultsObject: Object) => {', '\n    taskpool.executeDelayed(DELAY_TIME, this.task, taskpool.Priority.HIGH).then((searchResultsObject: Object) => {\n      if (!this.isActive() || generation !== this.searchGeneration) { return; }')
# Track search task cancellation separately; stale rejection must not close a new search/session.
presenter = change(presenter, '    taskpool.executeDelayed(DELAY_TIME, this.task, taskpool.Priority.HIGH)', '    this.tasks.add(this.task);\n    taskpool.executeDelayed(DELAY_TIME, this.task, taskpool.Priority.HIGH)')
start = presenter.index('  getPickerDataByIds(')
end = presenter.index('  checkTheParameterType()', start)
presenter = presenter[:start] + '''  getPickerDataByIds(contactIds: Set<number>,
    callBack: (contactIdPickerDataMap: Map<number, contact.Contact>) => void) {
    if (!this.isActive() || this.resultPending) { return; }
    const generation = ++this.resultGeneration;
    const scope = new WorkerRequestScope();
    this.resultScope?.dispose();
    this.resultScope = scope;
    this.setBusy(true);
    if (contactIds.size === 0) { scope.dispose(); callBack(new Map()); return; }
    const worker = this.getWorker();
    if (worker === undefined) { scope.dispose(); this.queryFailed(); return; }
    worker.sendRequest('getPickerDataByIds', {
      context: this.getContext(), contactIds: Array.from(contactIds), userId: this.userId
    }, (data: Map<number, contact.Contact> | undefined) => {
      scope.dispose();
      if (!this.isActive() || generation !== this.resultGeneration) { return; }
      if (data === undefined) { this.queryFailed(); return; }
      callBack(data);
    }, scope);
  }

''' + presenter[end:]
presenter = change(presenter, '''      ContactsGlobalThisHelper.GetGlobalThis()
        .getDefaultUIContext()?.terminateSelfWithResult({
        resultCode: result.code
      })''', '''      if (this.request !== undefined) {
        this.request.finish({ resultCode: result.code });
      } else {
        this.getContext()?.terminateSelfWithResult({ resultCode: result.code });
      }
      this.disposed = true;''')
presenter = change(presenter, '  returnDefaultSelectContactData() {', '''  returnDefaultSelectContactData() {
    if (!this.isActive()) { return; }
    this.resultScope?.dispose();
    this.resultGeneration++;
    this.setBusy(false);''')
presenter = change(presenter, '    ContactsPickerPresenter.sInstance = null;', '    ContactsPickerPresenter.sInstance?.dispose();\n    ContactsPickerPresenter.sInstance = null;')
presenter = change(presenter, 'if (ContactsPickerPresenter.sInstance == null) {', 'if (ContactsPickerPresenter.sInstance == null || ContactsPickerPresenter.sInstance.disposed) {')
presenter = change(presenter, '      this.disposed = true;', '      this.dispose();')

# Fence the older paged-query path as well as the current taskpool path.
presenter = change(presenter, '  initContactList() {', '  initContactList() {\n    if (!this.isActive()) { return; }\n    const generation = this.generation;')
presenter = change(presenter, 'getPhotosInfoAsync(this.userId).then(() => {', 'getPhotosInfoAsync(this.userId).then(() => {\n      if (!this.isActive() || generation !== this.generation) { return; }')
presenter = presenter.replace('''ContactsGlobalThisHelper.GetGlobalThis()
          .getValue<WorkerWrapper>(ContactsGlobalThisHelper.DataWorkerName)?.sendRequest''', 'this.getWorker()?.sendRequest')
presenter = presenter.replace('''ContactsGlobalThisHelper.GetGlobalThis()
        .getValue<WorkerWrapper>(ContactsGlobalThisHelper.DataWorkerName)?.sendRequest''', 'this.getWorker()?.sendRequest')
presenter = change(presenter, '}, (result: PickerContactList) => {', '}, (result: PickerContactList) => {\n          if (!this.isActive() || generation !== this.generation) { return; }\n          if (!result) { this.queryFailed(); return; }', 2)
presenter = change(presenter, '''        })
      }

      this.getWorker()''', '''        }, this.queryScope)
      }

      this.getWorker()''')
presenter = change(presenter, '''      });
    });
  }

  // 初始化数据''', '''      }, this.queryScope);
    }).catch(() => { if (generation === this.generation) { this.queryFailed(); } });
  }

  // 初始化数据''')
presenter = change(presenter, '''            setTimeout(() => {
              this.contactsListInited''', '''            const update = () => {
              if (!this.isActive() || generation !== this.generation) { return; }
              this.contactsListInited''')
presenter = change(presenter, '''            }, 750)''', '''            };
            if (this.request !== undefined) { this.request.delay(update, 750); }
            else { setTimeout(update, 750); }''')
# Release completed search tasks and ignore cancellation/error from old searches.
presenter = change(presenter, '''    this.tasks.add(this.task);
    taskpool.executeDelayed''', '''    const task = this.task;
    this.tasks.add(task);
    taskpool.executeDelayed''')
presenter = change(presenter, '''      HiLog.e(TAG, `contactSearchTaskFromDb error: ${error.message}`);
    })''', '''      if (this.isActive() && generation === this.searchGeneration) { this.queryFailed(); }
      HiLog.e(TAG, `contactSearchTaskFromDb error: ${error.message}`);
    }).finally(() => { this.tasks.delete(task); });''')

extension = original(CONTACTS, 'entry/src/main/ets/uiExtentionAbility/ContactUiExtentionAbility.ets').decode()
extension = change(extension, "import ContactsPickerPresenter from '../presenter/contact/batchselectcontacts/ContactsPickerPresenter'", "import ContactsPickerPresenter from '../presenter/contact/batchselectcontacts/ContactsPickerPresenter'\nimport PickerSession from './PickerSession';")
extension = change(extension, "  private startAbilityCallerBundleName: string = '';", "  private startAbilityCallerBundleName: string = '';\n  private sessions: Map<UIExtensionContentSession, PickerSession> = new Map();\n  private destroyed: boolean = false;")
extension = change(extension, '      this.localId = localId;', '      if (!this.destroyed) { this.localId = localId; }')
a = extension.index('  constructor() {', extension.index('export default class ContactUiExtentionAbility'))
b = extension.index('\n  parseContactParam', a)
extension = extension[:a] + '  constructor() { super(); }\n' + extension[b:]
extension = change(extension, "want.parameters!['ohos.aafwk.param.callerBundleName']", "want.parameters?.['ohos.aafwk.param.callerBundleName']")
extension = change(extension, "want.parameters!['ohos.aafwk.param.callerToken']", "want.parameters?.['ohos.aafwk.param.callerToken']")
a = extension.index('    setInterval(() => {')
b = extension.index('\n\n', a)
extension = extension[:a] + extension[b:]
for declaration in ['  private runTime: number[] = [];\n', '  private sumTime: number = 0;\n',
                    '  private succCount: number = 0;\n', '  private errCodes: Record<string, number> = {};\n',
                    '  private startTime: number = 0;\n', '  private endTime: number = 0\n',
                    '  private localId: number = 100;\n', '  private userId: number = 100;\n']:
    extension = change(extension, declaration, '')
extension = change(extension, '    this.startTime = new Date().getTime()\n', '')
extension = change(extension, '    this.userId = want.parameters?.userId as number;\n', '')
a = extension.index('    this.endTime = new Date().getTime()')
b = extension.index("    HiLog.i(TAG, 'uiExtentionParam parse finish ')", a)
extension = extension[:a] + extension[b:]
extension = change(extension, '  onDestroy() {', '''  onDestroy() {
    this.destroyed = true;
    for (const request of Array.from(this.sessions.values())) { request.dispose(); }
    this.sessions.clear();''')
extension = change(extension, '''  async onSessionCreate(want: Want, session: UIExtensionContentSession) {
    try {''', '''  async onSessionCreate(want: Want, session: UIExtensionContentSession) {
    if (this.destroyed || this.sessions.has(session)) { return; }
    let request: PickerSession | undefined = undefined;
    try {
      const started = Date.now();
      const params = this.parseContactParam(want);
      const duration = Date.now() - started;
      const durations: number[] = [duration];
      request = new PickerSession(session, this.context, params, this.mDataWorker);
      const current = request;
      this.sessions.set(session, current);
      current.addCleanup(() => {
        if (this.sessions.get(session) === current) { this.sessions.delete(session); }
        const globals = ContactsGlobalThisHelper.GetGlobalThis();
        if (globals.getUIExtensionContentSession() === session) {
          globals.remove(ContactsGlobalThisHelper.UiExtentionAbilityUIExtensionContentSession);
          if (globals.getValue<UiExtentionParam>(ContactsGlobalThisHelper.UiExtentionAbilityParams) === params) {
            globals.remove(ContactsGlobalThisHelper.UiExtentionAbilityParams);
          }
        }
        if (this.sessions.size === 0 && globals.getValue(ContactsGlobalThisHelper.UIContextName) === this.context) {
          globals.remove(ContactsGlobalThisHelper.UIContextName);
        }
      });
      current.storage.setOrCreate('pickerPresenter', ContactsPickerPresenter.createForSession(current));
      current.storage.setOrCreate('callerPid', String(want.parameters?.['ohos.aafwk.param.callerPid'] ?? ''));
      const timer = setInterval(() => {
        if (!current.active) { return; }
        HiAppEvent.getInstance().SchedulerUpload(this.processorId, params.callerBundleName,
          started, durations, 1, duration, -1);
      }, 1000);
      current.addCleanup(() => clearInterval(timer));
      const localAccountId = await osAccount.getAccountManager().getOsAccountLocalId();
      if (!current.active) { return; }
      await this.openSession(want, current, localAccountId);
    } catch (error) {
      HiLog.e(TAG, 'Contact picker session failed: ' + error?.message);
      if (request !== undefined) {
        await request.finish({ resultCode: -1 });
        request.dispose();
      } else {
        try { await session.terminateSelfWithResult({ resultCode: -1 }); } catch (_) {}
      }
    }
  }

  private async openSession(want: Want, request: PickerSession, localAccountId: number) {
    const session = request.session;
    const uiExtentionParam = request.params;
    const storage = request.storage;
    try {''')
extension = change(extension, '      let uiExtentionParam: UiExtentionParam = this.parseContactParam(want)', '      if (!request.active) { return; }')
a = extension.index('      let storageParamObj: LooseObject = {')
b = extension.index('      // 判断是否显示子窗', a)
extension = extension[:a] + '''      const foldChanged = (status: display.FoldStatus) => {
        if (request.active) { AppStorage.setOrCreate('isVerdeModel', ScreenFormUtil.isNewFormSmallFoldScreen()); }
      };
      foldChanged(display.getFoldStatus());
      display.on('foldStatusChange', foldChanged);
      request.addCleanup(() => display.off('foldStatusChange', foldChanged));

''' + extension[b:]
extension = change(extension, "        this.context.terminateSelf()", "        await request.finish({ resultCode: 1 });\n        return;")
extension = change(extension, 'this.localId === 100 && this.userId !== undefined && this.userId !== 100', 'localAccountId === 100 && uiExtentionParam.userId !== undefined && uiExtentionParam.userId !== 100')
extension = change(extension, "const subWindowName = 'subWindowPicker'", "const subWindowName = 'subWindowPicker' + request.id")
a = extension.index("        display.on('change', async (data) => {")
b = extension.index('\n\n', a)
extension = extension[:a] + '''        const ownedWindow = subWindow;
        request.addCleanup(() => { ownedWindow.destroyWindow().catch((error: Error) => {
          HiLog.w(TAG, 'Contact subwindow closed: ' + error?.message);
        }); });
        if (!request.active) { return; }
        const displayChanged = async (id: number) => {
          if (!request.active) { return; }
          try {
            const size = display.getDefaultDisplaySync();
            await ownedWindow.resize(size.width, size.height);
          } catch (error) { HiLog.w(TAG, 'Display resize failed: ' + error?.message); }
        };
        display.on('change', displayChanged);
        request.addCleanup(() => display.off('change', displayChanged));''' + extension[b:]
# Every suspended window operation is followed by a native lifetime check.
for operation in ["await subWindow?.resize(newDisplay.width, newDisplay.height)",
                  'await subWindow.setWindowTouchable(true);',
                  "await subWindow?.loadContent('pages/ContactUiExtentionIndex', storage);",
                  'await subWindow?.showWindow();',
                  'await subWindow.setFollowParentWindowLayoutEnabled(true);']:
    extension = change(extension, operation, operation + '\n        if (!request.active) { return; }')
extension = change(extension, "session?.setReceiveDataCallback((data) => {", "session?.setReceiveDataCallback((data) => {\n          if (!request.active) { return; }")
extension = change(extension, '''        this.listenerManager = new ListenerManager();
        this.listenerManager.registerListeners();''', '''        request.addCleanup(() => session.setReceiveDataCallback(() => {}));
        const listeners = new ListenerManager();
        listeners.registerListeners();
        request.addCleanup(() => listeners.unRegisterListeners());''')
extension = change(extension, 'this.mContactListPresenter.startPreInit(() => {', 'this.mContactListPresenter.startPreInit(() => {\n          if (!request.active) { return; }')
for owner, event, type_name, variable in [('subWindow','windowSizeChange','window.Size','subSizeChanged'),
                                         ('subWindow','avoidAreaChange','window.AvoidAreaOptions','subAvoidChanged'),
                                         ('windowProxy','windowSizeChange','window.Size','hostSizeChanged'),
                                         ('windowProxy','avoidAreaChange','window.AvoidAreaOptions','hostAvoidChanged')]:
    pattern = owner + ".on('" + event + "', (data) => {"
    a = extension.index(pattern)
    b = extension.index('          });', a)
    body = extension[a+len(pattern):b]
    extension = extension[:a] + f'''const {variable} = (data: {type_name}) => {{
            if (!request.active) {{ return; }}''' + body + f'''          }};
          {owner}.on('{event}', {variable});
          request.addCleanup(() => {owner}?.off('{event}', {variable}));''' + extension[b+len('          });'):]
extension = change(extension, 'HiLog.e(TAG, `onSessionCreate err: ${err.message} ,err code: ${err.code}`)', "throw new Error('Contact picker session setup failed: ' + (err as Error).message);")
extension = change(extension, '      // 设置窗口监听', '      if (!request.active) { return; }\n      // 设置窗口监听')
extension = change(extension, '    HiLog.i(TAG, `ContactUiExtentionAbility onSessionDestroy`)', '    this.sessions.get(session)?.dispose();\n    HiLog.i(TAG, `ContactUiExtentionAbility onSessionDestroy`)')

# The page wiring and renderer transformations follow.
page = original(CONTACTS, 'entry/src/main/ets/pages/contacts/batchselectcontacts/ContactsPickerPage.ets').decode()
page = change(page, "import ContactsPickerPresenter from '../../../presenter/contact/batchselectcontacts/ContactsPickerPresenter';", "import ContactsPickerPresenter from '../../../presenter/contact/batchselectcontacts/ContactsPickerPresenter';\nimport PickerSession from '../../../uiExtentionAbility/PickerSession';\nimport { WorkerRequestScope } from '../../../workers/base/WorkerWrapper';")
page = change(page, 'let subscriber: commonEventManager.CommonEventSubscriber;\n', '')
page = change(page, 'export default struct ContactsPickerPage {', '''export default struct ContactsPickerPage {
  @LocalStorageLink('pickerSession') private pickerSession: PickerSession | undefined = undefined;
  @LocalStorageLink('parameters') private sessionParameters: UiExtentionParam | undefined = undefined;
  @LocalStorageLink('pickerPresenter') private sessionPresenter: ContactsPickerPresenter | undefined = undefined;
  private pageScope: WorkerRequestScope = new WorkerRequestScope();
  private subscriber?: commonEventManager.CommonEventSubscriber;
  private titleMethodClass: TitleMethodClass = new TitleMethodClass();

  private delay(action: () => void, milliseconds: number): void {
    const scope = this.pageScope;
    let remove: () => void = () => {};
    const timer = setTimeout(() => {
      remove();
      if (scope.active && (this.pickerSession === undefined || this.pickerSession.active)) { action(); }
    }, milliseconds);
    remove = scope.onDispose(() => clearTimeout(timer));
  }
''')
page = change(page, '''  private uiExtentionParam = ContactsGlobalThisHelper.GetGlobalThis()
    .getValue<UiExtentionParam>(ContactsGlobalThisHelper.UiExtentionAbilityParams);''', '''  private uiExtentionParam: UiExtentionParam | undefined = undefined;''', 2)
# SecureAccessPopupTip uses only its own session's caller identity.
page = change(page, '''struct SecureAccessPopupTip {
''', '''struct SecureAccessPopupTip {
  @LocalStorageLink('parameters') private sessionParameters: UiExtentionParam | undefined = undefined;
''')
secure_start = page.index('struct SecureAccessPopupTip {')
secure_end = page.index('\n@Component', secure_start)
secure = page[secure_start:secure_end].replace('this.uiExtentionParam?', 'this.sessionParameters?')
page = page[:secure_start] + secure + page[secure_end:]
page = change(page, '  private session: UIExtensionContentSession = ContactsGlobalThisHelper.GetGlobalThis().getUIExtensionContentSession();', '  private session: UIExtensionContentSession | undefined = undefined;')
page = change(page, "@StorageProp('isGettingPickerData')", "@State")
for key in ['isShowBindSheet','isShowAccountants','isPickerSearch']:
    page = page.replace("@StorageLink('" + key + "')", "@LocalStorageLink('" + key + "')")
page = page.replace('titleMethodClass.', 'this.titleMethodClass.')
# Builder parameters replace the module-wide click handler shared by all pages.
page = change(page, 'let titleMethodClass = new TitleMethodClass()\n', '')
page = change(page, 'export function PickerTitleView($$: TitleVariableClass)', 'export function PickerTitleView($$: TitleVariableClass, methods: TitleMethodClass)')
builder_start = page.index('export function PickerTitleView(')
page = page[:builder_start] + page[builder_start:].replace('this.titleMethodClass.', 'methods.')
# Match the actual builder invocation(s), whose variable object spans lines.
pos = 0
while True:
    pos = page.find('PickerTitleView({', pos)
    if pos < 0: break
    end = page.index('})', pos)
    page = page[:end] + '}, this.titleMethodClass)' + page[end+2:]
    pos = end + 25
page = change(page, '''      if (data) {
        this.titleMethodClass.closeOnClick();''', '''      if (data && this.pageScope.active &&
        this.pickerSession === undefined) {
        this.titleMethodClass.closeOnClick();''')
page = change(page, '        subscriber = commonEventSubscriber;', '''        if (!this.pageScope.active || (this.pickerSession !== undefined && !this.pickerSession.active)) {
          try { commonEventManager.unsubscribe(commonEventSubscriber, this.unsubscribeCB); } catch (_) {}
          return;
        }
        this.subscriber = commonEventSubscriber;''')
page = change(page, 'commonEventManager.subscribe(subscriber,', 'commonEventManager.subscribe(commonEventSubscriber,')
page = change(page, '      commonEventManager.unsubscribe(subscriber, this.unsubscribeCB);', '''      const subscriber = this.subscriber;
      this.subscriber = undefined;
      if (subscriber !== undefined) { commonEventManager.unsubscribe(subscriber, this.unsubscribeCB); }''')
# Subscriber creation can complete after disappear/reappear of the same object.
a = page.index('  private createCB:')
b = page.index('  /**', a)
page = page[:a] + page[b:]
a = page.index('  public async registerSubscriber() {')
b = page.index('  /**', a)
page = page[:a] + '''  public async registerSubscriber() {
    const scope = this.pageScope;
    const request = this.pickerSession;
    // The ordinary Contacts import UI emits this unaddressed broadcast.
    // It cannot authorize terminating an independent public picker request.
    if (request !== undefined) { return; }
    try {
      commonEventManager.createSubscriber(subscribeInfo, (error, subscriber) => {
        if (error) { HiLog.e(TAG, 'Subscriber creation failed: ' + error.message); return; }
        if (!scope.active || scope !== this.pageScope || request !== this.pickerSession) {
          try { commonEventManager.unsubscribe(subscriber, this.unsubscribeCB); } catch (_) {}
          return;
        }
        this.subscriber = subscriber;
        scope.onDispose(() => {
          if (this.subscriber === subscriber) {
            this.subscriber = undefined;
            commonEventManager.unsubscribe(subscriber, this.unsubscribeCB);
          }
        });
        commonEventManager.subscribe(subscriber, (err, data) => {
          if (scope.active && scope === this.pageScope) { this.handleVcardShareSubscribeCB(err, data); }
        });
      });
    } catch (error) { HiLog.e(TAG, 'Subscriber registration failed: ' + error?.message); }
  }

''' + page[b:]
page = change(page, '  async aboutToAppear() {', '''  async aboutToAppear() {
    this.pageScope.dispose();
    this.pageScope = new WorkerRequestScope();
    const scope = this.pageScope;
    this.pickerSession?.addCleanup(() => scope.dispose());
    this.uiExtentionParam = this.sessionParameters;
    this.session = this.pickerSession?.session;
    this.mPresenter = this.sessionPresenter ?? ContactsPickerPresenter.getInstance();''')
page = change(page, '    this.localId = await osAccount.getAccountManager().getOsAccountLocalId();', '''    try {
      this.localId = await osAccount.getAccountManager().getOsAccountLocalId();
    } catch (error) {
      if (scope.active) { this.pickerSession?.finish({ resultCode: -1 }); }
      return;
    }
    if (!scope.active || (this.pickerSession !== undefined && !this.pickerSession.active)) { return; }''')
page = change(page, '    this.mPresenter.refreshUI = () => {', '    this.mPresenter.refreshUI = () => {\n      if (!scope.active) { return; }\n      this.isGettingPickerData = this.mPresenter.resultPending;')
page = change(page, '''          this.session?.terminateSelfWithResult({ resultCode: 1 }).then(() => {''', '''          (this.pickerSession !== undefined ? this.pickerSession.finish({ resultCode: 1 }) :
            this.session?.terminateSelfWithResult({ resultCode: 1 }))?.then(() => {''')
page = change(page, '''      if (!this.isGettingPickerData) {
        if (this.isSaveExistContact)''', '''      if (this.mPresenter.isActive()) {
        if (this.isSaveExistContact)''')
page = change(page, '''          setTimeout(() => {
            this.mPresenter.returnDefaultSelectContactData();
          }, 100);''', '''          this.mPresenter.returnDefaultSelectContactData();''')
page = change(page, '''                setTimeout(() => {
                  this.mPresenter.selectBatchContact();
                }, 100);''', '''                this.mPresenter.selectBatchContact();''')
page = page.replace('    setTimeout(() => {', '    this.delay(() => {')
page = change(page, '''    emitter.off(ContactsPickerPresenter.BATCH_SELECT_ITEM_CHECKED);''', '''    this.pageScope.dispose();
    this.mPresenter.refreshUI = () => {};
    this.intelligenceGroupAddContactDialogControler?.close();''')
page = change(page, '        this.mPresenter.searchSerInitStatus = Number(res.toString());', '        if (this.pageScope.active && this.mPresenter.isActive()) {\n          this.mPresenter.searchSerInitStatus = Number(res.toString());\n        }')
page = change(page, '''      });
    }
    if (this.isSearching)''', '''      }).catch((error: Error) => HiLog.w(TAG, 'Search service unavailable: ' + error?.message));
    }
    if (this.isSearching)''')
# Only per-item emitter callbacks are removed, never another session's listeners.
page = change(page, '    emitter.on(ContactsPickerPresenter.BATCH_SELECT_ITEM_CHECKED, (eventData: emitter.EventData) => {', '    emitter.on(this.presenter.selectionChangedEvent, this.selectionChanged);')
# The previous callback body now becomes a stable field, not a leaked closure.
a = page.index('      let contactId = eventData.data?.contactId as number;')
b = page.index('    this.updateInfo();', a)
callback = page[a:b]
assert callback.endswith('    })\n')
callback = callback[:-len('    })\n')]
page = page[:a] + page[b:]
item_start = page.rfind('@Component', 0, page.index('    emitter.on(this.presenter.selectionChangedEvent'))
item_end = page.index('  updateInfo() {', item_start)
page = page[:item_end] + '''  private itemGeneration: number = 0;
  private itemActive: boolean = false;
  private selectionChanged = (eventData: emitter.EventData): void => {
    if (!this.itemActive || !this.presenter.isActive()) { return; }
''' + callback + '''  };

''' + page[item_end:]
page = change(page, '  updateInfo() {', '  updateInfo() {\n    const generation = ++this.itemGeneration;\n    const contactId = this.item.contactId;')
page = change(page, '        this.photoPixelMap = res;', '''        if (!this.itemActive || !this.presenter.isActive() || generation !== this.itemGeneration ||
          contactId !== this.item.contactId) { return; }
        this.photoPixelMap = res;''')
page = change(page, '}, ContactsGlobalThisHelper.GetGlobalThis().getDefaultUIContext(), false)', '}, this.getUIContext().getHostContext(), false)')
page = change(page, '    emitter.on(this.presenter.selectionChangedEvent, this.selectionChanged);', '''    this.itemActive = true;
    emitter.on(this.presenter.selectionChangedEvent, this.selectionChanged);''')
page = change(page, '''  aboutToRecycle(): void {
  }

  aboutToDisappear(): void {
  }''', '''  aboutToRecycle(): void {
    this.itemActive = false;
    this.itemGeneration++;
  }

  aboutToDisappear(): void {
    this.itemActive = false;
    this.itemGeneration++;
    emitter.off(this.presenter.selectionChangedEvent, this.selectionChanged);
  }''')
page = change(page, '  aboutToReuse(): void {\n    this.updateInfo();', '  aboutToReuse(): void {\n    this.itemActive = true;\n    this.updateInfo();')
page = change(page, '  private itemGeneration: number = 0;', '''  private itemGeneration: number = 0;
  private selectionEvent: string | undefined = undefined;

  private bindSelection(): void {
    this.unbindSelection();
    this.selectionEvent = this.presenter.selectionChangedEvent;
    emitter.on(this.selectionEvent, this.selectionChanged);
  }

  private unbindSelection(): void {
    if (this.selectionEvent !== undefined) {
      emitter.off(this.selectionEvent, this.selectionChanged);
      this.selectionEvent = undefined;
    }
  }''')
page = change(page, '    emitter.on(this.presenter.selectionChangedEvent, this.selectionChanged);', '    this.bindSelection();')
page = change(page, '    emitter.off(this.presenter.selectionChangedEvent, this.selectionChanged);', '    this.unbindSelection();')
page = change(page, '  aboutToReuse(): void {\n    this.itemActive = true;', '  aboutToReuse(): void {\n    this.bindSelection();\n    this.itemActive = true;')
page = change(page, '  aboutToRecycle(): void {\n    this.itemActive = false;', '  aboutToRecycle(): void {\n    this.unbindSelection();\n    this.itemActive = false;')
# Preserve ordinary-app/save navigation's existing global bindings. Independent
# public selection sessions use only their local values and never mirror them.
for key in ['isShowBindSheet', 'isShowAccountants', 'isPickerSearch']:
    page = page.replace("@LocalStorageLink('" + key + "')", "@LocalStorageLink('" + key + "') @Watch('mirrorLegacyFlags')", 1)
page = change(page, '  private pageScope: WorkerRequestScope = new WorkerRequestScope();', '''  private pageScope: WorkerRequestScope = new WorkerRequestScope();

  private mirrorLegacyFlags(propertyName: string): void {
    const params = this.sessionParameters;
    if (this.pickerSession !== undefined && !(params?.isSaveContact || params?.isSaveExistContact ||
      params?.urlType === 'ContactList' || params?.urlType === 'ContactDetail')) { return; }
    if (propertyName === 'isShowBindSheet') { AppStorage.setOrCreate('isShowBindSheet', this.isShowBindSheet); }
    if (propertyName === 'isShowAccountants') { AppStorage.setOrCreate('isShowAccountants', this.isShowAccountants); }
    if (propertyName === 'isSearching') { AppStorage.setOrCreate('isPickerSearch', this.isSearching); }
  }''')

index = original(CONTACTS, 'entry/src/main/ets/pages/ContactUiExtentionIndex.ets').decode()
index = change(index, "import ContactsPickerPresenter from '../presenter/contact/batchselectcontacts/ContactsPickerPresenter';", "import ContactsPickerPresenter from '../presenter/contact/batchselectcontacts/ContactsPickerPresenter';\nimport PickerSession from '../uiExtentionAbility/PickerSession';\nimport { WorkerRequestScope } from '../workers/base/WorkerWrapper';")
index = change(index, 'let storage = LocalStorage.getShared()\n\n@Entry(storage)', '@Entry({ useSharedStorage: true })')
index = change(index, '''  private uiExtentionParam = ContactsGlobalThisHelper.GetGlobalThis()
    .getValue<UiExtentionParam>(ContactsGlobalThisHelper.UiExtentionAbilityParams);''', '''  @LocalStorageLink('parameters') private uiExtentionParam: UiExtentionParam = new UiExtentionParam();
  @LocalStorageLink('pickerSession') private pickerSession: PickerSession | undefined = undefined;
  private pageScope: WorkerRequestScope = new WorkerRequestScope();''')
index = change(index, '  private mPresenter: ContactsPickerPresenter = ContactsPickerPresenter.getInstance();', "  @LocalStorageLink('pickerPresenter') private mPresenter: ContactsPickerPresenter = ContactsPickerPresenter.getInstance();")
for key in ['isShowBindSheet','isShowAccountants']:
    index = index.replace("@StorageLink('" + key + "')", "@LocalStorageLink('" + key + "')")
for key in ['isGettingPickerData','isFromSaveContactPicker','isSaveExistContact','contactFromPicker']:
    index = index.replace("@StorageProp('" + key + "')", "@LocalStorageProp('" + key + "')")
index = change(index, '  aboutToAppear() {', '''  aboutToAppear() {
    this.pageScope.dispose();
    this.pageScope = new WorkerRequestScope();
    const scope = this.pageScope;
    this.pickerSession?.addCleanup(() => scope.dispose());''')
index = change(index, '  onPageShow(): void {', '  onPageShow(): void {\n    const scope = this.pageScope;')
index = change(index, "      HiLog.i(TAG, 'show bind sheet')", "      if (!scope.active || !this.pickerSession?.active) { return; }\n      HiLog.i(TAG, 'show bind sheet')")
index = change(index, '\n    setTimeout(() => {', '\n    const timer = setTimeout(() => {')
index = change(index, '    }, 100)\n  }', '    }, 100);\n    scope.onDispose(() => clearTimeout(timer));\n  }')
index = change(index, "    HiLog.i(TAG, 'aboutToDisappear!');", "    this.pageScope.dispose();\n    HiLog.i(TAG, 'aboutToDisappear!');")
index = index.replace('if (!this.isGettingPickerData) {', 'if (this.pickerSession?.active) {')
# Cancel/default-selection work is owned by the session, not a disappearing sheet's timer.
index = change(index, '''                setTimeout(() => {
                  // 选择联系人Picker，侧滑返回，返回默认选中的数据
                  this.mPresenter.returnDefaultSelectContactData();
                }, 100);''', '''                this.mPresenter.returnDefaultSelectContactData();''')
for prefix in ['''                ContactsGlobalThisHelper.GetGlobalThis()
                  .getDefaultUIContext()?.terminateSelfWithResult({ resultCode: 1 })''',
               '''              ContactsGlobalThisHelper.GetGlobalThis()
                .getDefaultUIContext()?.terminateSelfWithResult({ resultCode: 1 })''']:
    index = change(index, prefix, 'this.pickerSession?.finish({ resultCode: 1 })')
index = index.replace('this.isGettingPickerData', 'this.currentBusy')
index = change(index, '  private pageScope: WorkerRequestScope = new WorkerRequestScope();', '''  private pageScope: WorkerRequestScope = new WorkerRequestScope();
  @StorageProp('isGettingPickerData') private legacyGettingPickerData: boolean = false;
  @StorageLink('isShowAccountants') private legacyShowAccountants: boolean = false;

  private isLegacyFlow(): boolean {
    return this.uiExtentionParam.isSaveContact || this.uiExtentionParam.isSaveExistContact ||
      this.uiExtentionParam.urlType === URL_TYPE_CONTACT_LIST ||
      this.uiExtentionParam.urlType === URL_TYPE_CONTACT_DETAIL;
  }

  private get currentBusy(): boolean {
    return this.isLegacyFlow() ? this.legacyGettingPickerData : this.isGettingPickerData;
  }''')
index = index.replace('if (this.pickerSession?.active) {', 'if (this.pickerSession?.active && (!this.isLegacyFlow() || !this.currentBusy)) {')
index = change(index, '''      Accountants({ isShowAccountants: $isShowAccountants })''', '''      if (this.isLegacyFlow()) {
        Accountants({ isShowAccountants: $legacyShowAccountants })
      } else {
        Accountants({ isShowAccountants: $isShowAccountants })
      }''')
index = change(index, '.bindSheet(this.isShowAccountants, this.ShowAccountantsView(),', '.bindSheet(this.isLegacyFlow() ? this.legacyShowAccountants : this.isShowAccountants, this.ShowAccountantsView(),')

RENDERER = '''// @ts-nocheck
/* Copyright (c) 2022 Huawei Device Co., Ltd.
 * Copyright (c) 2026 Harmony Contrib
 * SPDX-License-Identifier: Apache-2.0 */
import windowManager from '@ohos.window';
import Extension from '@ohos.WallpaperExtension';
import wallPaper from '@ohos.wallpaper';

const MODULE_TAG = 'ExtWallpaper: ';

export default class WallpaperExtAbility extends Extension {
  private generation: number = 0;
  private imageGeneration: number = 0;
  private active: boolean = false;
  private wallpaperWindow: windowManager.Window | undefined = undefined;

  onCreated(want) {
    this.onDestroy();
    this.active = true;
    const generation = ++this.generation;
    this.createWindow(generation);
    this.sendPixelMapData();
  }

  private async createWindow(generation: number): Promise<void> {
    let owned: windowManager.Window | undefined = undefined;
    try {
      owned = await windowManager.create(this.context, 'wallpaper' + generation, 2000);
      if (!this.active || generation !== this.generation) {
        await this.destroyWindow(owned);
        return;
      }
      this.wallpaperWindow = owned;
      await owned.loadContent('pages/index');
      if (!this.active || generation !== this.generation) { return; }
      await owned.show();
      if (!this.active || generation !== this.generation) { return; }
      await owned.setFullScreen(true);
    } catch (error) {
      console.error(MODULE_TAG + 'window creation failed: ' + error?.code + ': ' + error?.message);
      // Only close this creation's window. A newer creation may already own another.
      if (owned !== undefined && this.wallpaperWindow === owned) {
        this.wallpaperWindow = undefined;
        await this.destroyWindow(owned);
      }
    }
  }

  private async destroyWindow(owned: windowManager.Window): Promise<void> {
    try { await owned.destroy(); }
    catch (error) { console.error(MODULE_TAG + 'window teardown failed: ' + error?.message); }
  }

  onWallpaperChanged(wallpaperType) {
    if (this.active) { this.sendPixelMapData(); }
  }

  onDestroy() {
    this.active = false;
    this.generation++;
    this.imageGeneration++;
    const owned = this.wallpaperWindow;
    this.wallpaperWindow = undefined;
    if (owned !== undefined) { this.destroyWindow(owned); }
  }

  initWallpaperImage() {
    if (this.active) { this.sendPixelMapData(); }
  }

  sendPixelMapData() {
    if (!this.active || !wallPaper) { return; }
    const generation = this.generation;
    const imageGeneration = ++this.imageGeneration;
    try {
      wallPaper.getPixelMap(0, (error, data) => {
        if (!this.active || generation !== this.generation || imageGeneration !== this.imageGeneration) { return; }
        if (error || data === undefined || data === null) {
          console.error(MODULE_TAG + 'wallpaper read failed: ' + error?.message);
          return;
        }
        AppStorage.SetOrCreate('slPixelData', data);
      });
    } catch (error) {
      console.error(MODULE_TAG + 'wallpaper request failed: ' + error?.message);
    }
  }
}
'''


def emit(project, component_name, outputs):
    component = ROOT / 'patches/common' / project / component_name
    component.mkdir(parents=True, exist_ok=True)
    files, patches = [], []
    for relative, text in outputs.items():
        before = original(project, relative)
        after = text.encode()
        # Existing Contacts business source is LF; preserve Theme CRLF only in
        # removed hunks so original no-final-newline input remains exact.
        assert before != after
        files.append((relative, hashlib.sha256(before).hexdigest() if before is not None else None,
                      hashlib.sha256(after).hexdigest()))
        path = project + '/' + relative
        patches.append(f'diff --git a/{path} b/{path}\n'.encode())
        if before is None: patches.append(b'new file mode 100644\n')
        for line in difflib.unified_diff((before or b'').decode().splitlines(keepends=True),
                                        text.splitlines(keepends=True),
                                        fromfile='a/' + path if before is not None else '/dev/null', tofile='b/' + path):
            patches.append(line.encode())
            if not line.endswith('\n'): patches.append(b'\n\\ No newline at end of file\n')
    (component / '0001-isolate-provider-lifetimes-and-release-owned-resources.patch').write_bytes(b''.join(patches))
    verifier = '''#!/usr/bin/env python3
"""Fail closed on drift or mixed business lifecycle patches."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
'''
    verifier += f'\nPROJECT = {project!r}\nREVISION = {META["projects"][project]!r}\nFILES = (\n'
    verifier += ''.join('    ' + repr(row) + ',\n' for row in files) + ')\n\n'
    verifier += 'def validate(root, require_patched=False):\n    return validate_component(root, PROJECT, REVISION, FILES, require_patched)\n'
    (component / 'verify_source.py').write_text(verifier)
    (component / 'apply.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
component_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec python3 "$component_dir/../../../../../lib/apply_exact_component.py" --component-dir "$component_dir" "$@"
''')
    return {project + '/' + row[0]: row[2] for row in files}


targets = emit(CONTACTS, 'picker_session_lifecycle', {
    'entry/src/main/ets/uiExtentionAbility/PickerSession.ets': SESSION,
    'entry/src/main/ets/uiExtentionAbility/ContactUiExtentionAbility.ets': extension,
    'entry/src/main/ets/workers/base/WorkerWrapper.ets': worker,
    'entry/src/main/ets/presenter/contact/batchselectcontacts/ContactsPickerPresenter.ets': presenter,
    'entry/src/main/ets/pages/contacts/batchselectcontacts/ContactsPickerPage.ets': page,
    'entry/src/main/ets/pages/ContactUiExtentionIndex.ets': index,
})
targets.update(emit(THEME, 'renderer_lifecycle', {
    'product/phone/src/main/ets/WallpaperExtAbility/WallpaperExtAbility.ts': RENDERER,
    'product/pad/src/main/ets/WallpaperExtAbility/WallpaperExtAbility.ts': RENDERER,
}))
(FIX / 'candidate-hashes.json').write_text(json.dumps(targets, indent=2) + '\n')
print('generated 8 scoped provider lifecycle targets')

# The remaining original implementation transformations are below.
