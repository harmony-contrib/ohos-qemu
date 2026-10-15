template <class Context>
napi_value InterfaceWithoutManager(napi_env env, napi_callback_info info, const std::string &asyncWorkName,
                                   bool (*Work)(napi_env, napi_value, Context *), AsyncWorkExecutor executor,
                                   AsyncWorkCallback callback)
{
    static_assert(std::is_base_of<BaseContext, Context>::value);

    napi_value thisVal = nullptr;
    size_t paramsCount = MAX_PARAM_NUM;
    napi_value params[MAX_PARAM_NUM] = {nullptr};
    NAPI_CALL(env, napi_get_cb_info(env, info, &paramsCount, params, &thisVal, nullptr));

    std::shared_ptr<EventManager> manager = nullptr;
    auto context = new Context(env, manager);
    context->ParseParams(params, paramsCount);
    if (context->IsNeedThrowException()) { // only api9 or later need throw exception.
        if (context->GetReleaseVersion() >= API_VERSION_THROW_BUSINESS_EXCEPTION) {
            napi_throw_business_error(env, context->GetErrorCode(), context->GetErrorMessage().c_str());
        } else {
            napi_throw_error(env, std::to_string(context->GetErrorCode()).c_str(), context->GetErrorMessage().c_str());
        }
        delete context;
        context = nullptr;
        return NapiUtils::GetUndefined(env);
    }
    if (Work != nullptr) {
        if (!Work(env, thisVal, context)) {
            NETMANAGER_BASE_LOGE("work failed error code = %{public}d", context->GetErrorCode());
        }
    }

    context->CreateAsyncWork(asyncWorkName, executor, callback);
    if (NapiUtils::GetValueType(env, context->GetCallback()) != napi_function && context->IsNeedPromise()) {
        return context->CreatePromise();
    }
    return NapiUtils::GetUndefined(env);
}
