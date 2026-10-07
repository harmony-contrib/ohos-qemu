# CertificateManager empty-list results

Pinned project: `57bd41128a07c5289987cf98e04dfc66421029a6`.

The original NAPI helper treats a successful empty list as a failed conversion,
causing `getAllAppPrivateCertificates()` to resolve `undefined` instead of its
declared `CMResult`. An empty count now produces a real empty array, preserving
the existing result object. Nonzero counts with null storage still fail; service
errors, permission checks, storage scopes and populated entries are unchanged.

The same empty-count rule is applied to the three existing certificate/credential
array converters. Their two list owners are freed even when their child storage
is null, including empty results and partially allocated failure paths. Null
owners remain no-ops; the existing child helpers handle null storage.

Apply with `bash apply.sh --source-root OPENHARMONY_ROOT`. Host NAPI/memory mocks
and product-object compilation are not guest proof. New-package acceptance must
exercise promise/callback results, repeated empty queries, populated results,
invalid arguments and ordinary-application privilege denial without granting
privileges to ordinary applications or relaxing the image access policy. The
separate system test HAP requests exactly the two documented certificate
permissions; its signed profile and actual installed identity must both match.

The applicator validates the whole original/final file hashes before touching
source. Unknown/partial changes fail without overwriting them; stale per-patch
marker files do not authorize a skip.

`ci/capability-audit/run_certificate_probe.py` runs both roles on the same
enclosing fresh package VM. It imports only a nonce-bearing test PKCS12 and
removes only the URI returned by its own import, never all credentials. Both
roles and complete raw observations are mandatory for the original finding's
closure and for the package gate. Host profile fixtures or signed HAPs alone
cannot satisfy it.
