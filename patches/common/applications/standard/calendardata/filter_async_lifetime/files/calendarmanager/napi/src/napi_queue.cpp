/*
 * Copyright (c) 2023 Huawei Device Co., Ltd.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "napi_queue.h"
#include <atomic>
#include <new>
namespace OHOS::CalendarApi {
namespace {
struct AsyncEnvironment {
    std::atomic<bool> alive { true };
    std::weak_ptr<ContextBase> context;
};

using EnvironmentOwner = std::shared_ptr<AsyncEnvironment>;

void CleanupAsyncEnvironment(void* data)
{
    // The environment owns this small hook token, never a raw AsyncContext.
    // It may outlive normal completion if unregistering the hook fails.
    std::unique_ptr<EnvironmentOwner> owner(static_cast<EnvironmentOwner*>(data));
    (*owner)->alive.store(false);
    auto context = (*owner)->context.lock();
    if (context != nullptr) {
        context->env = nullptr;
    }
}

void ThrowAsyncError(napi_env env, const char* message)
{
    bool pending = false;
    napi_is_exception_pending(env, &pending);
    if (!pending) {
        napi_throw_error(env, nullptr, message);
    }
}
} // namespace

ContextBase::~ContextBase()
{
    LOG_DEBUG("no memory leak after callback or promise[resolved/rejected]");
    if (env != nullptr) {
        if (callbackRef != nullptr) {
            auto status = napi_delete_reference(env, callbackRef);
            LOG_DEBUG("status:%{public}d", status);
        }
        if (selfRef != nullptr) {
            auto status = napi_delete_reference(env, selfRef);
            LOG_DEBUG("status:%{public}d", status);
        }
        env = nullptr;
    }
}

void ContextBase::GetCbInfo(napi_env envi, napi_callback_info info, NapiCbInfoParser parse, bool sync)
{
    env = envi;
    size_t argc = ARGC_MAX;
    napi_value argv[ARGC_MAX] = { nullptr };
    status = napi_get_cb_info(env, info, &argc, argv, &self, nullptr);
    CHECK_STATUS_RETURN_VOID(this, PARAMETER_INVALID, " napi_get_cb_info failed!");
    CHECK_ARGS_RETURN_VOID(this, argc <= ARGC_MAX, PARAMETER_INVALID, " too many arguments!");
    CHECK_ARGS_RETURN_VOID(this, self != nullptr, PARAMETER_INVALID, " no JavaScript this argument!");
    if (!sync) {
        status = napi_create_reference(env, self, 1, &selfRef);
        if (status != napi_ok) {
            ThrowAsyncError(env, "Cannot retain calendar async receiver");
        }
        CHECK_STATUS_RETURN_VOID(this, INTERNAL_ERROR, " ref self failed!");
    }
    status = napi_unwrap(env, self, &native);
    CHECK_STATUS_RETURN_VOID(this, INTERNAL_ERROR, " self unwrap failed!");

    if (!sync && (argc > 0)) {
        // get the last arguments :: <callback>
        size_t index = argc - 1;
        napi_valuetype type = napi_undefined;
        napi_status tyst = napi_typeof(env, argv[index], &type);
        if ((tyst == napi_ok) && (type == napi_function)) {
            status = napi_create_reference(env, argv[index], 1, &callbackRef);
            if (status != napi_ok) {
                SetErrorValue(error, INTERNAL_ERROR, "ref callback failed!");
                // No callback handle exists to deliver a failure. Keep the
                // original exception or throw synchronously instead.
                ThrowAsyncError(env, "Cannot retain calendar async callback");
                return;
            }
            argc = index;
            LOG_DEBUG(" async callback, no promise");
        } else {
            LOG_DEBUG(" no callback, async pormose");
        }
    }

    if (parse) {
        parse(argc, argv);
    } else {
        CHECK_ARGS_RETURN_VOID(this, argc == 0, PARAMETER_INVALID, " required no arguments!");
    }
}

napi_value NapiQueue::AsyncWork(napi_env env, std::shared_ptr<ContextBase> ctxt, const std::string& name,
                                NapiAsyncExecute execute, NapiAsyncComplete complete)
{
    LOG_DEBUG("name = %{public}s", name.c_str());
    bool pending = false;
    napi_is_exception_pending(env, &pending);
    if (pending) {
        return nullptr;
    }
    // This local owner extends the existing private context without changing
    // the queue header/ABI. NAPI references and work are released only on the
    // JS complete/submission path while the environment is still alive.
    struct WorkContext : AsyncContext {
        EnvironmentOwner environment = std::make_shared<AsyncEnvironment>();
        EnvironmentOwner* cleanup = nullptr;

        ~WorkContext()
        {
            if (env == nullptr || !environment->alive.load()) {
                env = nullptr;
                if (ctx != nullptr) {
                    ctx->env = nullptr;
                }
                // The engine owns JS handles/work during teardown. Its hook
                // owns cleanup independently; do not call NAPI on a dead env.
                return;
            }
            if (cleanup != nullptr && napi_remove_env_cleanup_hook(env, CleanupAsyncEnvironment, cleanup) == napi_ok) {
                delete cleanup;
            }
            cleanup = nullptr;
            if (!environment->alive.load()) {
                env = nullptr;
                if (ctx != nullptr) {
                    ctx->env = nullptr;
                }
            }
        }
    };
    auto* aCtx = new (std::nothrow) WorkContext;
    if (aCtx == nullptr) {
        ThrowAsyncError(env, "Cannot allocate calendar async context");
        return nullptr;
    }
    aCtx->env = env;
    aCtx->ctx = std::move(ctxt);
    aCtx->environment->context = aCtx->ctx;
    aCtx->execute = std::move(execute);
    aCtx->complete = std::move(complete);
    napi_value promise = nullptr;
    if (aCtx->ctx->callbackRef == nullptr) {
        auto status = napi_create_promise(env, &aCtx->deferred, &promise);
        if (status != napi_ok) {
            delete aCtx;
            ThrowAsyncError(env, "Cannot create calendar async promise");
            return nullptr;
        }
        LOG_DEBUG("AsyncWork create deferred promise");
    } else {
        if (napi_get_undefined(env, &promise) != napi_ok) {
            delete aCtx;
            ThrowAsyncError(env, "Cannot create calendar callback return value");
            return nullptr;
        }
    }
    auto fail = [aCtx, promise](napi_status status, const char* message) {
        aCtx->ctx->status = status;
        if (aCtx->ctx->error.code == NO_ERROR) {
            SetErrorValue(aCtx->ctx->error, INTERNAL_ERROR, message);
        }
        // Preserve the original promise and reject it, or invoke the callback
        // once with the real failure. The work has never been queued here.
        GenerateOutput(*aCtx, nullptr);
        delete aCtx;
        return promise;
    };
    aCtx->cleanup = new (std::nothrow) EnvironmentOwner(aCtx->environment);
    if (aCtx->cleanup == nullptr) {
        return fail(napi_generic_failure, "Cannot allocate calendar environment owner");
    }
    auto status = napi_add_env_cleanup_hook(env, CleanupAsyncEnvironment, aCtx->cleanup);
    if (status != napi_ok) {
        delete aCtx->cleanup;
        aCtx->cleanup = nullptr;
        return fail(status, "Cannot watch calendar async environment");
    }
    napi_value resource = nullptr;
    status = napi_create_string_utf8(env, name.c_str(), NAPI_AUTO_LENGTH, &resource);
    if (status != napi_ok) {
        return fail(status, "Cannot create calendar async resource");
    }
    status = napi_create_async_work(
        env, nullptr, resource,
        [](napi_env env, void* data) {
            CHECK_RETURN_VOID(data != nullptr, "AsyncWork napi_async_execute_callback nullptr");
            auto actx = static_cast<WorkContext*>(data);
            if (!actx->environment->alive.load()) {
                return;
            }
            LOG_DEBUG("AsyncWork napi_async_execute_callback ctxt->status=%{public}d", actx->ctx->status);
            if (actx->execute && actx->ctx->status == napi_ok) {
                actx->execute();
            }
        },
        [](napi_env env, napi_status status, void* data) {
            CHECK_RETURN_VOID(data != nullptr, "AsyncWork napi_async_complete_callback nullptr");
            auto actx = static_cast<WorkContext*>(data);
            if (env == nullptr || !actx->environment->alive.load()) {
                // An absent callback env is also a teardown signal. A hook
                // token that has not fired remains environment-owned, without
                // referencing this context after it is deleted.
                actx->environment->alive.store(false);
                actx->env = nullptr;
                actx->ctx->env = nullptr;
                delete actx;
                return;
            }
            LOG_DEBUG("AsyncWork napi_async_complete_callback status = %{public}d, ctxt->status = %{public}d",
                status, actx->ctx->status);
            if ((status != napi_ok) && (actx->ctx->status == napi_ok)) {
                actx->ctx->status = status;
                SetErrorValue(actx->ctx->error, INTERNAL_ERROR, "Calendar async work cancelled or failed");
            }
            napi_value output = nullptr;
            if ((actx->complete) && (status == napi_ok) && (actx->ctx->status == napi_ok)) {
                actx->complete(output);
            }
            if (actx->environment->alive.load()) {
                GenerateOutput(*actx, output);
            }
            delete actx;
            actx = nullptr;
        },
        reinterpret_cast<void*>(aCtx), &aCtx->work);
    if (status != napi_ok) {
        return fail(status, "Cannot create calendar async work");
    }
    status = napi_queue_async_work(env, aCtx->work);
    if (status != napi_ok) {
        return fail(status, "Cannot queue calendar async work");
    }
    return promise;
}

void NapiQueue::GenerateOutput(AsyncContext &ctx, napi_value output)
{
    if (ctx.ctx->env == nullptr) {
        return;
    }
    napi_value result[RESULT_ALL] = { nullptr };
    napi_status status = napi_ok;
    if (ctx.ctx->status == napi_ok) {
        status = napi_get_undefined(ctx.env, &result[RESULT_ERROR]);
        if (output == nullptr) {
            if (status == napi_ok) {
                status = napi_get_undefined(ctx.env, &output);
            }
        }
        result[RESULT_DATA] = output;
    } else {
        bool pending = false;
        status = napi_is_exception_pending(ctx.env, &pending);
        if (status == napi_ok && pending) {
            status = napi_get_and_clear_last_exception(ctx.env, &result[RESULT_ERROR]);
        } else if (status == napi_ok) {
            napi_value message = nullptr;
            napi_value code = nullptr;
            status = napi_create_string_utf8(ctx.env, ctx.ctx->error.message.c_str(), NAPI_AUTO_LENGTH, &message);
            if (status == napi_ok) {
                status = napi_create_int32(ctx.env,
                    ctx.ctx->error.code == NO_ERROR ? INTERNAL_ERROR : ctx.ctx->error.code, &code);
            }
            if (status == napi_ok) {
                // create_error's optional code is a string. BusinessError
                // requires a numeric code property instead.
                status = napi_create_error(ctx.env, nullptr, message, &result[RESULT_ERROR]);
            }
            if (status == napi_ok) {
                status = napi_set_named_property(ctx.env, result[RESULT_ERROR], "code", code);
            }
        }
        if (status == napi_ok) {
            status = napi_get_undefined(ctx.env, &result[RESULT_DATA]);
        }
    }
    if (status != napi_ok) {
        ThrowAsyncError(ctx.env, "Cannot construct calendar async result");
        return;
    }
    if (ctx.deferred != nullptr) {
        if (ctx.ctx->status == napi_ok) {
            LOG_DEBUG("GenerateOutput deferred promise resolved");
            status = napi_resolve_deferred(ctx.env, ctx.deferred, result[RESULT_DATA]);
        } else {
            LOG_DEBUG("GenerateOutput deferred promise rejected");
            status = napi_reject_deferred(ctx.env, ctx.deferred, result[RESULT_ERROR]);
        }
    } else {
        napi_value callback = nullptr;
        status = napi_get_reference_value(ctx.env, ctx.ctx->callbackRef, &callback);
        napi_value receiver = nullptr;
        if (status == napi_ok) {
            status = napi_get_undefined(ctx.env, &receiver);
        }
        if (status == napi_ok) {
            napi_value callbackResult = nullptr;
            LOG_DEBUG("GenerateOutput call callback function");
            status = napi_call_function(ctx.env, receiver, callback, RESULT_ALL, result, &callbackResult);
        }
    }
    if (status != napi_ok && ctx.ctx->env != nullptr) {
        ThrowAsyncError(ctx.env, "Cannot deliver calendar async result");
    }
}
} // namespace OHOS::Calendar
