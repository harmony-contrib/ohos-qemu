# Product SDK module schema

The actual product API26 SDK rejected the obsolete module buildOption.arkEnable
property before either renderer was compiled. Remove that old switch in both
phone and pad module profiles; ordinary ArkTS checking and compilation remain
enabled by the current standard tasks. All targets, API identity, manifests,
permissions and renderer source are unchanged. First actual SDK attempt evidence
is preserved; official complete module compilation still must pass.
