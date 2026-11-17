# Fixed Contacts source packaging candidate

`applications/standard/contacts` is pinned to
`65de33df8d6d7aaa5797a5625ed0e5938e5cb050`. This component changes only
`BUILD.gn` and the selected product's IDE signing association in
`build-profile.json5`. Compile SDK 26, target/compatible SDK 23, all seven
modules, every manifest, the actual picker implementation and the original
profile remain intact. GN uses the existing `prebuilt_hap` part and normal
`ohos_app` signing; no new bundle component is necessary.

Target: `//applications/standard/contacts:contacts_hap`. It compiles `entry`
to `Contacts.hap`, intended for `app/com.ohos.contacts`. There is one actual
entry module with `default` and `tablet` device declarations, not separate
phone and 2in1 source implementations. Shared HAP selection, precise signing
identity and preinstall authorization remain the parent integration task.

The existing `ContactUiExtentionAbility` is `sys/commonUI`, exported with no
extension entry permission, and loads actual picker pages. It preserves the
local `common`, `account`, `call`, `contact`, `dialpad`, `phonenumber` HAR
dependency graph and the external `com.ohos.security.pickersheet` /
`pickersheetlibrary` HSP dependency. This component does not remove that HSP
to make an SDK build pass. The original root Hypium 1.0.16 dependency remains;
the parent must prepare a fixed verified cache if needed. No downloads run here.

The real presenter sends selected contact data and 100-contact batches, then
terminates with an ability result; the pages contain cancel and default-selection
return paths. These are source observations, not runtime proof. Existing session
cleanup, timer/display-listener lifetime and simultaneous sessions need a separate
business fix and actual regression. All public picker overloads must be checked
against the final product NAPI implementation, including empty/cancel/error data,
one/many selections, filter limits, permission boundaries and caller/provider exit.

Run `apply.sh --source-root ROOT` only on a private source checkout. The exact
guard rejects drift, partial states and redirected inputs before mutation; repeat
applications verify the complete final metadata. Host tests use compressed fixed
inputs and do not compile or execute a HAP. API26 full system SDK compilation,
OS signing, installation and a newly packaged representative image are still
required. No capability requirement is closed by this component.
