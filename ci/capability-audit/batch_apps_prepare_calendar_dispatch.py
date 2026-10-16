#!/usr/bin/env python3
"""Reconstruct exact Calendar native callback patch from pinned editor fixtures."""
import base64
import difflib
import gzip
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'ci/capability-audit/fixtures/batch_apps/calendar_dispatch'
COMPONENT = ROOT / 'patches/common/applications/standard/calendardata/editor_callback_dispatch'
meta = json.loads((FIXTURE / 'provenance.json').read_text())
old = {p: gzip.decompress(base64.b64decode((FIXTURE / v['fixture']).read_bytes())).decode() for p,v in meta['files'].items()}
new = dict(old)
cpp = 'calendarmanager/napi/src/calendar_manager_napi.cpp'
hdr = 'calendarmanager/napi/include/calendar_manager_napi.h'
s = old[hdr].replace('#include <vector>', '#include <vector>\n#include <mutex>')
s = s.replace('namespace OHOS::CalendarApi {', 'namespace OHOS::AbilityRuntime { class AbilityContext; }\nnamespace OHOS::CalendarApi {')
a = s.index('    struct EditEventContext : public ContextBase {')
b = s.index('    static napi_value New(', a)
s = s[:a] + '''    struct EditorEnvironment {
        std::mutex mutex;
        napi_env env = nullptr;
        bool alive = true;
    };
    struct EditEventContext : public ContextBase {
        std::mutex mutex;
        string event;
        string caller;
        int32_t _sessionId = 0;
        // Identity only: reacquire through the caller's live AbilityContext before closing.
        Ace::UIContent *_uiContent = nullptr;
        std::weak_ptr<AbilityRuntime::AbilityContext> hostContext;
        std::shared_ptr<EditorEnvironment> environment;
        napi_deferred deferred = nullptr;
        void *cleanup = nullptr;
        uint64_t generation = 0;
        bool completionQueued = false;
        bool cancelled = false;
        bool settled = false;
        bool closed = false;
    };
    struct EditorCleanup {
        std::shared_ptr<EditorEnvironment> environment;
        std::weak_ptr<EditEventContext> context;
    };

''' + s[b:]
a = s.index('    static void FinishEditor(')
b = s.index('    static napi_value LaunchEditorPage', a)
s = s[:a] + '''    static void CleanupEditorEnvironment(void *data);
    static void CloseEditorSession(const std::shared_ptr<EditEventContext> &ctxt);
    static void QueueEditorResult(const std::shared_ptr<EditEventContext> &ctxt,
        bool failed, int32_t code, const std::string &message, int32_t eventId, bool closeModal);
    static void FinishEditor(const std::shared_ptr<EditEventContext> &ctxt, uint64_t generation,
        bool failed, int32_t code, const std::string &message, int32_t eventId, bool closeModal);
''' + s[b:]
new[hdr] = s
s=old[cpp]
s=s.replace('    auto ctxt = std::make_shared<EditEventContext>();\n    auto input = [env, ctxt]', '    auto ctxt = std::make_shared<EditEventContext>();\n    napi_value jsContext = nullptr;\n    auto input = [env, ctxt, &jsContext]')
s=s.replace('ctxt->_jsContext', 'jsContext')
s=s.replace('    ctxt->_uiContent = abilityContext->GetUIContent();', '    ctxt->hostContext = abilityContext;\n    ctxt->_uiContent = abilityContext->GetUIContent();')
a=s.index('void CalendarManagerNapi::FinishEditor(')
b=s.index('napi_value CalendarManagerNapi::New(',a)
s=s[:a]+'''void CalendarManagerNapi::CleanupEditorEnvironment(void *data)
{
    std::unique_ptr<EditorCleanup> cleanup(static_cast<EditorCleanup *>(data));
    auto environment = cleanup->environment;
    std::lock_guard<std::mutex> envLock(environment->mutex);
    environment->alive = false;
    environment->env = nullptr;
    auto ctxt = cleanup->context.lock();
    if (ctxt == nullptr) {
        return;
    }
    std::lock_guard<std::mutex> lock(ctxt->mutex);
    ctxt->cancelled = true;
    ++ctxt->generation;
    ctxt->completionQueued = false;
    ctxt->deferred = nullptr;
    ctxt->cleanup = nullptr;
    ctxt->_uiContent = nullptr;
    ctxt->closed = true;
}

void CalendarManagerNapi::CloseEditorSession(const std::shared_ptr<EditEventContext> &ctxt)
{
    std::lock_guard<std::mutex> lock(ctxt->mutex);
    if (ctxt->closed || ctxt->_uiContent == nullptr || ctxt->_sessionId <= 0) {
        return;
    }
    ctxt->closed = true;
    auto host = ctxt->hostContext.lock();
    auto content = host == nullptr ? nullptr : host->GetUIContent();
    if (content != nullptr && content == ctxt->_uiContent) {
        // This implementation posts CloseModalUIExtension to UI asynchronously.
        // Keep the lifetime lock until it has copied its native session/id task.
        content->CloseModalUIExtension(ctxt->_sessionId);
    }
}

void CalendarManagerNapi::QueueEditorResult(const std::shared_ptr<EditEventContext> &ctxt,
    bool failed, int32_t code, const std::string &message, int32_t eventId, bool closeModal)
{
    uint64_t generation;
    {
        std::lock_guard<std::mutex> lock(ctxt->mutex);
        if (ctxt->cancelled || ctxt->settled || ctxt->completionQueued) {
            return;
        }
        ctxt->completionQueued = true;
        generation = ctxt->generation;
    }
    napi_status status = napi_closing;
    auto environment = ctxt->environment;
    {
        // Cleanup is registered/removed only on JS. Its mutex excludes a sender
        // from using env while the cleanup hook invalidates the environment.
        std::lock_guard<std::mutex> envLock(environment->mutex);
        if (environment->alive) {
            status = napi_send_event(environment->env,
                [ctxt, generation, failed, code, message, eventId, closeModal] {
                    FinishEditor(ctxt, generation, failed, code, message, eventId, closeModal);
                }, napi_eprio_high);
        }
    }
    if (status != napi_ok) {
        {
            std::lock_guard<std::mutex> lock(ctxt->mutex);
            ctxt->cancelled = true;
            ++ctxt->generation;
            ctxt->completionQueued = false;
            ctxt->deferred = nullptr;
        }
        // No NAPI fallback on a UI callback when JS delivery is unavailable.
        LOG_ERROR("Calendar editor JS event delivery failed");
        CloseEditorSession(ctxt);
    }
}

void CalendarManagerNapi::FinishEditor(const std::shared_ptr<EditEventContext> &ctxt, uint64_t generation,
    bool failed, int32_t code, const std::string &message, int32_t eventId, bool closeModal)
{
    auto environment = ctxt->environment;
    std::lock_guard<std::mutex> envLock(environment->mutex);
    if (!environment->alive) {
        return;
    }
    napi_env env = environment->env;
    napi_deferred deferred;
    void *cleanup;
    {
        std::lock_guard<std::mutex> lock(ctxt->mutex);
        if (ctxt->cancelled || ctxt->settled || ctxt->generation != generation) {
            return;
        }
        ctxt->settled = true;
        ctxt->completionQueued = false;
        deferred = ctxt->deferred;
        ctxt->deferred = nullptr;
        cleanup = ctxt->cleanup;
    }
    napi_handle_scope scope = nullptr;
    if (napi_open_handle_scope(env, &scope) == napi_ok) {
        napi_value result = nullptr;
        if (failed) {
            napi_value text = nullptr;
            napi_value errorCode = nullptr;
            napi_create_string_utf8(env, message.c_str(), NAPI_AUTO_LENGTH, &text);
            napi_create_error(env, nullptr, text, &result);
            napi_create_int32(env, code, &errorCode);
            napi_set_named_property(env, result, "code", errorCode);
            napi_reject_deferred(env, deferred, result);
        } else {
            napi_create_int32(env, eventId, &result);
            napi_resolve_deferred(env, deferred, result);
        }
        napi_close_handle_scope(env, scope);
    } else {
        LOG_ERROR("Calendar editor cannot open JS handle scope");
    }
    if (cleanup != nullptr && napi_remove_env_cleanup_hook(env, CleanupEditorEnvironment, cleanup) == napi_ok) {
        {
            std::lock_guard<std::mutex> lock(ctxt->mutex);
            ctxt->cleanup = nullptr;
        }
        delete static_cast<EditorCleanup *>(cleanup);
    }
    if (closeModal) {
        CloseEditorSession(ctxt);
    }
}

napi_value CalendarManagerNapi::LaunchEditorPage(napi_env env, std::shared_ptr<EditEventContext> ctxt)
{
    napi_value promise = nullptr;
    if (napi_create_promise(env, &ctxt->deferred, &promise) != napi_ok) {
        napi_throw_error(env, nullptr, "Cannot create calendar editor promise");
        return nullptr;
    }
    ctxt->environment = std::make_shared<EditorEnvironment>();
    ctxt->environment->env = env;
    auto cleanup = new EditorCleanup { ctxt->environment, ctxt };
    if (napi_add_env_cleanup_hook(env, CleanupEditorEnvironment, cleanup) != napi_ok) {
        delete cleanup;
        FinishEditor(ctxt, ctxt->generation, true, INTERNAL_ERROR, "Cannot watch calendar editor environment",
            INVALID_EVENT_ID, false);
        return promise;
    }
    ctxt->cleanup = cleanup;
    if (ctxt->error.code != NO_ERROR || ctxt->status != napi_ok || ctxt->_uiContent == nullptr) {
        int32_t code = ctxt->error.code == NO_ERROR ? INTERNAL_ERROR : ctxt->error.code;
        FinishEditor(ctxt, ctxt->generation, true, code, "Calendar editor context is unavailable",
            INVALID_EVENT_ID, false);
        return promise;
    }
    AAFwk::Want want;
    want.SetElementName("com.ohos.calendardata", "EditorUIExtensionAbility");
    want.SetParam("ability.want.params.uiExtensionType", std::string("sys/commonUI"));
    want.SetParam("event", ctxt->event);
    // Caller identity is display-only input and is never used to authorize a write.
    Ace::ModalUIExtensionCallbacks callbacks;
    callbacks = {
        .onRelease = [ctxt](int32_t code) {
            QueueEditorResult(ctxt, code != 0, INTERNAL_ERROR, "Calendar editor was released", INVALID_EVENT_ID, true);
        },
        .onResult = [ctxt](int32_t code, const AAFwk::Want &wantRes) {
            int32_t eventId = wantRes.GetIntParam("eventId", INVALID_EVENT_ID);
            bool failed = code != 0 || eventId == 0;
            int32_t errorCode = wantRes.GetIntParam("errorCode", code > 0 ? code : INTERNAL_ERROR);
            QueueEditorResult(ctxt, failed, errorCode, "Calendar editor operation failed",
                eventId > 0 ? eventId : INVALID_EVENT_ID, true);
        },
        .onReceive = [](const AAFwk::WantParams &) {},
        .onError = [ctxt](int32_t code, const std::string &, const std::string &msg) {
            QueueEditorResult(ctxt, true, code > 0 ? code : INTERNAL_ERROR, msg, INVALID_EVENT_ID, true);
        },
        .onRemoteReady = [](const std::shared_ptr<Ace::ModalUIExtensionProxy> &) {},
        .onDestroy = [ctxt] {
            {
                // Invalidate native lifetime immediately on UI, before posting
                // cancellation. A queued result must never close a dead host.
                std::lock_guard<std::mutex> lock(ctxt->mutex);
                ctxt->closed = true;
                ctxt->_uiContent = nullptr;
                ++ctxt->generation;
                ctxt->completionQueued = false;
            }
            QueueEditorResult(ctxt, false, 0, "", INVALID_EVENT_ID, false);
        },
    };
    Ace::ModalUIExtensionConfig config;
    config = { .isProhibitBack = false };
    int32_t sessionId = ctxt->_uiContent->CreateModalUIExtension(want, callbacks, config);
    uint64_t generation;
    bool cancelSession;
    {
        std::lock_guard<std::mutex> lock(ctxt->mutex);
        ctxt->_sessionId = sessionId;
        generation = ctxt->generation;
        cancelSession = ctxt->cancelled || ctxt->settled;
    }
    if (sessionId <= 0) {
        FinishEditor(ctxt, generation, true, INTERNAL_ERROR, "Cannot create calendar editor session",
            INVALID_EVENT_ID, false);
    } else if (cancelSession) {
        // A send failure during synchronous creation had no session id yet.
        CloseEditorSession(ctxt);
    }
    return promise;
}

''' + s[b:]
new[cpp] = s
COMPONENT.mkdir(parents=True,exist_ok=True)
patch=''.join(''.join(difflib.unified_diff(old[p].splitlines(True),new[p].splitlines(True),fromfile='a/'+meta['project']+'/'+p,tofile='b/'+meta['project']+'/'+p)) for p in old)
(COMPONENT/'0001-dispatch-editor-results-with-native-lifetime-cancellation.patch').write_text(patch)
files=tuple((p,hashlib.sha256(old[p].encode()).hexdigest(),hashlib.sha256(new[p].encode()).hexdigest()) for p in old)
(COMPONENT/'verify_source.py').write_text('''#!/usr/bin/env python3
"""Exact native callback delta; must follow event_editor, without HAP source changes."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/calendardata'
REVISION = 'f922427ca0dc20895a0e254ae41382e5b03299a4'
FILES = '''+repr(files)+'''

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
''')
(COMPONENT/'apply.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
component_dir="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$component_dir/../../../../../lib/apply_exact_component.py" --component-dir "$component_dir" "$@"
''')
meta['patched_sha256']={p:hashlib.sha256(new[p].encode()).hexdigest() for p in old}
(FIXTURE/'provenance.json').write_text(json.dumps(meta,indent=2)+'\n')
