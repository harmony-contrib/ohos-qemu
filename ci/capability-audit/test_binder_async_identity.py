"""Approved identity boundaries; host snippets are not guest/package acceptance."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'patches/lib'))
from exact_source_states import validate_component


def load(relative, name):
    spec = importlib.util.spec_from_file_location(name, REPO / relative / 'verify_source.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


KERNEL = load('patches/common/kernel/linux/linux_6_6/binder_async_sender', 'binder_async_identity_test')
RS = load('patches/common/foundation/graphic/graphic_2d/async_caller_identity', 'rs_async_identity_test')


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


class BinderAsyncIdentityTests(unittest.TestCase):
    def test_exact_all_file_preflight_preserves_unknown_partial_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / 'project'
            project.mkdir()
            files = tuple((name, sha('original\n'), sha('repaired\n')) for name in ('a.c', 'b.h'))
            for name, _, _ in files:
                (project / name).write_text('original\n')
            self.assertFalse(validate_component(root, 'project', 'fixed', files))
            with self.assertRaises(ValueError):
                validate_component(root, 'project', 'fixed', files, True)
            (project / 'a.c').write_text('repaired\n')
            with self.assertRaisesRegex(ValueError, 'partial'):
                validate_component(root, 'project', 'fixed', files)
            (project / 'b.h').write_text('repaired\n')
            self.assertTrue(validate_component(root, 'project', 'fixed', files, True))
            (project / 'a.c').write_text('foreign\n')
            with self.assertRaises(ValueError): validate_component(root, 'project', 'fixed', files)
            self.assertEqual((project / 'a.c').read_text(), 'foreign\n')
            (project / 'a.c').unlink()
            (project / 'a.c').symlink_to(project / 'b.h')
            with self.assertRaisesRegex(ValueError, 'symlink'):
                validate_component(root, 'project', 'fixed', files)
            self.assertEqual((project / 'b.h').read_text(), 'repaired\n')

    def test_pinned_head_is_checked_without_accepting_other_release_commits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / 'project'
            project.mkdir()
            (project / '.git').mkdir()
            (project / 'file').write_text('original\n')
            files = (('file', sha('original\n'), sha('repaired\n')),)
            with patch('exact_source_states.subprocess.check_output', return_value='different\n'):
                with self.assertRaisesRegex(ValueError, 'pinned'):
                    validate_component(root, 'project', 'fixed', files)
            self.assertEqual((project / 'file').read_text(), 'original\n')

    def test_components_match_current_manifest_lock_and_single_ordered_plan(self):
        lock = json.loads((REPO / 'scripts/openharmony_7_0_release_source_lock.json').read_text())
        projects = {row['path']: row['revision'] for row in lock['projects']}
        self.assertEqual(projects[KERNEL.PROJECT], KERNEL.REVISION)
        self.assertEqual(projects[RS.PROJECT], RS.REVISION)
        builder = (REPO / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        plan = builder.split('apply_qemu_capability_patch_plan() {', 1)[1].split('\n}\n', 1)[0]
        for variable in ('QEMU_BINDER_ASYNC_SENDER_COMPONENT_SCRIPT', 'RS_ASYNC_CALLER_IDENTITY_COMPONENT_SCRIPT'):
            self.assertEqual(plan.count('bash "${' + variable + '}"'), 1)
            self.assertLess(plan.index(variable), plan.index('configure_qemu_device_profile'))
        self.assertLess(plan.index('QEMU_BINDER_ASYNC_SENDER_COMPONENT_SCRIPT'),
                        plan.index('RS_ASYNC_CALLER_IDENTITY_COMPONENT_SCRIPT'))

    def test_async_wire_and_sender_lifetime_are_not_replaced_by_client_pid(self):
        component = REPO / 'patches/common/kernel/linux/linux_6_6/binder_async_sender'
        source = '\n'.join(path.read_text() for path in sorted(component.glob('*.patch')))
        additions = '\n'.join(line[1:] for line in source.splitlines() if line.startswith('+') and not line.startswith('+++'))
        self.assertIn('get_task_pid(current, PIDTYPE_TGID)', additions)
        self.assertIn('if (!reply && (tr->flags & TF_ONE_WAY))', additions)
        self.assertEqual(additions.count('put_pid(t->async_sender_pid);'), 2)
        self.assertEqual(additions.count('put_pid(t_outdated->async_sender_pid);'), 1)
        self.assertIn('thread->sender_pid_nr = pid_nr(t->async_sender_pid)', additions)
        for forbidden in ('tr->sender_pid', 'trd->sender_pid =', 't->from =', 'sender_tokenid =', 'first_tokenid ='):
            self.assertNotIn(forbidden, additions)
        self.assertNotIn('uapi/', source)

    def test_frozen_update_cleanup_releases_exactly_once_without_double_accounting(self):
        replacement = next((old, new) for old, new in KERNEL.REPLACEMENTS['drivers/android/binder.c']
                           if 'kfree(t_outdated);' in old)
        old, new = replacement
        self.assertEqual(new.count('put_pid(t_outdated->async_sender_pid);'), 1)
        self.assertLess(new.index('put_pid('), new.index('kfree(t_outdated);'))
        self.assertIn('#ifdef CONFIG_BINDER_SENDER_INFO', new)
        self.assertNotIn('binder_free_transaction', new)
        self.assertNotIn('outstanding_txns', new)
        self.assertEqual(old.replace('\t\tkfree(t_outdated);',
                                     '#ifdef CONFIG_BINDER_SENDER_INFO\n'
                                     '\t\tput_pid(t_outdated->async_sender_pid);\n'
                                     '#endif\n\t\tkfree(t_outdated);'), new)

    def test_actual_rs_fallback_snippet_under_sanitizers(self):
        compiler = shutil.which('clang++')
        self.assertIsNotNone(compiler)
        preface = '''#include <cassert>
#include <cstdint>
#include <cstdio>
using pid_t = int;
constexpr int ERR_INVALID_STATE=-7;
enum class RSIClientToRenderConnectionInterfaceCode : uint32_t { COMMIT_TRANSACTION=23 };
struct MessageOption { static constexpr uint32_t TF_ASYNC=1; uint32_t flags; int GetFlags() const { return flags; } };
static pid_t wirePid, trustedPid, observedPid;
static unsigned realReads, marshals;
pid_t GetCallingPid() { return wirePid; }
struct IPCSkeleton { static pid_t GetCallingRealPid() { ++realReads; return trustedPid; } };
struct RSMarshallingHelper { static void SetCallingPid(pid_t p) { observedPid=p; ++marshals; } };
'''
        cases = '''    return 0;
}
int main() {
  unsigned tested=0;
  const int pids[]={-1,0,1,37,9999};
  for (uint32_t code=0;code<64;++code) for (uint32_t flags=0;flags<8;++flags)
    for (int w:pids) for (int t:pids) {
      wirePid=w; trustedPid=t; observedPid=-888; realReads=marshals=0;
      const bool fallback=code==23 && w==0 && (flags&1)!=0;
      const int result=entry(code,{flags});
      assert(realReads==static_cast<unsigned>(fallback));
      if (fallback && t<=0) {
        assert(result==ERR_INVALID_STATE && marshals==0 && observedPid==-888);
      } else {
        assert(result==0 && marshals==1 && observedPid==(fallback?t:w));
      }
      assert(RSScopedAsyncCallerPid::Get()==0);
      ++tested;
    }
  // Neither a forged command PID nor option bits outside TF_ASYNC are read.
  assert(tested==12800);
  std::puts("host_actual_identity_snippet_12800_boundaries_NOT_kernel_or_RS_IPC_acceptance");
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'identity.cpp'
            source.write_text(preface + RS.CALLER_CONTEXT +
                              'int entry(uint32_t code, MessageOption option) {\n' + RS.NEW_IDENTITY + cases)
            binary = root / 'identity'
            subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', str(source), '-o', str(binary)],
                           check=True, capture_output=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
            self.assertIn('12800_boundaries_NOT_kernel_or_RS_IPC_acceptance', result.stdout)
        self.assertNotIn('Read', RS.NEW_IDENTITY)
        self.assertNotIn('IsCallingPidValid', RS.NEW_IDENTITY)

    def test_actual_request_scope_shared_between_translation_units_and_restored(self):
        compiler = shutil.which('clang++')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'context.h').write_text('#pragma once\n#include <sys/types.h>\n' + RS.CALLER_CONTEXT)
            (root / 'reader.cpp').write_text('#include "context.h"\npid_t readContext() { return RSScopedAsyncCallerPid::Get(); }\n')
            (root / 'main.cpp').write_text('''#include "context.h"
#include <cassert>
#include <thread>
pid_t readContext();
int main() {
    assert(readContext()==0);
    {
        const RSScopedAsyncCallerPid outer(37);
        assert(readContext()==37);
        { const RSScopedAsyncCallerPid unrelated(0); assert(readContext()==0); }
        assert(readContext()==37);
        { const RSScopedAsyncCallerPid nested(99); assert(readContext()==99); }
        assert(readContext()==37);
        std::thread other([] {
            assert(readContext()==0);
            { const RSScopedAsyncCallerPid separate(81); assert(readContext()==81); }
            assert(readContext()==0);
        });
        other.join();
        assert(readContext()==37);
        try { const RSScopedAsyncCallerPid failed(63); throw 1; } catch (int) {}
        assert(readContext()==37);
    }
    assert(readContext()==0);
}
''')
            binary = root / 'context'
            subprocess.run([compiler, '-std=c++17', '-pthread', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', str(root / 'reader.cpp'),
                            str(root / 'main.cpp'), '-o', str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
