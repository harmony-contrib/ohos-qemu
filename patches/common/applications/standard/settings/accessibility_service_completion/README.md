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
config Promise bug fixed here.

The complete original file is pinned by SHA256; unknown source states and
symlinks fail before application. Apply this component during Settings source
preparation before its HAP build. Public recipe wiring is a main-agent
integration request and is absent from this isolated group.

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
