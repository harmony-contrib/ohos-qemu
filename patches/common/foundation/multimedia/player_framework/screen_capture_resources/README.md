# Fixed screen capture image resources

The fixed player_framework commit3d3b1231db27561e8978652d7ae867c12f488d9a
references eleven resources in services/etc/BUILD.gn, but all eleven paths are
absent in that commit and the actual fixed source. This component adds those
files using pinned official OpenHarmony resource bytes. It does not edit the
player C++ implementation, its GN recipe, permissions or controller protocol.

ASSETS.json records each official repository/revision/path and license. The
destination names are compatibility aliases, rather than a claim to recover
the missing original OEM artwork. In particular capsule_stop.svg,
capsule_stop_live2.svg and light.svg use the same official MMS stop icon;
stop_dark.png and stop.png use the same official sample-camera stop PNG.
The three upstream license texts are retained under LICENSES/.

The eleven FILES have original=None and exact final hashes, so the existing
exact_source_states mechanism rejects any partial, mixed or unknown resource
state. The unchanged apply_exact_component.py stages and applies the complete
numbered binary patch; it does not resolve or fetch assets at build time.

The actual3918-byte services/etc/BUILD.gn is a readonly prerequisite pinned to
611723ea3f2d7217980eeefa76718399740399dbacd2e902e4ac95b4858c3cd7.
It is deliberately not a FILES transition, because adding an already-final GN
file to eleven absent additions would incorrectly create a partial state.
The default apply.sh checks this prerequisite before and after the original
exact applier; validate_source and the actual image guard require it too.
The baseline validate function only checks the eleven resource states so the
original applier's scratch preimage does not require an unmodified GN copy.

verify_screen_capture_resources_image.py exports the actual image's eleven
regular files using the existing unique-inode alias guard, then requires their
bytes to match these exact current source files. This is a source/packaging
guard. It establishes no decoding, UI action, runtime permission, stop/pause/
resume behavior, media capture pass, ledger closure or first-artifact gate.
The actual newly packaged QEMU image must still validate those behaviors.
