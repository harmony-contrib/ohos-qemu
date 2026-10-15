# Scene plugin loading and initialization

Fixed `graphic_3d @ b2d7af910f2d4b941697630020b0940245d5bd99`
used the engine DSO handle as proof that scene plugins had loaded. A partial
symbol-load failure retained this handle; a failed plugin registration or an
earlier engine-only load caused later calls to skip the real registry. Loading
a requested plugin UID also returned true solely because the engine was open.

The patch tracks successful default-plugin loading separately, clears the DSO
and function pointers on incomplete exports, retries failed plugin registration,
and actually sends each requested UID to the existing real registry. Registry
creation is safe to retry: the fixed engine implementation uses `std::call_once`.

The engine initializer now reports queue/scheduling/factory/render/resource/
application/scene-manager failure. It initializes and rolls back partial engine
objects on `ENGINE_THREAD`, publishes the scene render context only after the
real application context and scene manager exist, and records success after
the initial frame. Deinitialization clears success. The JS SceneManager failure
branch runs before acquiring a queue reference, avoiding a retained JS queue on
each failed `Scene.load` attempt.

Apply with `bash apply.sh --source-root /path/to/openharmony`. The exact revision
and both complete source hashes are checked before mutation and after applying;
mixed state, symlinks and unrelated changes are refused. Parent-owned product
installers must wire in this component before a new representative package.

```sh
LC_ALL=C LC_CTYPE=C LANG=C python3 ci/capability-audit/batch_system_graphics3d_startup.py \
  --output /tmp/ohos-graphics3d-startup-evidence
```

The host regression extracts the actual loader and engine initializer functions
from the fixed source. It uses real `dlopen`/`dlsym` against a test-only DSO and ABI
shims for initialization failure injection, with ASan/UBSan. These DSOs do not
enter a product image and do not provide a fake scene or renderer. The NAPI
queue branch has a fixed-source ordering check only. Official GN compilation,
real engine/plugin linking, fresh packaged `Scene.load`/render/destroy/recreate,
invalid asset rejection and failure/retry remain mandatory. These host results
close no capability requirement and do not establish the original guest failure's
complete root cause.
