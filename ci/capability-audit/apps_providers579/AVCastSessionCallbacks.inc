    static const std::string callBackName = "NapiAVCastPickerHelper::SelectAVPicker";
    auto isValid = napiAVCastPickerHelper->isValid_;
    auto generationToken = napiAVCastPickerHelper->pickerGeneration_;
    const uint64_t generation = generationToken->fetch_add(1) + 1;
    auto pickerState = std::make_shared<std::atomic<int32_t>>(-1);
    auto notifyState = [napiAVCastPickerHelper, isValid, generationToken, generation, pickerState](int32_t state) {
        CHECK_AND_RETURN_LOG(isValid && *isValid, "NapiAVCastPickerHelper is destroyed");
        CHECK_AND_RETURN_LOG(generationToken->load() == generation, "Ignoring an older picker session");
        int32_t previous = pickerState->load();
        // Each modal session can appear once and disappear once. A terminal
        // close cannot be reopened by a delayed remote-ready/provider callback.
        while (previous != state && previous != static_cast<int32_t>(STATE_DISAPPEARING)) {
            if (pickerState->compare_exchange_weak(previous, state)) {
                CHECK_AND_RETURN_LOG(isValid && *isValid, "NapiAVCastPickerHelper is destroyed");
                CHECK_AND_RETURN_LOG(generationToken->load() == generation, "Ignoring an older picker session");
                napiAVCastPickerHelper->HandleEvent(EVENT_PICPKER_STATE_CHANGE, callBackName, state, generation);
                return;
            }
        }
    };
    return {
        .onRelease = ([callback, notifyState](auto arg) {
            // The callback still owns and closes this actual modal session,
            // even when its generation no longer owns the helper's events.
            callback->OnRelease(arg);
            notifyState(STATE_DISAPPEARING);
        }),
        .onResult = ([callback](auto arg1, auto arg2) { callback->OnResult(arg1, arg2); }),
        .onReceive = ([callback, notifyState](auto arg) {
            callback->OnReceive(arg);
            AAFwk::Want stateWant;
            stateWant.SetParams(arg);
            const int32_t state = stateWant.GetIntParam("state", -1);
            if (state == static_cast<int32_t>(STATE_APPEARING) ||
                state == static_cast<int32_t>(STATE_DISAPPEARING)) {
                notifyState(state);
            }
        }),
        .onError = ([callback](auto arg1, auto arg2, auto arg3) { callback->OnError(arg1, arg2, arg3); }),
        .onRemoteReady = ([callback](auto arg) {
            // Proxy readiness does not prove that the provider's panel is
            // visible. Its actual sendData({state: 0}) owns APPEARING.
            callback->OnRemoteReady(arg);
        }),
        .onDestroy = ([callback, notifyState]() {
            callback->OnDestroy();
            notifyState(STATE_DISAPPEARING);
        }),
    };