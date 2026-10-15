"""Fixed real AVC functions/frames with ASan/UBSan; never a guest acceptance result."""
import base64
import gzip
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/foundation/multimedia/av_codec/avc_surface_layout'
FIXTURES = Path(__file__).parent / 'fixtures/batch_media'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


source = load('batch_media_layout_source', COMPONENT / 'verify_source.py')
layout, eos = source.layout, source.eos
stack = load('batch_media_layout_stack', REPO / 'patches/lib/apply_component_stack.py')


def originals():
    return {layout.WRAPPER: gzip.decompress(base64.b64decode((FIXTURES.parent /
        'avc_wrapper_original.cpp.gz.b64').read_text().strip(), validate=True)).decode(),
        layout.UTIL: (FIXTURES / 'avc_encoder_util.cpp').read_text()}


def previous(values):
    return {layout.WRAPPER: eos.repaired_source(values[layout.WRAPPER]), layout.UTIL: values[layout.UTIL]}


def repaired(values):
    before = previous(values)
    return {layout.WRAPPER: layout.repair_wrapper(before[layout.WRAPPER]),
            layout.UTIL: layout.repair_util(before[layout.UTIL])}


def materialize(root, values):
    for name, value in values.items():
        path = root / 'foundation/multimedia/av_codec' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)


def validate(root, values, require=False):
    with patch.object(source.subprocess, 'check_output', side_effect=[source.REVISION + '\n',
            values[layout.WRAPPER].encode(), values[layout.UTIL].encode()]):
        return source.validate(root, require)


def cpp_harness():
    values = originals()
    before, after = previous(values), repaired(values)
    harness = (FIXTURES / 'input_harness.cpp').read_text()
    declarations = '''enum COLOR_RANGE {RANGE_UNSPECIFIED=0,RANGE_FULL,RANGE_LIMITED};
enum COLOR_MATRIX {MATRIX_UNSPECIFIED=0,MATRIX_BT709,MATRIX_FCC47_73_682,MATRIX_BT601};
struct RgbImageData {uint8_t *data;int32_t stride;COLOR_MATRIX matrix;COLOR_RANGE range;int32_t bytesPerPixel;};
struct YuvImageData {uint8_t *data;int32_t stride;int32_t uvOffset;};
using errno_t=int;
static int memcpy_s(void *dst,size_t capacity,const void *src,size_t size) {
    if (!dst || !src || size>capacity) return -1;
    memcpy(dst,src,size);return 0;
}
'''
    converter = (FIXTURES / 'avc_encoder_convert.cpp').read_text()
    for matrix in ('BT601_MATRIX','BT709_MATRIX'):
        start = converter.index('static const int16_t '+matrix)
        declarations += converter[start:converter.index('};',start)+2]+'\n'
    for signature in ('inline uint8_t Clip3(', 'int32_t ConvertRgbToYuv420(',
                      'int32_t ConvertNv12ToYuv420(', 'int32_t ConvertNv21ToYuv420('):
        declarations += layout.function(converter, signature)+'\n'
    declarations += layout.function(after[layout.UTIL], 'VideoPixelFormat TranslateVideoPixelFormat(')+'\n'
    declarations += layout.function(before[layout.UTIL], 'VideoPixelFormat TranslateVideoPixelFormat(').replace(
        'TranslateVideoPixelFormat(', 'LegacyTranslateVideoPixelFormat(')+'\n'
    declarations += layout.function(harness, 'class AvcEncoder {').replace('AvcEncoder', 'LegacyEncoder')+';\n'
    for signature in ('int32_t AvcEncoder::GetSurfaceBufferUvOffset(',
                      'int32_t AvcEncoder::GetInputFrameFromAVBuffer(', 'int32_t AvcEncoder::CheckBufferSize('):
        declarations += layout.function(before[layout.WRAPPER], signature).replace('AvcEncoder::',
            'LegacyEncoder::').replace('TranslateVideoPixelFormat(', 'LegacyTranslateVideoPixelFormat(')+'\n'
    for signature in ('int32_t AvcEncoder::GetSurfaceBufferUvOffset(',
                      'int32_t AvcEncoder::GetInputFrameFromAVBuffer(', 'int32_t AvcEncoder::CheckBufferSize(',
                      'void AvcEncoder::SendFrame(', 'void AvcEncoder::ReleaseSurfaceBufferByAVBuffer('):
        declarations += layout.function(after[layout.WRAPPER], signature)+'\n'
    return harness.replace('// @ACTUAL_FUNCTIONS@',declarations)


class BatchMediaAvcSurfaceLayoutTests(unittest.TestCase):
    def test_pinned_source_fixture_integrity(self):
        values = originals()
        for name, expected in source.MANIFEST.items():
            self.assertEqual(hashlib.sha256(values[name].encode()).hexdigest(), expected)
        manifest = __import__('json').loads((FIXTURES / 'manifest.json').read_text())
        for name, expected in manifest['files'].items():
            self.assertEqual(hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest(), expected['sha256'])

    def test_two_complete_states_idempotent_application_and_eos_overlay(self):
        values=originals()
        for start in (values, {layout.WRAPPER:eos.repaired_source(values[layout.WRAPPER],False),layout.UTIL:values[layout.UTIL]},
                      previous(values), repaired(values)):
            with self.subTest(state=hashlib.sha256(start[layout.WRAPPER].encode()).hexdigest()), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);materialize(root,start)
                # The earlier stack is run until complete; the later exact overlay is recognized and skipped.
                for _ in range(2):
                    actual=(root/'foundation/multimedia/av_codec'/layout.WRAPPER).read_text()
                    with patch.object(eos.subprocess,'check_output',side_effect=[eos.REVISION+'\n',values[layout.WRAPPER].encode()]):
                        overlay=False
                        try: overlay=eos.validate(root,True,True)
                        except ValueError: pass
                    if not overlay: stack.run(COMPONENT.parent/'avc_eos',root)
                    self.assertEqual(validate(root,values),overlay)
                    stack.run(COMPONENT,root)
                    self.assertTrue(validate(root,values,True))
                    self.assertEqual({name:(root/'foundation/multimedia/av_codec'/name).read_text()
                                      for name in values},repaired(values))

    def test_unknown_partial_and_linked_inputs_rejected_without_writes(self):
        values=originals();before=previous(values);after=repaired(values)
        for state in ({layout.WRAPPER:after[layout.WRAPPER],layout.UTIL:before[layout.UTIL]},
                      {layout.WRAPPER:before[layout.WRAPPER],layout.UTIL:after[layout.UTIL]},
                      {layout.WRAPPER:after[layout.WRAPPER]+'\n// user edit\n',layout.UTIL:after[layout.UTIL]}):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);materialize(root,state)
                with self.assertRaises(ValueError): validate(root,values)
                self.assertEqual({n:(root/'foundation/multimedia/av_codec'/n).read_text() for n in values},state)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);materialize(root,before)
            target=root/'foundation/multimedia/av_codec'/layout.UTIL
            saved=root/'saved-util.cpp';target.rename(saved);target.symlink_to(saved)
            with self.assertRaises(ValueError): validate(root,values)
            self.assertTrue(target.is_symlink());self.assertEqual(saved.read_text(),before[layout.UTIL])

    def test_bad_patch_validates_entire_stack_before_any_write(self):
        values=originals();before=previous(values)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);materialize(root,before)
            private=root/'component';shutil.copytree(COMPONENT,private)
            numbered=next(private.glob('0001-*.patch'))
            value=numbered.read_text();self.assertIn('-        case GraphicPixelFormat::GRAPHIC_PIXEL_FMT_YCBCR_P010:',value)
            numbered.write_text(value.replace('-        case GraphicPixelFormat::GRAPHIC_PIXEL_FMT_YCBCR_P010:',
                '-        case GraphicPixelFormat::UNKNOWN_PINNED_FORMAT:'))
            with self.assertRaises(ValueError):stack.run(private,root)
            self.assertEqual({n:(root/'foundation/multimedia/av_codec'/n).read_text() for n in values},before)

    def test_real_input_functions_and_converter_pixels_with_sanitizers(self):
        compiler=shutil.which('clang++')
        if compiler is None:self.skipTest('clang++ needed for real-function sanitizer check')
        with tempfile.TemporaryDirectory(prefix='batch-media-avc-layout-') as directory:
            root=Path(directory);candidate=root/'actual-input-functions.cpp';binary=root/'actual-input-functions'
            candidate.write_text(cpp_harness())
            command=[compiler,'-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                     '-fno-sanitize-recover=all','-g',str(candidate),'-o',str(binary)]
            built=subprocess.run(command,text=True,capture_output=True)
            self.assertEqual(built.returncode,0,built.stdout+built.stderr)
            result=subprocess.run([str(binary)],text=True,capture_output=True,
                env={**os.environ,'ASAN_OPTIONS':('detect_leaks=1' if sys.platform.startswith('linux') else 'detect_leaks=0'),'UBSAN_OPTIONS':'halt_on_error=1'})
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('actual_function_checks=',result.stdout)
            print(result.stdout.strip())


if __name__=='__main__':unittest.main(verbosity=2)
