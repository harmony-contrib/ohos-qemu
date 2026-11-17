# Real API26 compatibility

Actual product SDK attempt 03 showed that its real device definitions contain
no phone SysCap set; use its existing default profile instead, as for the other
phone source applications. Do not synthesize SDK device definitions or disable
SysCap checks. The tablet profile remains tablet. Both original AbilityStage
imports use the removed @ohos.application namespace; migrate to the real
@ohos.app.ability.AbilityStage declaration. Bundle, extension, feature module and
permission/profile policy stay unchanged. Apply after module_names. Actual
complete SDK build and BMS/new package runtime acceptance remain required.
