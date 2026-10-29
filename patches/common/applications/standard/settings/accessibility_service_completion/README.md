# Accessibility notification action completion

Fixed project: `applications/standard/settings` at
`0aba461c750fda71977c2f5186ca0e756ecfc6ca`.

The real `IgnoreRepeatClickExtService` is already declared by the source-built
Settings HAP. Its notification handler previously treated asynchronous
`accessibility.config.*.set(false)` calls as synchronous: it changed its local
cache and reported success before the service replied, while an asynchronous
rejection escaped its `try/catch`.

This component serializes delivered requests, awaits the actual config change,
and then changes the local cache and emits its behavior event. Synchronous
throws and Promise rejections are logged as failures without poisoning the
queue. The four original action strings, the two real config operations,
notification preferences and permission guards are retained. No substitute
provider or success fallback is added.

The second patch attaches queued requests to the service lifetime. Destruction
invalidates actions that have not begun and prevents old async completions from
updating the local cache or publishing a success event. Recreating the same
service object uses a new generation; its requests remain serialized behind any
already accepted operation. A native config operation that was already started
can still complete; this is not a cancellation or rollback of that operation.

The two preference branches use `SettingsDataUtils.setSecureValue(): void`,
which calls `setSettingsData(): boolean` and the actual `Settings.setValueSync`.
They do not launch an untracked Promise. Their helper already logs and absorbs a
false write result; this component makes no new success claim for those writes.

Service lifetime remains managed by the existing framework. In the fixed native
`ServiceExtensionContext::TerminateAbility`, termination passes the token and
`-1` without a conditional start ID. An unconditional asynchronous
`terminateSelf()` would race with a newly delivered request. This patch therefore
does not introduce automatic termination. Verifying extension destruction and
choosing a safe idle-stop strategy remain integration work, separate from the
config Promise and stale-lifetime bugs fixed here. Real config/cache listener
resynchronization after an accepted operation completes across destruction still
requires packaged-image validation.

The complete original file is pinned by SHA256; unknown source states and
symlinks fail before application. Apply this component during Settings source
preparation before its HAP build. The existing root recipe already applies this
component; this lifetime update adds no shared script change.

Host check:

```sh
LC_ALL=C LC_CTYPE=C LANG=C python3 ci/capability-audit/test_batch_apps_accessibility_service.py
```

The check executes the complete patched class after erasing imports/type syntax,
with explicit host doubles. It reproduces premature success on the original
file, then checks delayed success, synchronous/asynchronous failure, queued and
reentrant requests, notification actions and unknown actions. Every case rejects
an unexpected termination call, including a second request delivered from inside
the first backend operation. These are host regressions. Official SDK/HAP
compilation and new-package notification action, state, permission and extension
lifecycle checks remain required before any capability ledger entry can close.

The exact previous patched state can be upgraded once, before the root agent
reprepares its existing source snapshot:

```sh
python3 ci/capability-audit/batch_apps_upgrade_settings_lifetimes.py --source-root /path/to/source
```

The tool checks both complete Settings components before replacing any source
file and rejects unknown edits, partial versions and symlinks. Clean source
preparation uses the normal two-patch stack after its existing prerequisites;
the upgrade command is not needed for a fresh checkout.
