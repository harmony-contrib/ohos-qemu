#!/usr/bin/env python3
"""Compile bounded IPC/RS component repairs with real three-product Ninja flags.

Source/output are read-only; complete GN/link and guest IPC acceptance remain
the responsibility of the new representative package build.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

from compile_camera_component import assert_seed_inactive

FILES = (
    ("foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/rs_connect_to_render_process.cpp",
     "obj/foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/librender_service/rs_connect_to_render_process.o"),
    ("foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/zidl/rs_connect_to_render_process_stub.cpp",
     "obj/foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/zidl/librender_service/rs_connect_to_render_process_stub.o"),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def overlay_patched_include_directories(command, cwd, root, staged):
    """Prefer owned modified headers while retaining every real RO include."""
    revised = []
    for token in command:
        if token.startswith('-I') and len(token) > 2:
            original = (cwd / token[2:]).resolve()
            lexical = Path(os.path.abspath(cwd / token[2:]))
            input_root = cwd.parents[1]
            relative = (original.relative_to(root) if original.is_relative_to(root) else
                        lexical.relative_to(input_root) if lexical.is_relative_to(input_root) else None)
            if relative is not None:
                candidate = staged / relative
                if candidate.is_dir():
                    revised.append('-I' + str(candidate))
        revised.append(token)
    return revised


def prepare_missing_rust_cxx(root, cwd, argv, output, index, line):
    """Run the real bridge generator; never substitute a declaration stub."""
    generator = cwd / argv[1]
    if sha(generator) != sha(root / "build/templates/rust/rust_cxxbridge.py"):
        raise ValueError("Rust bridge script differs from the pinned current source")
    # Completed scratch deliberately uses RO source symlinks. Check the GN
    # argument's lexical root first, then compare the resolved file's content.
    source = Path(os.path.abspath(cwd / argv[argv.index("--") + 1]))
    relative = source.relative_to(cwd.parents[1])
    if relative != Path("foundation/graphic/graphic_2d/rosen/modules/render_service_base/rust/src/lib.rs"):
        raise ValueError("unexpected Rust bridge source")
    if sha(source) != sha(root / relative):
        raise ValueError("completed Rust source differs from the pinned current source")
    # cxxbridge is a Linux x86_64 host tool, not an architecture-specific header.
    tool = root / "out/arm64_virt/clang_x64/thirdparty/rust_cxx/cxxbridge"
    cargo = root / "third_party/rust/crates/cxx/gen/cmd/Cargo.toml"
    version = subprocess.run([str(tool), "--version"], check=True, capture_output=True, text=True).stdout.strip()
    if version != "cxxbridge 1.0.130" or 'version = "1.0.130"' not in cargo.read_text():
        raise ValueError("Rust bridge host tool does not match the fixed source version")
    revised = list(argv)
    revised[revised.index("--cxxbridge") + 1] = str(tool)
    revised[revised.index("--") + 1] = str(root / relative)
    destinations = []
    for option in ("--cc", "--header"):
        position = revised.index(option) + 1
        path = Path(revised[position])
        if path.is_absolute() or not str(path).startswith("gen/") or ".." in path.parts:
            raise ValueError("Rust bridge output outside the owned generated tree")
        destination = output / path
        if destination.exists():
            raise ValueError("refuse to overwrite an existing Rust bridge output")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destinations.append(destination)
        revised[position] = str(destination)
    inputs = {str(path): sha(path) for path in (generator, root / relative, cargo, tool)}
    log = output / f"idl-{index}.log"
    with log.open("x") as stream:
        completed = subprocess.run(revised, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    if completed.returncode or any(not path.is_file() for path in destinations):
        raise RuntimeError("actual isolated Rust bridge generation failed")
    if any(sha(Path(path)) != value for path, value in inputs.items()):
        raise ValueError("Rust bridge input changed during generation")
    return {"kind": "rust_cxxbridge", "actual_gn_command": line, "owned_command": revised,
            "exit_code": completed.returncode, "host_tool_version": version,
            "input_sha256": inputs, "log": str(log), "log_sha256": sha(log),
            "generated_sha256": {str(path): sha(path) for path in destinations}}


def prepare_missing_idl(root, cwd, command, output, copy_readonly_inputs=False):
    """Run real GN IDL actions into owned output, never a completed seed."""
    includes = [token[2:] for token in command if token.startswith(("-Igen/foundation/", "-Igen/base/"))]
    definitions = {}
    with (cwd / "toolchain.ninja").open() as stream:
        for line in stream:
            if not line.startswith("build gen/") or ": " not in line:
                continue
            destinations = line[6:].split(": ", 1)[0].split()
            matching = [name for name in destinations if name.endswith(".h") and
                        any(str(Path(name).parent) == directory for directory in includes)]
            if matching and any(not (cwd / name).exists() and not (output / name).exists() for name in matching):
                definitions[matching[0]] = destinations
    records = []
    action_lines = []
    existing = len(list(output.glob("idl-*.log")))
    if definitions:
        queried = subprocess.run([str(root / "prebuilts/build-tools/linux-x86/bin/ninja"),
            "-w", "dupbuild=warn", "-C", str(cwd), "-t", "commands", "-s", *definitions],
            check=True, capture_output=True, text=True)
        (output / f"idl-actions-query-{existing}.stdout").write_text(queried.stdout)
        (output / f"idl-actions-query-{existing}.stderr").write_text(queried.stderr)
        action_lines = queried.stdout.strip().splitlines()
    for index, line in enumerate(action_lines, start=existing):
        argv = shlex.split(line)
        generator = cwd / argv[1] if len(argv) > 1 else None
        if len(argv) > 1 and argv[0] == "/usr/bin/env" and generator.name == "rust_cxxbridge.py":
            records.append(prepare_missing_rust_cxx(root, cwd, argv, output, index, line))
            continue
        if (len(argv) < 2 or argv[0] != "/usr/bin/env" or generator.name != "idl.py" or
                sha(generator) != sha(root / "build/config/components/idl_tool/idl.py")):
            raise ValueError("missing generated RS input is not a real GN IDL action: " + line[:200])
        originals = argv[argv.index("--dst-file") + 1].split(",")
        destinations = []
        for original in originals:
            path = Path(original)
            relative = path.relative_to(cwd)
            if not str(relative).startswith("gen/") or ".." in relative.parts:
                raise ValueError("IDL action has an output outside the generated input tree")
            destinations.append(output / relative)
        directory = Path(argv[argv.index("--dst-path") + 1]).relative_to(cwd)
        argv[argv.index("--dst-path") + 1] = str(output / directory)
        argv[argv.index("--dst-file") + 1] = ",".join(map(str, destinations))
        source_paths = argv[argv.index("--src-idl") + 1].split(",")
        source_hashes = {path: sha(Path(path)) for path in source_paths}
        for path in source_paths:
            relative = Path(path).relative_to(cwd.parents[1])
            if sha(Path(path)) != sha(root / relative):
                raise ValueError("completed scratch IDL source differs from the current pinned source")
        copied_idl_hashes = {}
        if copy_readonly_inputs:
            # The pinned generator's File::CheckValid requires W_OK even for
            # input IDL. Copy real declarations/import siblings into owned
            # scratch; never make the production source writable or use stubs.
            for source_path in source_paths:
                for source_idl in Path(source_path).parent.rglob('*.idl'):
                    relative = source_idl.relative_to(cwd.parents[1])
                    destination = output / 'idl-inputs' / relative
                    original_sha = sha(source_idl)
                    if original_sha != sha(root / relative):
                        raise ValueError('IDL import differs from pinned current source')
                    if destination.exists():
                        if sha(destination) != original_sha:
                            raise ValueError('owned IDL copy differs from original input')
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(source_idl, destination)
                    copied_idl_hashes[str(destination)] = original_sha
            argv[argv.index('--src-idl') + 1] = ','.join(str(output / 'idl-inputs' /
                Path(path).relative_to(cwd.parents[1])) for path in source_paths)
        tool = Path(argv[argv.index("--idl-tool-path") + 1]) / "idl"
        log = output / ("idl-" + str(index) + ".log")
        with log.open("x") as stream:
            generated = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
        record = {"actual_gn_command": line, "owned_command": argv, "exit_code": generated.returncode,
                  "idl_source_sha256": source_hashes, "tool_sha256": sha(tool),
                  "owned_actual_idl_input_sha256": copied_idl_hashes,
                  "generator_sha256": sha(generator),
                  "log": str(log), "log_sha256": sha(log)}
        records.append(record)
        if generated.returncode or any(not path.is_file() for path in destinations):
            raise RuntimeError("actual isolated RS IDL generation failed")
        if any(sha(Path(path)) != value for path, value in
               {**source_hashes, **copied_idl_hashes}.items()):
            raise ValueError('actual IDL inputs changed during generation')
        record["generated_sha256"] = {str(path): sha(path) for path in destinations}
    revised = []
    for token in command:
        if token.startswith("-Igen/") and (output / token[2:]).is_dir():
            revised.append("-I" + str(output / token[2:]))
        revised.append(token)
    return revised, records


def prepare_missing_libxml(root, cwd, command, output):
    """Execute the pinned real install/header GN actions in owned directories."""
    includes = ("gen/third_party/libxml2/libxml2-2.14.0/include", "obj/third_party/libxml2/include")
    if not any("-I" + directory in command for directory in includes):
        return command, []
    records = []
    generated = output / includes[1] / "libxml/xmlversion.h"
    parser = output / includes[0] / "libxml/parser.h"
    if not generated.exists() or not parser.exists():
        targets = ("gen/third_party/libxml2/libxml2-2.14.0/config.h.cmake.in",
                   "obj/third_party/libxml2/include/libxml/xmlversion.h")
        queried = subprocess.run([str(root / "prebuilts/build-tools/linux-x86/bin/ninja"),
            "-w", "dupbuild=warn", "-C", str(cwd), "-t", "commands", "-s", *targets],
            check=True, capture_output=True, text=True)
        (output / "libxml-actions-query.stdout").write_text(queried.stdout)
        (output / "libxml-actions-query.stderr").write_text(queried.stderr)
        actions = queried.stdout.strip().splitlines()
        if len(actions) != 2:
            raise ValueError("libxml headers require exactly the real install and generate actions")
        source = root / "third_party/libxml2"
        inputs = ("install.py", "generate_header.py", "libxml2-2.14.0.tar.xz",
                  "config_linux.json", "xml_version.json")
        input_hashes = {name: sha(source / name) for name in inputs}
        input_hashes.update({path.name: sha(path) for path in source.glob("*.patch")})
        for index, line in enumerate(actions):
            argv = shlex.split(line)
            script = cwd / argv[1] if len(argv) > 1 else None
            expected_script = "install.py" if index == 0 else "generate_header.py"
            if (len(argv) < 2 or argv[0] != "/usr/bin/env" or script.name != expected_script or
                    sha(script) != input_hashes[expected_script]):
                raise ValueError("unknown libxml GN preparation script")
            if index == 0:
                prior = Path(argv[argv.index("--source-file") + 1])
                if any(sha(prior / name) != value for name, value in input_hashes.items()):
                    raise ValueError("completed libxml GN inputs differ from pinned current source")
                argv[argv.index("--source-file") + 1] = str(source)
                destination = output / "gen/third_party/libxml2"
                if destination.exists():
                    raise ValueError("refuse to replace previously generated libxml input")
                destination.mkdir(parents=True)
                argv[argv.index("--gen-dir") + 1] = str(destination)
            else:
                for option in ("--config-input-path", "--config-path",
                               "--xmlversion-input-path", "--xmlversion-path"):
                    position = argv.index(option) + 1
                    relative = Path(argv[position])
                    if relative.is_absolute() or ".." in relative.parts:
                        raise ValueError("libxml header action path outside its generated tree")
                    argv[position] = str(output / relative)
                    if option in ("--config-path", "--xmlversion-path"):
                        Path(argv[position]).parent.mkdir(parents=True, exist_ok=True)
            log = output / f"libxml-action-{index}.log"
            with log.open("x") as stream:
                completed = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
            records.append({"actual_gn_command": line, "owned_command": argv,
                            "input_sha256": input_hashes, "exit_code": completed.returncode,
                            "log_sha256": sha(log)})
            if completed.returncode or "error!" in log.read_text():
                raise RuntimeError("actual libxml preparation failed, including swallowed installer errors")
        if not generated.is_file() or not parser.is_file():
            raise ValueError("actual libxml headers were not produced")
        if any(sha(source / name) != value for name, value in input_hashes.items()):
            raise ValueError("pinned libxml input changed during generation")
    records.append({"parser_header_sha256": sha(parser), "version_header_sha256": sha(generated)})
    revised = []
    for token in command:
        if token in tuple("-I" + directory for directory in includes):
            revised.append("-I" + str(output / token[2:]))
        revised.append(token)
    return revised, records


def prepare_missing_jsoncpp(root, component, cwd, command, output):
    """Run the actual fixed GN jsoncpp installer; never fabricate json headers."""
    include = 'gen/third_party/jsoncpp/jsoncpp-1.9.6/include'
    if '-I' + include not in command:
        return command, []
    header = output / include / 'json/json.h'
    records = []
    if not header.is_file():
        workspace = output / 'jsoncpp-installer-input'
        workspace.mkdir()
        source = root / 'third_party/jsoncpp'
        git_archive = subprocess.Popen(['git', '-C', str(source), 'archive',
            '--prefix=third_party/jsoncpp/', 'HEAD'], stdout=subprocess.PIPE)
        subprocess.run(['tar', '-xf', '-', '-C', str(workspace)], stdin=git_archive.stdout, check=True)
        git_archive.stdout.close()
        if git_archive.wait():
            raise RuntimeError('pinned jsoncpp source archive failed')
        copied = workspace / 'third_party/jsoncpp'
        gitdir = subprocess.check_output(['git', '-C', str(source), 'rev-parse', '--absolute-git-dir'], text=True).strip()
        (copied / '.git').write_text('gitdir: ' + gitdir + '\n')
        apply_log = workspace / 'apply.log'
        with apply_log.open('x') as stream:
            subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(workspace)],
                           check=True, stdout=stream, stderr=subprocess.STDOUT)
        queried = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
            '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s',
            'gen/third_party/jsoncpp/jsoncpp-1.9.6/src/lib_json/json_reader.cpp'],
            check=True, capture_output=True, text=True)
        (workspace / 'query.stdout').write_text(queried.stdout)
        (workspace / 'query.stderr').write_text(queried.stderr)
        actions = queried.stdout.strip().splitlines()
        if len(actions) != 1:
            raise ValueError('jsoncpp preparation needs exactly its real GN installer action')
        argv = shlex.split(actions[0])
        if argv[0] != '/usr/bin/env' or Path(argv[1]).name != 'install.py':
            raise ValueError('unknown jsoncpp installer GN command')
        spec = importlib.util.spec_from_file_location('owned_jsoncpp_baseline', component / 'check.py')
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        baseline.validate(copied, require_patched=True)
        installer = cwd / argv[1]
        if sha(installer) not in (baseline.ORIGINAL_SHA256, baseline.FIRST_PATCH_SHA256, baseline.REPAIRED_SHA256):
            raise ValueError('real jsoncpp GN command uses an unknown installer')
        if sha(source / baseline.ARCHIVE) != baseline.ARCHIVE_SHA256:
            raise ValueError('jsoncpp archive differs from the pinned release')
        inputs = {str(source / baseline.ARCHIVE): sha(source / baseline.ARCHIVE),
                  str(source / 'install.py'): sha(source / 'install.py')}
        argv[1] = str(copied / 'install.py')
        argv[argv.index('--source-file') + 1] = str(source)
        argv[argv.index('--gen-dir') + 1] = str(output / 'gen/third_party/jsoncpp')
        log = workspace / 'install.log'
        with log.open('x') as stream:
            completed = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
        if completed.returncode or not header.is_file():
            raise RuntimeError('actual isolated jsoncpp generation failed')
        if any(sha(Path(path)) != value for path, value in inputs.items()):
            raise ValueError('read-only jsoncpp input changed during generation')
        records.append({'actual_gn_command': actions[0], 'owned_command': argv,
                        'readonly_input_sha256': inputs, 'installer_sha256': sha(copied / 'install.py'),
                        'component_sha256': {path.name: sha(path) for path in component.iterdir() if path.is_file()},
                        'apply_log_sha256': sha(apply_log), 'exit_code': completed.returncode,
                        'log_sha256': sha(log)})
    records.append({'header_sha256': sha(header)})
    revised = []
    for token in command:
        if token == '-I' + include:
            revised.append('-I' + str(output / include))
        revised.append(token)
    return revised, records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--component", choices=("render_connection_reply", "async_caller_identity",
                                               "binder_connector_initialization", "binder_object_safety"),
                        default="render_connection_reply")
    parser.add_argument("--completed-source", action="append", type=Path, default=[],
                        help="completed matching Camera GN/link scratch; use its real generated headers/flags without modifying it")
    parser.add_argument('--only-source', action='append', default=[],
                        help='bounded supplement for an exact listed TU; recorded as partial, never the full selection')
    args = parser.parse_args()
    root, repo = args.source_root.resolve(), args.repo_root.resolve()
    if any(not os.statvfs(path).f_flag & os.ST_RDONLY for path in (root, root / "out")):
        raise ValueError("source and product output must be read-only")
    parent = ("patches/common/foundation/communication/ipc"
              if args.component in ("binder_connector_initialization", "binder_object_safety") else
              "patches/common/foundation/graphic/graphic_2d")
    component = repo / parent / args.component
    files = FILES
    if args.component == "async_caller_identity":
        files = (
            ("foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/zidl/rs_client_to_render_connection_stub.cpp",
             "obj/foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/zidl/librender_service/rs_client_to_render_connection_stub.o"),
            ("foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/rs_client_to_render_connection.cpp",
             "obj/foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/librender_service/rs_client_to_render_connection.o"),
            ("foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/platform/ohos/rs_ashmem_helper.cpp",
             "obj/foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/platform/ohos/rosen_ohos_sources/rs_ashmem_helper.o"),
            ("foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/transaction/rs_transaction_data.cpp",
             "obj/foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/transaction/render_service_base_src/rs_transaction_data.o"),
            ("foundation/graphic/graphic_2d/rosen/modules/render_service/core/rs_render_pipeline_agent.cpp",
             "obj/foundation/graphic/graphic_2d/rosen/modules/render_service/core/librender_service/rs_render_pipeline_agent.o"),
            ("foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/rs_unmarshal_thread.cpp",
             "obj/foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/librender_service/rs_unmarshal_thread.o"),
            ("foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/feature/delegate_composite/rs_delegate_composite_callback_manager.cpp",
             "obj/foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/feature/delegate_composite/render_service_base_src/rs_delegate_composite_callback_manager.o"),
            ("foundation/graphic/graphic_2d/rosen/modules/render_service/core/pipeline/main_thread/rs_main_thread.cpp",
             "obj/foundation/graphic/graphic_2d/rosen/modules/render_service/core/pipeline/main_thread/librender_service/rs_main_thread.o"),
            ("foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/platform/ohos/rs_marshalling_helper.cpp",
             "obj/foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/platform/ohos/rosen_ohos_sources/rs_marshalling_helper.o"),
            ("foundation/graphic/graphic_2d/rosen/modules/render_service/main/render_server/transaction/zidl/rs_client_to_service_connection_stub.cpp",
             "obj/foundation/graphic/graphic_2d/rosen/modules/render_service/main/render_server/transaction/zidl/librender_service/rs_client_to_service_connection_stub.o"),
            ("foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/command/rs_command_factory.cpp",
             "obj/foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/command/render_service_base_src/rs_command_factory.o"),
        )
        subprocess.run(["python3", str(component / "verify_source.py"), "--source-root", str(root)], check=True)
    elif args.component == "binder_connector_initialization":
        files = (("foundation/communication/ipc/ipc/native/src/core/invoker/source/binder_connector.cpp",
                  "obj/foundation/communication/ipc/ipc/native/src/core/invoker/source/ipc_common/binder_connector.o"),)
        subprocess.run(["python3", str(component / "verify_source.py"), "--source-root", str(root)], check=True)
    elif args.component == "binder_object_safety":
        files = (
            ("foundation/communication/ipc/ipc/native/src/core/invoker/source/binder_invoker.cpp",
             "obj/foundation/communication/ipc/ipc/native/src/core/invoker/source/ipc_single/binder_invoker.o"),
            ("foundation/communication/ipc/ipc/native/src/core/framework/source/message_parcel.cpp",
             "obj/foundation/communication/ipc/ipc/native/src/core/framework/source/ipc_single/message_parcel.o"),
        )
        subprocess.run(["python3", str(component / "verify_source.py"), "--source-root", str(root)], check=True)
    full_sources = tuple(source for source, _ in files)
    if args.only_source:
        if len(set(args.only_source)) != len(args.only_source) or not set(args.only_source) <= set(full_sources):
            parser.error('--only-source requires unique exact production TUs from the selected component')
        files = tuple(row for row in files if row[0] in args.only_source)
    patch_name = {"render_connection_reply": "0001-match-existing-client-render-connection-reply.patch",
                  "async_caller_identity": "0001-use-kernel-identity-only-for-zero-pid-async-commits.patch",
                  "binder_connector_initialization": "0001-synchronize-all-binder-singleton-publication-and-reads.patch",
                  "binder_object_safety": "0001-copy-four-byte-aligned-binder-objects-and-close-fd-zero.patch"}[args.component]
    patch = component / patch_name
    if args.output.exists():
        raise ValueError("refusing to replace prior compile evidence")
    result = {"scope": "real_three_ABI_server_translation_units_only_NOT_link_or_guest_IPC_validation",
              "first_artifact_behavior_gate_passed": False, "component": args.component,
              "patch_sha256": sha(patch), "results": [], "status": "fail"}
    result.update(requested_sources=[source for source, _ in files],
                  full_component_sources=list(full_sources),
                  full_compilation_selection=len(files) == len(full_sources),
                  compiler_check_script_sha256=sha(Path(__file__)))
    result["component_payload_sha256"] = {
        path.name: sha(path) for path in sorted(component.iterdir()) if path.is_file()}
    staged = Path(tempfile.mkdtemp(prefix="render-connection-reply-compile-"))
    result["scratch"] = str(staged)
    try:
        frozen = staged / "inputs"
        shutil.copytree(repo / "patches/lib", frozen / "patches/lib")
        frozen_component = frozen / component.relative_to(repo)
        shutil.copytree(component, frozen_component)
        frozen_jsoncpp = frozen / 'patches/common/third_party/jsoncpp/generated_source'
        if args.component == 'async_caller_identity':
            shutil.copytree(repo / 'patches/common/third_party/jsoncpp/generated_source', frozen_jsoncpp)
            result['frozen_jsoncpp_component_sha256'] = {
                path.name: sha(path) for path in frozen_jsoncpp.iterdir() if path.is_file()}
        if result["component_payload_sha256"] != {
                path.name: sha(path) for path in frozen_component.iterdir() if path.is_file()}:
            raise ValueError("component changed while its validation inputs were frozen")
        completed_sources = {}
        result["completed_generated_input_evidence"] = []
        for candidate in args.completed_source:
            candidate = candidate.resolve()
            if candidate == root or candidate.is_relative_to(root) or root.is_relative_to(candidate):
                raise ValueError("completed scratch must be separate from production")
            records = []
            for evidence in candidate.glob("camera-component-*-evidence.json"):
                record = json.loads(evidence.read_text())
                if (record.get("scratch_source") == str(candidate)
                        and record.get("gn_exit_code") == 0 and record.get("link_exit_code") == 0):
                    records.append((evidence, record))
            if len(records) != 1:
                raise ValueError("scratch must have exactly one matching successful Camera GN/link record")
            evidence, record = records[0]
            product = record["product"]
            if product not in ("arm64_virt", "armv7a_virt", "x86_64_virt") or product in completed_sources:
                raise ValueError("unknown or duplicate completed product scratch")
            assert_seed_inactive(candidate)
            completed_sources[product] = candidate
            result["completed_generated_input_evidence"].append(
                {"product": product, "source": str(candidate), "evidence": str(evidence), "sha256": sha(evidence)})
        for source, _ in files:
            target = staged / source
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / source, target)
        if args.component in ("async_caller_identity", "binder_connector_initialization", "binder_object_safety"):
            spec = importlib.util.spec_from_file_location("rs_identity_baseline", frozen_component / "verify_source.py")
            baseline = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(baseline)
            for relative, _, _ in baseline.FILES:
                target = staged / baseline.PROJECT / relative
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(root / baseline.PROJECT / relative, target)
        if args.component == "async_caller_identity":
            # The connection's unchanged local header includes zidl/stub.h.
            # Materialize it next to the owned source so it resolves the patched
            # private header, rather than a pristine header in the RO tree.
            companion = "foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/rs_client_to_render_connection.h"
            shutil.copy2(root / companion, staged / companion)
            result["unchanged_companion_sha256"] = {companion: sha(root / companion)}
        apply_log = staged / "component-apply.log"
        with apply_log.open("x") as stream:
            apply_codes = []
            for _ in range(2):
                applied = subprocess.run(["bash", str(frozen_component / "apply.sh"), "--source-root", str(staged)],
                                         stdout=stream, stderr=subprocess.STDOUT)
                apply_codes.append(applied.returncode)
                if applied.returncode:
                    break
        result["component_apply"] = {"exit_code": applied.returncode, "log": str(apply_log),
                                     "log_sha256": sha(apply_log), "first_and_idempotent_apply_exit_codes": apply_codes}
        if applied.returncode:
            raise RuntimeError("frozen component application failed; see owned apply evidence")
        for product in ("arm64_virt", "armv7a_virt", "x86_64_virt"):
            input_source = completed_sources.get(product, root)
            cwd = input_source / "out" / product
            output = staged / product
            output.mkdir()
            for relative, target in files:
                unit_output = output / Path(relative).stem
                unit_output.mkdir()
                commands = subprocess.run([str(root / "prebuilts/build-tools/linux-x86/bin/ninja"), "-w", "dupbuild=warn",
                                           "-C", str(cwd), "-t", "commands", "-s", target],
                                          text=True, capture_output=True, check=True)
                command = shlex.split(commands.stdout.splitlines()[-1])
                if Path(command[0]).name == "ccache":
                    command.pop(0)
                if Path(command[0]).name != "clang++" or (cwd / command[command.index("-c") + 1]).resolve() != root / relative:
                    raise ValueError("unexpected real compiler command/source")
                command[command.index("-c") + 1] = str(staged / relative)
                obj = unit_output / Path(target).name
                command[command.index("-o") + 1] = str(obj)
                command[command.index("-MF") + 1] = str(obj.with_suffix(".d"))
                command = overlay_patched_include_directories(command, cwd, root, staged)
                generated_inputs = []
                libxml_inputs = []
                jsoncpp_inputs = []
                if args.component == "async_caller_identity":
                    command, generated_inputs = prepare_missing_idl(root, cwd, command, output)
                    command, libxml_inputs = prepare_missing_libxml(root, cwd, command, output)
                    command, jsoncpp_inputs = prepare_missing_jsoncpp(root, frozen_jsoncpp, cwd, command, output)
                # Preserve the original translation unit's implicit local
                # quoted-header search without copying/changing those headers.
                command.extend(["-iquote", str((staged / relative).parent),
                                "-iquote", str((root / relative).parent)])
                log = obj.with_suffix(".log")
                with log.open("x") as stream:
                    compiled = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
                result["results"].append({"product": product, "source": relative, "argv": command,
                                           "generated_input_cwd": str(cwd),
                                           "exit_code": compiled.returncode, "log": str(log), "log_sha256": sha(log),
                                           "owned_real_idl_generation": generated_inputs,
                                           "owned_real_jsoncpp_generation": jsoncpp_inputs,
                                           "owned_real_libxml_generation": libxml_inputs,
                                           "object_sha256": sha(obj) if obj.is_file() else None,
                                           "patched_source_sha256": sha(staged / relative)})
                if compiled.returncode:
                    raise RuntimeError(product + " actual translation unit failed: " + relative)
        result["status"] = "pass"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result["error"] = str(error)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "error": result.get("error")}))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
