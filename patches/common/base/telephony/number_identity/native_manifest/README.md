# Schema-valid NumberIdentity manifest

This exact component reverses the three `extensionAbilities[].srcLanguage: "c++"` additions rejected by real Hvigor PreBuild 00303038. The final file is byte-identical to the official NumberIdentity 50e1330 JSON5; all permission, URI, export, Stage, device and ability declarations are preserved.

`FILES.before` is the already-installed invalid manifest (42ff5388…), and `FILES.after` is the official valid manifest (9b0a2d76…). Thus old prepared source receives the inverse patch; pristine official source is already final and requires no write. Any other whole-file content is rejected. Remove the previous numbered patch when integrating this complete successor directory. `source_states.json` and patch bytes are cross-checked by the verifier before the shared exact helper is used.

This component does not route native extensions by itself. Pair it with `number_identity_loader` and `native_package_identity`; root owns source/build/image combined verification. No compiler, packaged image, BMS, creator callback, local CRUD or aggregate provider pass is asserted here.
