# Read-only jsoncpp source during generation

Applies only to fixed 7.0 component `ea808a0b6318fbe1fee1d3acb8cb0fa36d4748d0`
and the pinned `jsoncpp-1.9.6.tar.gz` archive. Run `apply.sh --source-root ROOT`
before traversal/GN. Unknown revisions, source edits and symlinks fail closed.

The original installer extracted into the source directory, recursively removed
that directory and swallowed extraction/copy errors. This breaks read-only
source builds and can race between products. The replacement only reads source,
verifies archive identity and safe entries, stages under the actual generation
directory, verifies every GN-declared output plus the public header, and then
publishes the complete generated tree. Failed tar/validation/publication exits
nonzero. Existing valid generated output survives failed extraction; successful
generation replaces only `GEN/jsoncpp-1.9.6`, not sibling outputs.

The independent second patch handles GN-created empty output-directory
skeletons. It accepts only directory-only ancestors of known GN outputs;
partial files, unknown directories, links and special entries still fail
without overwriting them. Extraction/publication failure preserves the
skeleton or prior valid tree. The component entry validates the whole fixed
installer against exact patch-prefix hashes, so repeated application works
even though the two numbered diffs overlap.

This changes build generation, not jsoncpp source algorithms, permissions or
public interfaces. Host/unit and isolated dependency builds are not QEMU runtime
acceptance.
