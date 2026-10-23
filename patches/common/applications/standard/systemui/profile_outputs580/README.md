Profile-isolated actual SystemUI publication

This exact one-file successor retains the external systemui_hap group used by all seven source HAP definitions. It creates one mutually exclusive inner ohos_app target: systemui_phone_sources for phone, or systemui_pc_sources for 2in1. Its target name owns the unsigned-list/hap-list metadata, signed HAP directory and install module metadata. The previous systemui_hap directory is preserved.

The fixed source-to-output maps contain the entry context observed in actual feature HAP basenames. Phone selects seven exact inputs; 2in1 selects eight. strict_hap_list=true requires the separately reviewed explicit opt-in build-framework change; all other applications retain legacy signing behavior. The source_provider guard retains its original patch and complete four-file baseline, proving this whole BUILD inverse before calling that original guard on a temporary four-file ancestor view.

Parent must apply the strict-signing component and this successor in the existing serialized build, and bind the package verifier to the profile target directory. The complete HAP graph and independent ScreenLock remain unchanged. No old output is deleted and no verifier output set is relaxed. The renamed inner target also requires checking the actual Hvigor label policy. This candidate has not been executed, compiled, packaged or QEMU-validated.
