"""Executable scheduling counterexamples, constrained by extracted C++ structure.

This is not C++ execution or an engine emulator. It checks ownership invariants
under explicit GC/queue/teardown schedules and refuses an unrecognized source
shape. Actual native sanitizer, official product TU/link and guest proof remain
separate gates.
"""
import re


def block(source, start):
    """Extract a balanced C++ block, ignoring quoted strings and comments."""
    offset = source.index(start)
    begin = source.index('{', offset)
    token = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]', re.S)
    depth = 0
    for match in token.finditer(source, begin):
        value = match.group()
        if value == '{':
            depth += 1
        elif value == '}':
            depth -= 1
            if depth == 0:
                return source[offset:match.end()]
    raise ValueError('unbalanced extracted C++ block: ' + start)


class SourcePolicy:
    def __init__(self, calendar, queue, repaired):
        region = calendar[calendar.index('struct GetEventsContext'):calendar.index('\nstruct InstancesContext')]
        execute = block(region, 'auto execute =')
        self.snapshot = 'std::shared_ptr<Native::EventFilter> eventFilter;' in region
        self.wrapper_in_worker = 'ctxt->eventFilter->GetNative()' in execute
        self.preserves_promise = 'return fail(status, "Cannot queue calendar async work")' in queue
        self.environment_guard = 'std::weak_ptr<ContextBase> context;' in queue
        self.nonzero_cancel_error = 'SetErrorValue(actx->ctx->error, INTERNAL_ERROR, "Calendar async work cancelled' in queue
        if not repaired:
            assert 'EventFilterNapi* eventFilter;' in region
            assert self.wrapper_in_worker and not self.snapshot
            assert 'napi_delete_reference(ctxt->env, *ctxt->refHolder)' in region
            assert 'napi_get_undefined(env, &promise);\n        delete aCtx;' in queue
            return
        assert self.snapshot and not self.wrapper_in_worker
        assert 'std::shared_ptr<Native::Calendar> calendar;' in region
        assert 'CalendarNapi::ToJson(env, ctxt->self, calendar)' in region
        assert region.index('ctxt->eventFilter = filter->GetNative();') < region.index('NapiQueue::AsyncWork(')
        assert region.index('ctxt->calendar = calendar->GetNative();') < region.index('NapiQueue::AsyncWork(')
        assert 'filter != nullptr, PARAMETER_INVALID' in region
        assert 'ctxt->eventFilter != nullptr, PARAMETER_INVALID' in region
        assert 'ctxt->calendar != nullptr, INTERNAL_ERROR' in region
        assert 'ctxt->calendar->GetEvents(ctxt->eventFilter, ctxt->eventKeys)' in execute
        assert 'ctxt->native' not in execute and 'GetNative' not in execute
        assert not re.search(r'\bnapi_\w+\s*\(', execute)
        assert 'napi_ref' not in region and 'napi_delete_reference' not in region
        assert self.preserves_promise and self.environment_guard and self.nonzero_cancel_error
        worker = block(queue, '[](napi_env env, void* data)')
        assert not re.search(r'\bnapi_\w+\s*\(', worker)
        cleanup = block(queue, 'void CleanupAsyncEnvironment(')
        assert 'context->env = nullptr;' in cleanup
        assert not re.search(r'\bnapi_\w+\s*\(', cleanup)
        assert 'std::unique_ptr<EnvironmentOwner>' in cleanup
        assert 'napi_remove_env_cleanup_hook(env, CleanupAsyncEnvironment, cleanup) == napi_ok' in queue
        assert 'env == nullptr || !actx->environment->alive.load()' in queue
        assert 'actx->ctx->env = nullptr;' in queue
        assert 'status = napi_create_reference(env, self, 1, &selfRef)' in queue
        assert 'Cannot retain calendar async callback' in queue
        for stage in ('resource', 'work'):
            assert 'Cannot create calendar async ' + stage in queue
        assert 'napi_create_error(ctx.env, nullptr, message' in queue
        assert 'napi_set_named_property(ctx.env, result[RESULT_ERROR], "code", code)' in queue
        assert 'napi_get_and_clear_last_exception' in queue
        assert 'napi_call_function(ctx.env, receiver, callback' in queue


class Native:
    def __init__(self):
        self.owners = 1  # original JS wrapper's native shared_ptr
        self.destroyed = 0

    def retain(self):
        assert self.owners > 0
        self.owners += 1

    def release(self):
        assert self.owners > 0, 'double native release'
        self.owners -= 1
        if self.owners == 0:
            self.destroyed += 1


class Wrapper:
    def __init__(self, native):
        self.native = native
        self.alive = True
        self.references = 0
        self.js_owner = True

    def gc(self, force=False):
        self.js_owner = False
        if self.alive and (force or self.references == 0):
            self.alive = False
            self.native.release()


class Engine:
    def __init__(self):
        self.alive = True
        self.thread = 'js'
        self.calls = []
        self.hooks = []

    def napi(self, name):
        assert self.alive, 'NAPI call into a dead environment: ' + name
        assert self.thread == 'js', 'NAPI call on worker: ' + name
        self.calls.append(name)

    def destroy(self):
        self.alive = False
        for hook in self.hooks[:]:
            hook.fire()


class Hook:
    """Environment-owned token; it never owns a raw async request pointer."""
    def __init__(self, engine):
        self.engine = engine
        self.fired = False
        self.released = False
        self.environment_alive = True
        engine.hooks.append(self)

    def fire(self):
        assert not self.released, 'hook invoked twice'
        self.fired = True
        self.released = True
        self.environment_alive = False
        self.engine.hooks.remove(self)

    def unregister(self):
        assert not self.released
        self.released = True
        self.engine.hooks.remove(self)


class Request:
    def __init__(self, policy, engine, wrapper=None, callback=False, bad=None):
        self.policy, self.engine, self.wrapper = policy, engine, wrapper
        self.callback = callback
        self.native = None
        self.done = False
        self.deliveries = []
        self.queued = False
        self.executed = 0
        self.owner_releases = 0
        self.js_reference_releases = 0
        self.hook = None
        self.status = 'argument_error' if bad else 'ok'
        self.promise = 'not_created' if callback else 'pending'
        if wrapper is not None and not bad:
            if policy.snapshot:
                wrapper.native.retain()
                self.native = wrapper.native
            else:
                # Original source creates then immediately deletes the JS ref.
                wrapper.references += 1
                wrapper.references -= 1

    def submit(self, failure=None, unregister_failure=False):
        self.unregister_failure = unregister_failure
        if failure in ('promise', 'self_ref', 'callback_ref'):
            self.promise = 'sync_throw'
            self.release()
            return
        if self.policy.environment_guard and failure != 'hook':
            self.hook = Hook(self.engine)
        if failure:
            if self.policy.preserves_promise:
                self.status = failure + '_error'
                self.deliver()
            else:
                self.promise = 'pending_returned_undefined'
            self.release()
            return
        self.queued = True

    def execute(self):
        assert self.queued and not self.done
        self.engine.thread = 'worker'
        try:
            if self.hook is not None and not self.hook.environment_alive:
                return
            if self.status != 'ok':
                return
            if self.wrapper is not None:
                if self.policy.wrapper_in_worker and not self.wrapper.alive:
                    raise ReferenceError('raw EventFilterNapi used after JS finalization')
                native = self.native if self.policy.snapshot else self.wrapper.native
                assert native.owners > 0, 'destroyed native filter used'
            self.executed += 1
        finally:
            self.engine.thread = 'js'

    def deliver(self, reentrant=None):
        if self.hook is not None and not self.hook.environment_alive:
            return
        self.engine.napi('callback' if self.callback else 'settle')
        assert not self.deliveries, 'double result delivery'
        self.deliveries.append(self.status)
        if not self.callback:
            self.promise = 'resolved' if self.status == 'ok' else 'rejected'
        if reentrant:
            reentrant()

    def complete(self, cancelled=False, null_env=False, output_error=False, reentrant=None):
        assert not self.done
        if null_env and self.hook:
            self.hook.environment_alive = False
        if self.hook and not self.hook.environment_alive:
            self.release()
            return
        if cancelled or output_error:
            self.status = 'INTERNAL_ERROR' if self.policy.nonzero_cancel_error else 'error_code_0'
        self.deliver(reentrant)
        self.release()

    def release(self):
        assert not self.done, 'async request released twice'
        self.done = True
        if self.native is not None:
            self.native.release()
            self.owner_releases += 1
            self.native = None
        if self.hook and self.hook.environment_alive:
            self.engine.napi('unregister')
            if not self.unregister_failure:
                self.hook.unregister()
        if self.engine.alive and (self.hook is None or self.hook.environment_alive or self.hook.fired):
            # A null complete env suppresses NAPI even if the engine hook has
            # not fired yet. The independent token remains valid until exit.
            if self.hook and not self.hook.environment_alive and not self.hook.fired:
                return
            self.engine.napi('release_refs_and_work')
            self.js_reference_releases += 1
