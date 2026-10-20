Independent QEMU-only reference AT PTY access source candidate. The parent must
select it only in the QEMU hook alongside ril_reference_transport. No policy
compiler, checker, parser or image/runtime operation was run by this child.

Actual sole-CID preimage: riladapter_host.te SHA256
170ee019eb9e35b6b803997884dcd7531d860c7ef820104abc0649361d1dfa8c.
The parent exported the complete 1775-file policy tree and actual project HEAD
cfc1d5b31a7438dbc87763f9222f00337221cf21. This component guards the whole actual
file, independently of the RTT and RIL HCS/parameter components.

Source rationale: riladapter_host belongs only to hdfdomain/domain (adapter
public/type.te:46-47). Shared hdfdomain rules grant executable/library access;
shared domain rules grant only fs_attr filesystem/dir getattr here. Neither
grants the PTY read/open/write or dev_pts_file directory traversal needed by
the actual configured symlink -> owned slave. fs_use labels devpts nodes as
devpts; file_contexts labels /dev/pts as dev_pts_file and /dev generally dev_file.

Added scope: riladapter_host may read the configured dev_file symlink, search
the existing dev_pts_file directory, and open/read/write the PTY slave. The
actual vendor_adapter.c DEVICE_PATH_DEFAULT is /dev/ttyUSB, so /dev/ttyUSB0
also calls tcgetattr/tcsetattr(TCSANOW); only TCGETS 0x5401 and TCSETS 0x5402
ioctl xperms are granted. No PTMX creation, setattr, relabel, TIOCSTI, new domain,
HAP permission or global mode change is added. Existing TIOCSTI neverallow and
global enforcing remain intact. Radio UID with no DAC override still requires
the exact owned slave's radio:radio mode 0600 from the original root fixture.

The new representative image must prove actual enforcing mode, actual labels,
real radio UID/domain, exact PTY inode and reader fd, actual termios/open/read
and ModemInit traffic, complete public callback chain, and final cleanup. Keep
raw AVC/native logs even on success. A policy source patch is not proof that
the packaged policy contains it or the genuine public chain works.
