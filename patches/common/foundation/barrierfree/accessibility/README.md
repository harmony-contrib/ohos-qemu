# Accessibility manager

This component extends OpenHarmony's installed `ohos-a11yManager` CLI with
generic `ability-enable` and `ability-disable` commands. QEMU accessibility
tests can enable their own installed `AccessibilityExtensionAbility` without
compiling or pushing a privileged helper binary into the guest. Direct HDC
execution is restricted to a root shell; non-root callers continue through the
platform CLI permission framework.

The second patch exports the three ordinary ArkTS 1.1 accessibility enums
declared by the pinned SDK but omitted by the N-API module:
`AccessibilitySourceType`, `FocusMoveResultCode`, and
`OperateVirtualNodeResult`. Each member uses the corresponding platform C++
result code; this does not implement unrelated missing accessibility.config
blinking APIs. The ordinary-app ArkTS export probe also checks every member's
runtime integer value before the three audit entries can be closed.

```bash
bash patches/common/foundation/barrierfree/accessibility/apply.sh \
  --source-root /path/to/openharmony
```

After the test HAP is installed, enable its extension with:

```bash
hdc smode
hdc tconn 127.0.0.1:5555
hdc shell /system/bin/cli_tool/executable/ohos-a11yManager ability-enable \
  --name com.example.app/AccessibilityExtAbility \
  --capabilities 7
```

The mask must be a subset of the extension's declared capabilities. `7`
matches `retrieve`, `touchGuide`, and `gesture`.
