# Explicit strict HAP list

The pinned OpenHarmony build signer uses `hap_list` to rename matching inputs,
but still signs unmatched inputs. SystemUI therefore publishes modules for other
profiles alongside its selected profile. This component adds an explicit
`strict_hap_list = true` opt-in through `ohos_app`, `app_sign` and
`app_sign.py --strict-hap-list`. The existing signer and every signing parameter
are retained. The original non-opt-in main branch remains byte-for-byte intact;
only the CLI flag and the early opt-in dispatch are added around it.

Strict mode requires an explicit nonempty `hap_list` with `do_filter: true`.
Each `source:output` pair has a unique safe extensionless source and output
name. The input key is always `hap_name + "-" + basename(unsigned_path)` with
its `.hap`/`.hsp` extension removed before matching. All selected keys must
have exactly one nonempty regular unsigned input; duplicate paths, selected
aliases, missing keys and conflicting names fail before the first signer call.
Unselected profile inputs are never signed or published. The one-input shortcut
continues to belong to the original default branch.

The output directory may contain GN metadata such as `hap_list.json` and
`unsigned_hap_path_list.json`. Strict mode preserves those files. Existing HAP
or HSP entries must be a regular-file subset of the exact expected collection;
unknown outputs are rejected without deletion. A fresh profile-specific target
directory is required when an old mixed collection remains. All selected HAPs
are signed into a private temporary directory beside the target directory before
any output publication. After the complete staged collection succeeds and the
original directory state is rechecked, only the expected HAP/HSP names are
replaced. A complete prior expected collection or a subset can be rebuilt.

Publication errors raise failure and roll back only files still identified as
owned by this publication. External changes are preserved; a rollback conflict
retains the private recovery directory and reports its path. No success receipt
is written. The parent owns exclusive build access; this file-by-file publication
is not a filesystem transaction for concurrent consumers. An abrupt process kill
can interrupt publication and requires the parent to treat the attempt as failed.

The component pins build project HEAD
`5c0623072ed9c2ee93ab909a7a01f428fee95082`, three complete before/after hashes,
and original modes (GN 0644, signer 0755). `verify_source.py` delegates the
whole-vector and available-project-HEAD check to `exact_source_states`;
unknown/partial states fail before the shared exact applier changes source.
Scratch trees without Git metadata follow that existing helper contract.
`apply.sh` reuses `patches/lib/apply_exact_component.py`. The patch changes only
`build/ohos/app/app.gni`, `build/ohos/app/app_internal.gni` and
`build/scripts/app_sign.py`; before/ retains the captured whole original files.

This is a source-only candidate. It has not been executed or adopted into active
build wiring. SystemUI's exact profile lists and fresh target name, shared
launcher wiring, signing, packaging and newly packaged runtime validation remain
with the parent and their assigned agents. Compile/Hvigor policy and HAP graph
selection are outside this component.
