void NapiAVCastPickerHelper::HandleEvent(int32_t event, std::string callBackName, const T& param, uint64_t generation)
{
    std::lock_guard<std::mutex> lockGuard(lock_);
    const auto generationToken = pickerGeneration_;
    CHECK_AND_RETURN_LOG(generationToken->load() == generation, "Ignoring an older picker event");
    if (callbacks_[event].empty()) {
        SLOGE("pickerNotRegister:%{public}d", event);
        return;
    }
    for (auto ref = callbacks_[event].begin(); ref != callbacks_[event].end(); ++ref) {
        const napi_ref callbackRef = *ref;
        asyncCallback_->CallWithFunc(callbackRef, isValid_,
            [this, callbackRef, event, generationToken, generation]() {
                std::lock_guard<std::mutex> lockGuard(lock_);
                if (generationToken->load() != generation) {
                    SLOGI("Ignoring an older queued picker event");
                    return false;
                }
                if (callbacks_[event].empty()) {
                    SLOGE("checkCallbackValid with empty list for event=%{public}d", event);
                    return false;
                }
                bool hasFunc = false;
                for (auto it = callbacks_[event].begin(); it != callbacks_[event].end(); ++it) {
                    hasFunc = (callbackRef == *it ? true : hasFunc);
                }
                if (!hasFunc) {
                    SLOGE("checkCallbackValid res false for event=%{public}d", event);
                }
                return hasFunc;
            }, callBackName,
            [param](napi_env env, int& argc, napi_value* argv) {
                argc = NapiUtils::ARGC_ONE;
                NapiUtils::SetValue(env, param, *argv);
            });
    }
}
