# Image-generator custom-model callbacks

The fixed OpenHarmony 7.0 ACE project initializes no result array before
`push`, drops partial errors without an optional BusinessError, and can accept
duplicate completion or late callbacks from a cancelled session. This
component repairs the real checked-in JS and corresponding ETS implementation
and includes the imported JS in the normal Rollup action's inputs.

`apply.sh --source-root <checkout>` checks the pinned project and every complete
file before any patching. Unknown, partially patched and symlinked inputs are
rejected; the complete stack is idempotent. The standard Docker recipe invokes
this component before source preparation/traversal.

The host regression executes the whole original and patched JS and reproduces
the original failure. It covers synchronous callbacks, ready/result ordering,
partial errors, completion without image data, duplicate completion,
cancellation, stale sessions and independent clients. Run:

```sh
python3 -m unittest discover -s ci/capability-audit -p test_image_model_callbacks.py
```

This is **not** a default AI model implementation or restoration of the missing
public dialog/nodegraph exports. Host tests are not guest/UI acceptance. The
newly packaged representative artifact and remaining architectures must still
pass the original behavior/closure gates before six-package delivery.
