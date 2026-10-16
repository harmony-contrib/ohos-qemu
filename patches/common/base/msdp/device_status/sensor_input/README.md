# Require actual MSDP sensor input and validate event boundaries

This component pins `base/msdp/device_status` at
`96335211bea5ca348325d55746e14e102208354f` and changes the five exact targets in
`manifest.json`. It adds `device_status_allow_mock_fallback` (default true, to
preserve other products). Main must set it false on QEMU. Real SensorHDI and
sensor-algorithm initialization still run normally; when neither backend
supports a requested type, initialization returns an error instead of using
MockHandle's JSON events.

The real algorithm SensorAgent boundary now rejects non-accelerometer events,
null/incorrect-length payloads, nonfinite and out-of-range samples. It copies
three floats into aligned storage and bounds the pending sample queue to 256.
SetBatch failure unsubscribes the partial registration; Activate failure attempts
deactivate and unsubscribe. Rollback errors are logged and the original request
still fails. This adds no client, model, event generator or successful empty
stream, and does not expand the advertised set of supported types.

```sh
bash patches/common/base/msdp/device_status/sensor_input/apply.sh --source-root /path/to/ohos
LC_ALL=C LC_CTYPE=C LANG=C python3 ci/capability-audit/batch_system_msdp_input.py --output /tmp/unique-msdp-host-evidence
```

The strict installer has the same fixed revision/hash/symlink/mixed-state and
write rollback behavior as the QEMU sensor component. Host regression extracts
the actual fixed PushData, event callback, RegisterCallbackSensor and InitMsdpImpl
functions, reproducing seven original failures and testing eleven repaired paths
plus default-product fallback behavior. SensorAgent fault injection and a
semaphore count shim are explicitly supplemental: they do not execute the real
SensorService, algorithm worker, semaphore lifecycle, service IPC or public APIs.

Main owns product features and client packaging, official TU/link validation and
the first newly packaged ARM64 phone behavior gate. Input must flow through the
real Sensor HDI and SensorAgent into the existing algorithm sources, with
independent external challenge observations. Check all three existing algorithms
concurrently, subscribe/unsubscribe order, repeated enable/disable, process
destruction/restart and permissions. Existing worker/semaphore teardown and
shared sensor user/reference handling need that runtime evidence; host queue and
rollback tests do not close those lifecycle gaps or all declared MSDP/multimodal
capabilities.
