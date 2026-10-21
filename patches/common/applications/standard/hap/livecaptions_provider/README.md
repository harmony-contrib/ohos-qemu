# Caption SDK26 component member source successor

The actual build02 compiler reports 10505001 for Captions.backgroundColor,
which conflicts with the inherited CustomComponent.backgroundColor method.
The local field is now captionBackgroundColor and its one this-reference uses
that name. @LocalStorageLink('backgroundColor'), its default and the rendered
backgroundColor(...) call stay unchanged. This is the only product ETS delta.

Complete23 states remain strict: absent, legacy72, deviceTypes d4, typed Session
b091, native ServiceContext f785/v4, and final v5. Fresh0001 and direct known
migrations0002/0003/0004 contain the same finite page hunk; new0005 migrates only
the complete f78523 vector. Unknown/mixed/extra ETS inputs reject. Final is a
no-op. Actual parent HAP HEAD, per-file ownership snapshots, unchanged-inode
checks, staged full-vector checks, atomic writes and owned rollback all remain.

Session178ec, service3998, module deviceTypes, permission/signer, audio capture
consent, UI/session/worker/queue/conditional native stop/recovery/cleanup,
ASR32/64 source dependencies, helper861e and normal SDK declaration preparation
are unchanged. The 45 warnings and duplicate printing of one actual error are
not treated as additional errors. Models or source preparation do not prove
capability acceptance. Root must batch this with all failures, prepare and
build normally, then validate the newly packaged QEMU behavior.
