# Serial attachment metadata policy

Fixed selinux_adapter cfc1d5b31a7438dbc87763f9222f00337221cf21.
The guard checks that revision and the entire original serial_service.te SHA:
8dbe5797286ce668099cdb766312aa540902eb42bafa9986197b9fe7a5906321.
It accepts only original bytes or the exact unique transformation.

Add only serial_service -> tty_device:chr_file getattr for the real devnode
stat needed by attachment lifetime checks. Existing read/write/open/lock/ioctl
and ioctl ranges are unchanged. No HAP/root/domain grants, new device labels,
console access, signer changes or user-authorization bypass is introduced.

Root and sepolicy AGENTS were read completely. This system subject stays in
the existing feature's system rule; framework/global attributes are unchanged.
The documented workflow still requires actual policy compilation, new guest
enforcing mode, observed USB/ACM labels, stat behavior and relevant AVC checks.
Source reasoning and host guards are not that device verification.

Apply only on an owned writable candidate. Production inputs stay read-only.
The frozen r18 did not contain this component; subsequent full GN, policy and
Serial component builds must record the newly patched source manifest.
