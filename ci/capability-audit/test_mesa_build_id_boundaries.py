"""Actual historical note callback with synthetic ELF mappings under ASAN/UBSAN."""
import base64
import gzip
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/third_party/mesa3d/build_id_boundaries'
SPEC = importlib.util.spec_from_file_location('mesa_build_id', COMPONENT / 'apply_mesa_build_id.py')
BACKPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BACKPORT)
PREPARED = gzip.decompress(base64.b64decode(
    Path(__file__).with_name('fixtures').joinpath('mesa_build_id_prepared.c.gz.b64').read_bytes()))

DOUBLES = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ElfW(type) Elf64_##type
#define NT_GNU_BUILD_ID 3
#define PT_LOAD 1
#define PT_NOTE 4
#define ALIGN_POT(x,a) (((x)+(a)-1)&~((a)-1))
typedef struct {uint32_t n_namesz,n_descsz,n_type;} Elf64_Nhdr;
typedef struct {uint32_t p_type;uintptr_t p_vaddr;size_t p_filesz;} Elf64_Phdr;
struct dl_phdr_info {uintptr_t dlpi_addr;unsigned dlpi_phnum;const Elf64_Phdr *dlpi_phdr;};
'''

HARNESS = r'''
static const struct build_id_note *Find(unsigned char *bytes,size_t length) {
 Elf64_Phdr headers[2]={{PT_LOAD,0,0},{PT_NOTE,0,length}};
 struct dl_phdr_info info={(uintptr_t)bytes,2,headers};
 struct callback_data data={bytes,NULL};
 int result=build_id_find_nhdr_callback(&info,sizeof(info),&data);
 assert(result==0 || result==1);
 assert((result==1)==(data.note!=NULL));
 return data.note;
}
static void Header(unsigned char *bytes,uint32_t names,uint32_t desc,uint32_t type) {
 Elf64_Nhdr header={names,desc,type};memcpy(bytes,&header,sizeof(header));
}
'''


def native(source):
    text = source.decode()
    start = text.index('struct build_id_note {')
    end = text.index('\nconst struct build_id_note *\nbuild_id_find_nhdr_for_addr')
    return DOUBLES + text[start:end] + HARNESS


class MesaBuildIdTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(hashlib.sha256(PREPARED).hexdigest(), BACKPORT.ORIGINAL_SHA)

    def prepare(self, root):
        target = root / BACKPORT.RELATIVE
        target.parent.mkdir(parents=True)
        target.write_bytes(PREPARED)
        (root / 'VERSION').write_text('21.3.3\n')
        return target

    def repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = self.prepare(root)
            BACKPORT.apply(root, COMPONENT / BACKPORT.PATCH_NAME)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), BACKPORT.REPAIRED_SHA)
            return target.read_bytes()

    def test_actual_prepared_callback_reads_past_final_note(self):
        source = native(PREPARED) + r'''
int main(void){unsigned char *bytes=calloc(1,20);assert(bytes);
 Header(bytes,4,4,1);memcpy(bytes+12,"OHOS",4);
 assert(!Find(bytes,20));free(bytes);}
'''
        # The historical source has an uncategorized pointer/integer warning.
        # Preserve its exact callback and allow that warning for reproduction.
        with tempfile.TemporaryDirectory() as directory:
            cpp, binary = Path(directory) / 'original.c', Path(directory) / 'original'
            cpp.write_text(source)
            subprocess.run([shutil.which('clang'), '-std=gnu11', '-Wall', '-Wextra',
                '-Wno-unused-parameter', '-fsanitize=address,undefined', '-g',
                str(cpp), '-o', str(binary)], check=True, capture_output=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('AddressSanitizer: heap-buffer-overflow', result.stderr)

    def test_repaired_callback_real_notes_truncation_extremes_and_alignment(self):
        result = compile_run(native(self.repaired()) + r'''
int main(void){
 unsigned cases=0;
 for(size_t length=0;length<=128;++length){
  unsigned char *bytes=calloc(1,length?length:1);assert(bytes);
  if(length>=12){Header(bytes,UINT32_MAX,UINT32_MAX,3);assert(!Find(bytes,length));++cases;
   Header(bytes,0,UINT32_MAX,3);assert(!Find(bytes,length));++cases;}
  free(bytes);
 }
 for(size_t length=0;length<=36;++length){
  unsigned char *bytes=calloc(1,length?length:1);assert(bytes);
  unsigned char valid[36]={0};Header(valid,4,20,3);memcpy(valid+12,"GNU",4);
  for(unsigned n=0;n<20;++n)valid[16+n]=(unsigned char)(n+1);
  memcpy(bytes,valid,length);
  const struct build_id_note *note=Find(bytes,length);
  assert((note!=NULL)==(length==36));
  if(note)assert(note->nhdr.n_descsz==20 && !memcmp(note->build_id,valid+16,20));
  free(bytes);++cases;
 }
 unsigned char chain[60]={0};
 // The pinned musl crtbrand uses an eight-byte padded OHOS name and type 1.
 Header(chain,8,4,1);memcpy(chain+12,"OHOS",5);chain[20]=1;
 Header(chain+24,4,20,3);memcpy(chain+36,"GNU",4);chain[40]=0x9b;
 assert((const unsigned char *)Find(chain,sizeof(chain))==chain+24);++cases;
 // Header-only notes advance by their header size; a zero desc is no build-ID.
 memset(chain,0,sizeof(chain));Header(chain,0,0,1);
 Header(chain+12,4,4,3);memcpy(chain+24,"GNU",4);chain[28]=0x13;
 assert((const unsigned char *)Find(chain,32)==chain+12);++cases;
 Header(chain+12,4,0,3);assert(!Find(chain,32));++cases;
 Header(chain+12,4,4,3);memcpy(chain+24,"BAD",4);assert(!Find(chain,32));++cases;
 // Non-word descriptor lengths require their complete four-byte ELF padding.
 memset(chain,0,sizeof(chain));Header(chain,4,1,3);memcpy(chain+12,"GNU",4);
 assert(!Find(chain,17));assert(Find(chain,20));++cases;
 // An unaligned note must never escape as a struct that callers dereference.
 unsigned char unaligned[24]={0};Header(unaligned+1,4,4,3);memcpy(unaligned+13,"GNU",4);
 assert(!Find(unaligned+1,20));++cases;
 // Bounded arbitrary note sizes must not read outside the PT_NOTE segment.
 uint32_t seed=0x84d193a7;
 for(unsigned n=0;n<20000;++n){
  seed=seed*1664525u+1013904223u;size_t length=12+(seed%117);
  unsigned char *bytes=calloc(1,length);assert(bytes);
  seed=seed*1664525u+1013904223u;uint32_t names=seed;
  seed=seed*1664525u+1013904223u;uint32_t desc=seed;
  Header(bytes,names,desc,n%4);assert(!Find(bytes,length));free(bytes);++cases;
 }
 printf("bounded_ELF_note_callback_cases=%u\n",cases);
}
''')
        self.assertIn('bounded_ELF_note_callback_cases=20277', result.stdout)

    def test_exact_apply_repeat_nested_checkout_unknown_edit_and_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            outer = Path(directory)
            subprocess.run(['git', 'init', '-q', str(outer)], check=True)
            root = outer / 'extracted'
            target = self.prepare(root)
            BACKPORT.apply(root, COMPONENT / BACKPORT.PATCH_NAME)
            repaired = target.read_bytes()
            BACKPORT.apply(root, COMPONENT / BACKPORT.PATCH_NAME)
            self.assertEqual(target.read_bytes(), repaired)
            target.write_bytes(repaired + b'\n// caller edit\n')
            edited = target.read_bytes()
            with self.assertRaisesRegex(ValueError, 'preserving'):
                BACKPORT.apply(root, COMPONENT / BACKPORT.PATCH_NAME)
            self.assertEqual(target.read_bytes(), edited)
            target.unlink()
            outside = outer / 'caller.c'
            outside.write_bytes(PREPARED)
            target.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                BACKPORT.apply(root, COMPONENT / BACKPORT.PATCH_NAME)
            self.assertEqual(outside.read_bytes(), PREPARED)


if __name__ == '__main__':
    unittest.main()
