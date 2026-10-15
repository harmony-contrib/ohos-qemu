"""Native KMS import/final-release race with explicit DRM doubles, not guest proof."""
import base64
import gzip
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/third_party/mesa3d/kms_mapping_synchronization'
PATCH = COMPONENT / '0002-serialize-import-reference-and-final-destroy.patch'
PREPARED_SHA = 'e5fef3b60fa2c555bc4447cba13a2dd23819fd7f6bf33c065a597a9bca909670'
REPAIRED_SHA = 'e34309672d2bec5db3ed89e53fa340d8cbcac89dfa7f074c3280673ddc3a5687'
RELATIVE = Path('src/gallium/winsys/sw/kms-dri/kms_dri_sw_winsys.c')


def native_source(repaired):
    fixture = Path(__file__).with_name('fixtures') / 'kms_winsys_mapping_prepared.c.gz.b64'
    source = gzip.decompress(base64.b64decode(fixture.read_bytes()))
    if hashlib.sha256(source).hexdigest() != PREPARED_SHA:
        raise ValueError('complete prepared historical source differs')
    if not repaired:
        return source.decode()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        target = root / RELATIVE
        target.parent.mkdir(parents=True)
        target.write_bytes(source)
        subprocess.run(['git', '-C', root, 'apply', PATCH], check=True, capture_output=True)
        result = target.read_bytes()
    if hashlib.sha256(result).hexdigest() != REPAIRED_SHA:
        raise ValueError('complete candidate historical source differs')
    return result.decode()


def bodies(repaired):
    source = native_source(repaired)
    names = ('get_plane', 'kms_sw_displaytarget_find_and_ref',
             'kms_sw_displaytarget_add_from_prime', 'kms_sw_displaytarget_from_handle',
             'kms_sw_displaytarget_destroy')
    selected = []
    for name in names:
        match = re.search(r'^static [^;{}]*\b' + name + r'\([^;{}]*\)\n\{[\s\S]*?^}',
                          source, re.MULTILINE)
        if not match:
            raise ValueError('complete native body missing: ' + name)
        body = match.group()
        if name == 'kms_sw_displaytarget_find_and_ref':
            anchor = '         kms_sw_dt->ref_count++;'
            if body.count(anchor) != 1:
                raise ValueError('interleaving hook differs')
            body = body.replace(anchor, '         before_ref();\n' + anchor)
        selected.append(body)
    return '\n'.join(selected)


DOUBLES = r'''
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
typedef pthread_mutex_t mtx_t;
enum {mtx_plain=0,thrd_success=0,WINSYS_HANDLE_TYPE_KMS=1,WINSYS_HANDLE_TYPE_FD=2,
 DRM_IOCTL_MODE_DESTROY_DUMB=3};
enum pipe_format {FORMAT_RGBA};
struct list_head {struct list_head *next,*prev;};
static void list_inithead(struct list_head *h){h->next=h->prev=h;}
static void list_add(struct list_head *n,struct list_head *h){n->next=h->next;n->prev=h;h->next->prev=n;h->next=n;}
static void list_del(struct list_head *n){n->prev->next=n->next;n->next->prev=n->prev;}
#define ENTRY(n,t,m) ((t*)((char*)(n)-offsetof(t,m)))
#define LIST_FOR_EACH_ENTRY(v,h,m) \
 for(struct list_head *node=(h)->next;node!=(h)&&((v)=ENTRY(node,__typeof__(*(v)),m),1);node=node->next)
#define LIST_FOR_EACH_ENTRY_SAFE(v,tmp,h,m) \
 for(struct list_head *node=(h)->next,*next=node->next;node!=(h)&& \
 ((v)=ENTRY(node,__typeof__(*(v)),m),(tmp)=next==(h)?NULL:ENTRY(next,__typeof__(*(tmp)),m),1);node=next,next=node->next)
struct sw_winsys {int unused;};
struct sw_displaytarget {int unused;};
struct kms_sw_displaytarget {enum pipe_format format;unsigned size;uint32_t handle;
 void *mapped,*ro_mapped;int ref_count,map_count;struct list_head link,planes;mtx_t map_lock;};
struct kms_sw_plane {unsigned width,height,stride,offset;struct kms_sw_displaytarget *dt;struct list_head link;};
struct kms_sw_winsys {struct sw_winsys base;int fd;struct list_head bo_list;mtx_t bo_lock;};
struct winsys_handle {unsigned type,handle,stride,offset;};
struct pipe_resource {enum pipe_format format;unsigned width0,height0;};
struct drm_mode_destroy_dumb {uint32_t handle;};
static struct kms_sw_plane *kms_sw_plane(struct sw_displaytarget *p){return (void*)p;}
static struct sw_displaytarget *sw_displaytarget(struct kms_sw_plane *p){return (void*)p;}
static struct kms_sw_winsys *kms_sw_winsys(struct sw_winsys *p){return (void*)p;}
static unsigned util_format_get_2d_size(enum pipe_format f,unsigned s,unsigned h){(void)f;return s*h;}
static pthread_mutex_t control=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t condition=PTHREAD_COND_INITIALIZER;
static bool hook,reached,release_ref,destroy_blocked,destroy_done;
static _Thread_local bool destroy_thread;
static int destroy_calls,fail_prime,fail_seek,fail_init;
static int mtx_init(mtx_t *m,int kind){assert(kind==mtx_plain);return fail_init?1:pthread_mutex_init(m,NULL);}
static void mtx_destroy(mtx_t *m){assert(!pthread_mutex_destroy(m));}
static __attribute__((unused)) void mtx_lock(mtx_t *m){
 if(destroy_thread){int r=pthread_mutex_trylock(m);if(!r)return;assert(r==EBUSY);
  assert(!pthread_mutex_lock(&control));destroy_blocked=true;
  assert(!pthread_cond_broadcast(&condition));assert(!pthread_mutex_unlock(&control));}
 assert(!pthread_mutex_lock(m));
}
static __attribute__((unused)) void mtx_unlock(mtx_t *m){assert(!pthread_mutex_unlock(m));}
static void before_ref(void){if(!hook)return;
 assert(!pthread_mutex_lock(&control));reached=true;assert(!pthread_cond_broadcast(&condition));
 while(!release_ref)assert(!pthread_cond_wait(&condition,&control));
 assert(!pthread_mutex_unlock(&control));}
static int drmIoctl(int fd,int request,struct drm_mode_destroy_dumb *p){
 assert(fd==7&&request==DRM_IOCTL_MODE_DESTROY_DUMB&&p->handle==41);++destroy_calls;return 0;}
static int drmPrimeFDToHandle(int fd,int prime,uint32_t *h){assert(fd==7&&prime==9);*h=41;return fail_prime?-1:0;}
static off_t fake_lseek(int fd,off_t offset,int whence){assert(fd==9&&!offset);
 return fail_seek?-1:(whence==SEEK_END?256:0);}
#define lseek fake_lseek
#define CALLOC_STRUCT(t) calloc(1,sizeof(struct t))
#define FREE free
#define DEBUG_PRINT(...) ((void)0)
#define FALLTHROUGH __attribute__((fallthrough))
'''

MAIN = r'''
static struct kms_sw_winsys ws={.fd=7};
static struct pipe_resource templ={.format=FORMAT_RGBA,.width0=4,.height0=4};
static struct winsys_handle handle={.type=WINSYS_HANDLE_TYPE_KMS,.handle=41,.stride=16};
static struct sw_displaytarget *original,*imported;
static void *import_worker(void *unused){(void)unused;unsigned stride=0;
 imported=kms_sw_displaytarget_from_handle(&ws.base,&templ,&handle,&stride);
 assert(imported&&stride==16);return NULL;}
static void *destroy_worker(void *unused){(void)unused;destroy_thread=true;
 kms_sw_displaytarget_destroy(&ws.base,original);
 assert(!pthread_mutex_lock(&control));destroy_done=true;
 assert(!pthread_cond_broadcast(&condition));assert(!pthread_mutex_unlock(&control));return NULL;}
static void unlocked(void){assert(!pthread_mutex_trylock(&ws.bo_lock));assert(!pthread_mutex_unlock(&ws.bo_lock));}
int main(void){alarm(20);assert(!mtx_init(&ws.bo_lock,mtx_plain));list_inithead(&ws.bo_list);
 for(int repeat=0;repeat<64;++repeat){
  struct winsys_handle prime={.type=WINSYS_HANDLE_TYPE_FD,.handle=9,.stride=16};unsigned stride=0;
  original=kms_sw_displaytarget_from_handle(&ws.base,&templ,&prime,&stride);assert(original&&stride==16);
  hook=true;reached=release_ref=destroy_blocked=destroy_done=false;destroy_calls=0;
  pthread_t importing,destroying;assert(!pthread_create(&importing,NULL,import_worker,NULL));
  assert(!pthread_mutex_lock(&control));while(!reached)assert(!pthread_cond_wait(&condition,&control));
  assert(!pthread_mutex_unlock(&control));assert(!pthread_create(&destroying,NULL,destroy_worker,NULL));
  assert(!pthread_mutex_lock(&control));
  while(REPAIRED?!destroy_blocked:!destroy_done)assert(!pthread_cond_wait(&condition,&control));
  if(REPAIRED)assert(!destroy_done);
  release_ref=true;assert(!pthread_cond_broadcast(&condition));assert(!pthread_mutex_unlock(&control));
  assert(!pthread_join(importing,NULL));assert(!pthread_join(destroying,NULL));hook=false;
  assert(REPAIRED);assert(imported==original&&kms_sw_plane(imported)->dt->ref_count==1&&!destroy_calls);
  unlocked();kms_sw_displaytarget_destroy(&ws.base,imported);
  assert(destroy_calls==1&&ws.bo_list.next==&ws.bo_list);unlocked();
 }
 struct winsys_handle prime={.type=WINSYS_HANDLE_TYPE_FD,.handle=9,.stride=16};unsigned stride=123;
 fail_prime=1;assert(!kms_sw_displaytarget_from_handle(&ws.base,&templ,&prime,&stride));unlocked();fail_prime=0;
 fail_seek=1;assert(!kms_sw_displaytarget_from_handle(&ws.base,&templ,&prime,&stride));unlocked();fail_seek=0;
 fail_init=1;assert(!kms_sw_displaytarget_from_handle(&ws.base,&templ,&prime,&stride));unlocked();fail_init=0;
 prime.offset=256;assert(!kms_sw_displaytarget_from_handle(&ws.base,&templ,&prime,&stride));unlocked();
 prime.offset=0;original=kms_sw_displaytarget_from_handle(&ws.base,&templ,&prime,&stride);assert(original);
 prime.offset=256;assert(!kms_sw_displaytarget_from_handle(&ws.base,&templ,&prime,&stride));unlocked();
 assert(kms_sw_plane(original)->dt->ref_count==1);
 prime.offset=64;imported=kms_sw_displaytarget_from_handle(&ws.base,&templ,&prime,&stride);
 assert(imported&&imported!=original&&kms_sw_plane(imported)->dt==kms_sw_plane(original)->dt);
 kms_sw_displaytarget_destroy(&ws.base,original);assert(kms_sw_plane(imported)->dt->ref_count==1);
 kms_sw_displaytarget_destroy(&ws.base,imported);unlocked();assert(ws.bo_list.next==&ws.bo_list);
 mtx_destroy(&ws.bo_lock);puts("serialized_import_final_release_and_prime_boundaries_pass");
}
'''


class MesaKmsLifetimeTests(unittest.TestCase):
    def test_prepared_native_import_final_release_has_asan_use_after_free(self):
        result = compile_run('#define REPAIRED 0\n' + DOUBLES + bodies(False) + MAIN,
                             expect_success=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('AddressSanitizer: heap-use-after-free', result.stderr)

    def test_repaired_native_import_final_release_and_prime_failure_boundaries(self):
        result = compile_run('#define REPAIRED 1\n' + DOUBLES + bodies(True) + MAIN)
        self.assertIn('serialized_import_final_release_and_prime_boundaries_pass', result.stdout)


if __name__ == '__main__':
    unittest.main()
