SDK467 developer-tool repair

These exact reviewed patches preserve the original SDK-batch375 source and document the private SDK-batch467 successor used for the next real 14-role build. They are committed here so all repair code remains reviewable on the single development branch. The actual producer and complete fixed-source manifest are pinned in ../preflight463-and-repair469.json. These patch records do not execute a build or turn the failed463 receipt into success. The SDK source-manifest path changes are explicit environment DATA; do not apply them to an unrelated checkout.

The real producer remains run_sdk_batch26.py with explicit --execute, actual clean commit and a fresh output. Both Linux producers retain original ownership, mounts, source freeze, child/worker status and removal checks. CID observations now preserve each actual raw read. Original463 did not record its failing CID bytes; the precise partial state was not observed.
