# Actual mouse pressed-button state

The pinned OHOS converter starts its mask at zero, then ANDs every pressed
left/right/middle bit into it. This always reports zero, losing independently
held-button state used by ArkUI's mouse-to-touch dispatch and pointer identity.

Combine the existing three bits with OR. Preserve the MMI device/source/tool,
button/action/coordinate conversion, extended-button array, ABI, recognizers,
permissions and dispatch policy. No client-supplied or injected state is used.
The exact component is applied before GN for both profiles and all three ABIs.

Host tests exercise the actual patched block across all eight combinations,
held movement, partial release and complete release, and demonstrate the old
zero-mask failure. Full product TU compilation and newly packaged physical
input regression remain separate required evidence; this change alone does not
prove the SpringLoading backend or close its first-package gate.
