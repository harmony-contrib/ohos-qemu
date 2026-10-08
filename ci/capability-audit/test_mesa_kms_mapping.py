"""Exact historical Mesa map/unmap interleaving; not RS root-cause or guest proof."""
from pathlib import Path
import hashlib
import importlib.util
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/third_party/mesa3d/kms_mapping_synchronization'
PATCH = COMPONENT / '0001-serialize-displaytarget-mapping.patch'


def functions(repaired):
    hunks = next(iter(patch_sections(PATCH).values()))
    source = '\n'.join(line for hunk in hunks for line in hunk[2 if repaired else 1])
    selected = []
    for kind, name in (('void \\*', 'kms_sw_displaytarget_map'), ('void', 'kms_sw_displaytarget_unmap')):
        match = re.search(r'^static ' + kind + r'\n' + name + r'\([\s\S]*?^}', source, re.MULTILINE)
        if not match:
            raise ValueError('complete exact native function absent: ' + name)
        selected.append(match.group())
    return '\n'.join(selected)


MOCK = r'''
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
typedef pthread_mutex_t mtx_t;
enum {mtx_plain=0,thrd_success=0,PIPE_MAP_READ=1,PIPE_MAP_WRITE=2,DRM_IOCTL_MODE_MAP_DUMB=3};
struct kms_sw_displaytarget {uint32_t handle;unsigned size;void *mapped,*ro_mapped;int map_count;mtx_t map_lock;};
struct kms_sw_plane {unsigned offset;struct kms_sw_displaytarget *dt;};
struct sw_displaytarget {int unused;};
struct sw_winsys {int unused;};
struct kms_sw_winsys {int fd;};
struct drm_mode_map_dumb {uint32_t handle;uint64_t offset;};
static struct kms_sw_plane *kms_sw_plane(struct sw_displaytarget *dt){return (struct kms_sw_plane*)dt;}
static struct kms_sw_winsys *kms_sw_winsys(struct sw_winsys *ws){return (struct kms_sw_winsys*)ws;}
static pthread_mutex_t control=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t condition=PTHREAD_COND_INITIALIZER;
static bool reached,release_map,unmap_blocked,unmap_done,enable_hook;
static int fail_ioctl,fail_mapping,map_calls,unmap_calls;
static _Thread_local bool in_unmap_worker;
static int mtx_init(mtx_t *lock,int kind){assert(kind==mtx_plain);return pthread_mutex_init(lock,NULL);}
static void mtx_destroy(mtx_t *lock){assert(!pthread_mutex_destroy(lock));}
static void mtx_lock(mtx_t *lock){
 if(in_unmap_worker){
  int result=pthread_mutex_trylock(lock);
  if(!result)return;
  assert(result==EBUSY);
  assert(!pthread_mutex_lock(&control));unmap_blocked=true;
  assert(!pthread_cond_broadcast(&condition));assert(!pthread_mutex_unlock(&control));
 }
 assert(!pthread_mutex_lock(lock));
}
static void mtx_unlock(mtx_t *lock){assert(!pthread_mutex_unlock(lock));}
static void before_increment(void){
 if(!enable_hook)return;
 assert(!pthread_mutex_lock(&control));reached=true;
 assert(!pthread_cond_broadcast(&condition));
 while(!release_map)assert(!pthread_cond_wait(&condition,&control));
 assert(!pthread_mutex_unlock(&control));
}
static int drmIoctl(int fd,int request,struct drm_mode_map_dumb *map){
 assert(fd==7&&request==DRM_IOCTL_MODE_MAP_DUMB&&map->handle==41);
 map->offset=0;return fail_ioctl?-1:0;
}
static void *mock_mmap(void *hint,size_t size,int prot,int flags,int fd,off_t offset){
 assert(!hint&&size==256&&(prot==PROT_READ||prot==(PROT_READ|PROT_WRITE)));
 assert(flags==MAP_SHARED&&fd==7&&!offset);
 if(fail_mapping)return MAP_FAILED;
 ++map_calls;void *value=calloc(1,size);assert(value);return value;
}
static int mock_munmap(void *ptr,size_t size){assert(ptr&&ptr!=MAP_FAILED&&size==256);++unmap_calls;free(ptr);return 0;}
#define mmap mock_mmap
#define munmap mock_munmap
#define DEBUG_PRINT(...) ((void)0)
'''

MAIN = r'''
static struct kms_sw_winsys ws={.fd=7};
static struct kms_sw_displaytarget bo;
static struct kms_sw_plane plane={.offset=0,.dt=&bo};
static void *returned;
static void *map_worker(void *unused){(void)unused;returned=kms_sw_displaytarget_map((struct sw_winsys*)&ws,
 (struct sw_displaytarget*)&plane,PIPE_MAP_READ|PIPE_MAP_WRITE);return NULL;}
static void *unmap_worker(void *unused){(void)unused;in_unmap_worker=true;
 kms_sw_displaytarget_unmap((struct sw_winsys*)&ws,(struct sw_displaytarget*)&plane);
 assert(!pthread_mutex_lock(&control));unmap_done=true;assert(!pthread_cond_broadcast(&condition));
 assert(!pthread_mutex_unlock(&control));return NULL;}
static void initialize(void){bo=(struct kms_sw_displaytarget){.handle=41,.size=256,.mapped=MAP_FAILED,.ro_mapped=MAP_FAILED};
 assert(mtx_init(&bo.map_lock,mtx_plain)==thrd_success);}
int main(void){
 // Bound the concurrent regression even if a failure path leaves the lock held.
 alarm(20);
 for(int repeat=0;repeat<64;++repeat){
  initialize();map_calls=unmap_calls=0;enable_hook=false;
  void *first=kms_sw_displaytarget_map((struct sw_winsys*)&ws,(struct sw_displaytarget*)&plane,PIPE_MAP_READ|PIPE_MAP_WRITE);
  assert(first&&first!=MAP_FAILED&&bo.map_count==1);
  reached=release_map=unmap_blocked=unmap_done=false;enable_hook=true;
  pthread_t mapping,unmapping;assert(!pthread_create(&mapping,NULL,map_worker,NULL));
  assert(!pthread_mutex_lock(&control));while(!reached)assert(!pthread_cond_wait(&condition,&control));
  assert(!pthread_mutex_unlock(&control));
  assert(!pthread_create(&unmapping,NULL,unmap_worker,NULL));
  assert(!pthread_mutex_lock(&control));
  while(REPAIRED?!unmap_blocked:!unmap_done)assert(!pthread_cond_wait(&condition,&control));
  if(REPAIRED)assert(!unmap_done); // Native map lock actually prevents this teardown.
  release_map=true;assert(!pthread_cond_broadcast(&condition));assert(!pthread_mutex_unlock(&control));
  assert(!pthread_join(mapping,NULL));assert(!pthread_join(unmapping,NULL));enable_hook=false;
  if(!REPAIRED){assert(returned==MAP_FAILED&&bo.map_count==1&&unmap_calls==1);
   kms_sw_displaytarget_unmap((struct sw_winsys*)&ws,(struct sw_displaytarget*)&plane);mtx_destroy(&bo.map_lock);
   puts("reproduced_invalid_map_return_after_concurrent_unmap");return 7;}
  assert(returned==first&&bo.map_count==1&&unmap_calls==0);
  ((unsigned char*)returned)[255]=42; // Live until its actual final owner unmaps.
  kms_sw_displaytarget_unmap((struct sw_winsys*)&ws,(struct sw_displaytarget*)&plane);
  assert(!bo.map_count&&map_calls==1&&unmap_calls==1);mtx_destroy(&bo.map_lock);
 }
 initialize();fail_ioctl=1;
 assert(!kms_sw_displaytarget_map((struct sw_winsys*)&ws,(struct sw_displaytarget*)&plane,PIPE_MAP_READ));
 assert(!bo.map_count&&!pthread_mutex_trylock(&bo.map_lock));mtx_unlock(&bo.map_lock);
 fail_ioctl=0;fail_mapping=1;
 assert(!kms_sw_displaytarget_map((struct sw_winsys*)&ws,(struct sw_displaytarget*)&plane,PIPE_MAP_READ));
 assert(!bo.map_count&&!pthread_mutex_trylock(&bo.map_lock));mtx_unlock(&bo.map_lock);fail_mapping=0;
 map_calls=unmap_calls=0;
 for(int index=0;index<4;++index){unsigned mode=index%2?PIPE_MAP_READ|PIPE_MAP_WRITE:PIPE_MAP_READ;
  assert(kms_sw_displaytarget_map((struct sw_winsys*)&ws,(struct sw_displaytarget*)&plane,mode)!=MAP_FAILED);}
 assert(bo.map_count==4&&map_calls==2);
 for(int index=0;index<3;++index)kms_sw_displaytarget_unmap((struct sw_winsys*)&ws,(struct sw_displaytarget*)&plane);
 assert(bo.map_count==1&&!unmap_calls);
 kms_sw_displaytarget_unmap((struct sw_winsys*)&ws,(struct sw_displaytarget*)&plane);
 assert(!bo.map_count&&unmap_calls==2&&bo.mapped==MAP_FAILED&&bo.ro_mapped==MAP_FAILED);
 kms_sw_displaytarget_unmap((struct sw_winsys*)&ws,(struct sw_displaytarget*)&plane);
 assert(!bo.map_count&&unmap_calls==2&&!pthread_mutex_trylock(&bo.map_lock));mtx_unlock(&bo.map_lock);
 mtx_destroy(&bo.map_lock);puts("serialized_map_unmap_and_failure_cleanup_pass");
}
'''


class MesaKmsMappingTests(unittest.TestCase):
    def test_original_native_interleaving_reproduces_invalid_return(self):
        source = functions(False).replace('   kms_sw_dt->map_count++;',
                                          '   before_increment();\n   kms_sw_dt->map_count++;')
        # Original has no lock operations; suppress only unused fixture helpers.
        source = MOCK.replace('static void mtx_lock(', 'static __attribute__((unused)) void mtx_lock(') + source
        result = compile_run('#define REPAIRED 0\n' + source + MAIN, expect_success=False)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertIn('reproduced_invalid_map_return_after_concurrent_unmap', result.stdout)
        self.assertNotIn('Sanitizer', result.stderr)

    def test_repaired_exact_native_interleaving_and_all_map_unmap_returns(self):
        source = functions(True).replace('   kms_sw_dt->map_count++;',
                                         '   before_increment();\n   kms_sw_dt->map_count++;')
        result = compile_run('#define REPAIRED 1\n' + MOCK + source + MAIN)
        self.assertIn('serialized_map_unmap_and_failure_cleanup_pass', result.stdout)

    def test_created_and_imported_targets_initialize_and_release_mutex(self):
        source = '\n'.join(line for hunk in next(iter(patch_sections(PATCH).values())) for line in hunk[2])
        self.assertEqual(source.count('if (mtx_init(&kms_sw_dt->map_lock, mtx_plain) != thrd_success)'), 2)
        self.assertEqual(source.count('mtx_destroy(&kms_sw_dt->map_lock);'), 4)
        self.assertIn('off_t lseek_ret = lseek(fd, 0, SEEK_END);\n   if (lseek_ret == -1) {\n      mtx_destroy', source)
        self.assertIn('plane = get_plane(kms_sw_dt, format, width, height, stride, offset);\n   if (!plane) {\n      mtx_destroy', source)

    def test_complete_source_guard_repeatability_and_unknown_edit_preservation(self):
        spec = importlib.util.spec_from_file_location('kms_backport', COMPONENT / 'files/apply_mesa_kms_mapping.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_preimages(root, PATCH)
            path = root / helper.RELATIVE
            (root / 'VERSION').write_text('21.3.3\n')
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            subprocess.run(['git', '-C', root, 'apply', PATCH], check=True, capture_output=True)
            after = hashlib.sha256(path.read_bytes()).hexdigest()
            subprocess.run(['git', '-C', root, 'apply', '-R', PATCH], check=True, capture_output=True)
            with patch.object(helper, 'ORIGINAL_SHA', before), patch.object(helper, 'REPAIRED_SHA', after):
                helper.apply(root, PATCH)
                helper.apply(root, PATCH)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), after)
                path.write_bytes(b'unknown user changes')
                with self.assertRaises(ValueError):
                    helper.apply(root, PATCH)
                self.assertEqual(path.read_bytes(), b'unknown user changes')
                (root / 'VERSION').write_text('25.0.1\n')
                with self.assertRaises(ValueError):
                    helper.apply(root, PATCH)

    def test_both_builders_apply_before_meson_and_gn_tracks_exact_assets(self):
        device = ROOT / 'patches/common/device/qemu/kms_mesa_build'
        for item in sorted(device.glob('*.patch')):
            sections = patch_sections(item)
            python = [value for name, value in sections.items() if name.endswith('.py')]
            self.assertEqual(len(python), 1)
            lines = '\n'.join(line for hunk in python[0] for line in hunk[2])
            self.assertLess(lines.index('apply_mesa_kms_mapping.py'), lines.index('write_cross_file('))
            self.assertIn('"--source-root", str(source_dir)], check=True,', lines)
            self.assertNotIn('except', lines)
        for item in (device / '0001-integrate-shared-64bit-mapping-backport.patch',
                     ROOT / 'patches/common/third_party/mesa3d/kms_mapping_build/0001-track-armv7a-mapping-backport-inputs.patch'):
            added = '\n'.join(line for line in item.read_text().splitlines()
                              if line.startswith('+') and not line.startswith('+++'))
            self.assertIn('inputs = [', added)
            self.assertIn('mesa_kms_mapping/apply_mesa_kms_mapping.py', added)
            self.assertIn('mesa_kms_mapping/0001-serialize-displaytarget-mapping.patch', added)
        builder = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        plan = builder.split('apply_qemu_capability_patch_plan() {', 1)[1].split('\nmain() {', 1)[0]
        for variable in ('MESA_KMS_MAPPING_COMPONENT_SCRIPT', 'QEMU_KMS_MESA_BUILD_COMPONENT_SCRIPT',
                         'MESA_KMS_MAPPING_BUILD_COMPONENT_SCRIPT'):
            invocation = 'bash "${' + variable + '}" --source-root "${OHOS_ROOT}"'
            self.assertEqual(plan.count(invocation), 1)
            self.assertLess(plan.index('apply_standard_vpn_component'), plan.index(invocation))

    def test_device_recipes_fail_before_mutating_siblings_with_unknown_input(self):
        component = ROOT / 'patches/common/device/qemu/kms_mesa_build'
        spec = importlib.util.spec_from_file_location('kms_recipe', component / 'apply_recipe.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_preimages(root, tuple(sorted(component.glob('*.patch'))))
            files = []
            before = {}
            for relative, original, repaired, item, optional in helper.FILES:
                path = root / helper.PROJECT / relative
                before[relative] = path.read_bytes()
                files.append((relative, hashlib.sha256(before[relative]).hexdigest(), repaired, item, optional))
            unknown = root / helper.PROJECT / files[-1][0]
            unknown.write_bytes(b'unknown user recipe')
            with patch.object(helper, 'FILES', tuple(files)), self.assertRaises(ValueError):
                helper.apply(root)
            for relative, content in before.items():
                self.assertEqual((root / helper.PROJECT / relative).read_bytes(),
                                 b'unknown user recipe' if relative == files[-1][0] else content)

    def test_device_recipes_reapply_exact_payload_refresh_without_markers(self):
        component = ROOT / 'patches/common/device/qemu/kms_mesa_build'
        spec = importlib.util.spec_from_file_location('kms_recipe_repeat', component / 'apply_recipe.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_preimages(root, tuple(sorted(component.glob('*.patch'))))
            before = {relative: (root / helper.PROJECT / relative).read_bytes()
                      for relative, _, _, _, _ in helper.FILES}
            for item in sorted(component.glob('*.patch')):
                subprocess.run(['git', '-C', root, 'apply', item], check=True, capture_output=True)
            files = tuple((relative, hashlib.sha256(before[relative]).hexdigest(),
                           hashlib.sha256((root / helper.PROJECT / relative).read_bytes()).hexdigest(), item, optional)
                          for relative, _, _, item, optional in helper.FILES)
            for relative, content in before.items():
                (root / helper.PROJECT / relative).write_bytes(content)
            with patch.object(helper, 'FILES', files):
                helper.apply(root)
                helper.apply(root)
                # The normal base installer refreshes only the shared Python payload.
                (root / helper.PROJECT / files[0][0]).write_bytes(before[files[0][0]])
                helper.apply(root)
            for relative, _, repaired, _, _ in files:
                self.assertEqual(hashlib.sha256((root / helper.PROJECT / relative).read_bytes()).hexdigest(), repaired)


if __name__ == '__main__':
    unittest.main()
