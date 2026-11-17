# Native FA-card event target

The fixed native media service sends its existing `assetChangeUris` and
`assetChangeTypes` arrays to a commercial Photos bundle absent from OpenHarmony.
This patch changes only the two target bundle names to the real fixed-release
`com.ohos.photos` source `FACardServiceAbility`. The service name, arrays,
account selection, extension type, caller identity and permissions are unchanged.

The separate Photos source component builds that actual provider and repairs
its inverted first-store initialization guard. Both components must precede
traversal. This patch does not provide the separate commercial cloud-sync
authority, promise event delivery, or pass guest/form acceptance by itself.

Run `python3 -m unittest discover -s ci/capability-audit -p test_photos_facard_target.py`.
Exact whole-file validation rejects partial/unknown edits and symlinks; the
original native change protocol remains byte-for-byte unchanged outside the two
bundle literals. Actual new-package asset-change/form-refresh regressions are
still required.
