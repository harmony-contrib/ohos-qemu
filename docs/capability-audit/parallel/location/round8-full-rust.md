# Complete current communication Rust dylib diagnostic

The final diagnostic passes actual CXX generation, private archive creation,
complete original-platform API solink and all six current Rust modules through
compilation, linking and stripping. Its new communication callback is present
in the linked AArch64 shared ELF. This proves complete Rust compile/link in the
documented private diagnostic; fresh GN, a full product rebuild and runtime are
still untested. All22 assigned requirements remain open.

`compile_communication_rust.py` takes explicit successful complete-TU checkpoints
and never starts Docker or writes source/product out. It validates exact fixed
project HEADs, known whole-component byte states, original platform argv, complete
selected sources, depfiles, actual generated header/source, object hashes and all
reported LLVM split-LTO modules. A failed parent batch can supply an individually
successful object, with its failed batch status retained. An older known prefix
is accepted only when the selected source is current and the actual depfile did
not consume any subsequently changed owned file. Unknown states, obsolete
consumed headers, failed objects and altered flags are rejected.

The fixed real cxxbridge regenerates `wrapper.rs.cc/.h` from the current complete
`wrapper.rs`; their bytes must match the pair consumed by the successful CXX
objects. A private deterministic llvm-ar archive contains exactly the verified
consumer and generated wrapper objects. The full Rust dylib recipe preserves
crate type, edition, target, optimization, extern crates, native libraries and
`no-undefined`. Only private paths/cache, CPU2 LTO parallelism, the current CXX
archive, the actual new AccessToken GN library and the private current API output
replace their documented original counterparts. Six actual `.rs` inputs are
checked before and after, and the actual depfile must list all six.

Attempt01 reached the real linker and failed because the old product registry
API did not contain the new virtual method/thunk. Attempt02 rejected the failed
batch04 proxy at preflight. Both failures remain preserved. The source repair
commit4bfbb78 adds consistent proxy overrides and the explicit IPC header;
parent batch06 then passes both actual proxy variants and registry service.

Attempt03 combines only successful, individually source-bound objects: the ANI
consumer/wrapper from selected batch05, Observer from otherwise failed batch04,
and API proxy from selected batch06. Actual depfiles confirm the earlier objects
did not consume either subsequently repaired file. The API is relinked using its
real full solink rule, CFI/version scripts and `no-undefined`, replacing those two
observer objects and retaining its other two unchanged original product objects
and all native inputs. This is a complete original-recipe solink with those
precise replacements, not a fresh build of all native dependencies.

All five actual commands pass. The stripped Rust dylib is678448 bytes, SHA256
`2fc7e3c3ff02e60cd8591c8e3561e1cfdb5e2694cbcf5ac3b73464a521853ee6`.
The unstripped dylib is10058632 bytes, SHA256
`ec27ae311d51b4edafdaf7f4fcffcec6db8224d29c17a4dcc272006661ff54e3`.
All129 recorded existing dependency inputs remain unchanged. The exact full
commands, six module hashes, object provenance, tools and artifacts are saved
byte-for-byte in `round8-rust-complete-evidence.json`; its SHA256 is
`2320364200791a1fb6835996898b24e46433effb4390cf0f313e4b18a4364bfc`.
The host paths, Docker invocation, frozen archive, prior failed attempts and
remaining integration gates are in `round8-full-rust.json`.

The helper's five light tests cover failed/wrong/duplicate object rejection,
source/argv/generator/dependency binding, safe known prefixes versus obsolete
consumed headers, bitcode module validation, architecture, symlink/path escape
and missing dependencies. These metadata tests do not stand in for compilation.
The parent still owns fresh product integration, the newly packaged ARM64 phone
runtime gate and validation of the remaining five artifacts.
