# Caption secure SettingsData permission

Build25 QEMU started AiCaptionServiceExtAbility, but its first USER_PROPERTY
state write failed with Permission denied. The actual DataShare log names
ohos.permission.MANAGE_SECURE_SETTINGS; the application requested only
MANAGE_SETTINGS, SYSTEM_FLOAT_WINDOW and WRITE_ACCESSIBILITY_CONFIG. The
platform defines the missing permission as system_grant/system_basic with
provisionEnable=true.

The module now requests that permission and the release profile includes its
exact ACL. The existing system_basic APL, signing identity, extension caller
permission and real playback-capture consent remain unchanged. The service
continues to use the same USER_PROPERTY API and rejects a failed write.

Fresh0001 creates the four-permission source. Existing0002–0005 remain intact;
the same staged transaction applies the selected historical patch, then new
0006 to reach v6. A complete v5 state applies only0006. All23 source files must
match one complete known vector; verification never migrates. The profile
helper authenticates either the complete current four-ACL profile or the exact
prior three-ACL profile with the same OS issuer and all other values equal.
Only the latter is regenerated with the one additional ACL, preserving unknown
or concurrent signed bytes. No user-grant row is added. New QEMU behavior is
still pending.

## Earlier SDK26 component member correction

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
