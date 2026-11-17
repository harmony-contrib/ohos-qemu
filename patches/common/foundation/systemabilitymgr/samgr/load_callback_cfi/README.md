# load_callback_cfi

Matches `OnLoadSystemAbilitySuccessInner` by adding `__attribute__((no_sanitize("cfi")))` to `OnLoadSystemAbilityFailInner`, `OnLoadSystemAbilityFailWithCodeInner`, and `OnLoadSACompleteForRemoteInner` so cross-DSO `SystemAbilityLoadCallbackStub` subclasses (such as `selection_service`) do not fault with `SIGILL` (`__cfi_slowpath_diag`).
