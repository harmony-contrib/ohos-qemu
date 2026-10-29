# Preserve GN native-library identity in the NumberIdentity HAP

The official `ohos_app` system_lib_deps path copies GN's `number_identity` DSO into the project's native-library directory before Hvigor. This exact one-file component adds only `buildOption.nativeLib.debugSymbol.strip: false` in entry/build-profile.json5 so this project does not strip the same GN-produced DSO again. Existing obfuscation, target and API settings remain byte-for-byte unchanged outside the inserted block. No global SDK setting changes.

This separate component avoids introducing mixed before/after vectors into `native_manifest`: pristine and old-invalid module JSON5 states retain their own exact contract. Apply all required components before building the HAP. Actual Hvigor schema acceptance, exact final HAP member bytes, ABI/ELF/dependencies and installed nativeLibraryFileNames/path remain root execution gates; this source option alone is not proof of identity or successful native loading.
