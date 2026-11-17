# Actual qrcode archive CFI metadata

Root's actual490 export proves qrcodegen.a has seven real C++ object members. They include function-pointer hooks, so lack of virtual methods is not a metadata exemption. Only the standard OHOS qrcodegen target gains the official cfi/cfi_cross_dso sanitize scope. Source list, flags, exception policy, public config and Lite/host behavior are retained. Existing sanitizer machinery controls host/ASan/TSan policy.

The actual archive consumers are libace_compatible, libace_compatible_components and libarkui_qrcode. The native coverage guard rejects additional consumers until their complete metadata boundary is reviewed. The exact BUILD.gn paired-state verifier/apply uses the unchanged common helper. Target and runtime proof remain pending.
