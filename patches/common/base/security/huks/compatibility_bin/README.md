# Packaged HUKS compatibility helper

Include the existing helper in the image because the existing init profile invokes
it. Migrate real legacy files by descriptor-relative traversal, reject symbolic
and hard links and nonregular files, bound recursion, preserve payloads and the
keystore root, and propagate real filesystem failures. Descendants keep the
existing service UID/GID 3510 and directory/file modes 0700/0600.

Emit a bounded completion record without key data to stdout and /dev/kmsg: init's
asynchronous exec closes standard output. The init job invokes the helper before
invoking service start, but does not guarantee migration completion precedes
service startup. No extra application permission or service privilege is added.

The packaged acceptance suite independently verifies the actual image, boot-time
helper completion, normal service identity, an exclusive real migration fixture,
payload preservation and fixture cleanup. This narrow proof does not establish
legacy encrypted-key conversion, TEE or OEM attestation.
