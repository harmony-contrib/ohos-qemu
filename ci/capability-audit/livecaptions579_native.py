"""Finite genuine OHOS32 inference recipe for the original root dependency builder.

Returns source pins, exact native configure/build/install argv and data-copy
requirements. Never downloads, executes, constructs a process or owns resources.
The admitted existing HAR supplies arm64-v8a/x86_64; ARMv7 is a real new build.
"""
from pathlib import Path
from livecaptions579_arm32_sources import RPATH_SOURCE, RPATH_SOURCE_SHA, RPATH_PATCH

SHERPA = '419f7fea0a9a3f7b047dee53ad7da266767a425f'
NODE_ADDON = 'c679f6f4c9dc6bf9fc0d99cbe5982bd24a5e2c7b'
ORT = {'url':'https://huggingface.co/csukuangfj/onnxruntime-libs/resolve/c5ad3699dbc2902c93b0128a1e427201cec95df4/onnxruntime-ohos-armeabi-v7a-1.16.3.zip',
       'sha256':'cecbae2a8404a26ad1595f3ff0886e2e1353933c0883e2dfa846f063dfe34902','bytes':5252542}
PREFIX = 'harmony-os/SherpaOnnxHar/sherpa_onnx'
NAPI_SOURCES = ('audio-tagging.cc','keyword-spotting.cc','non-streaming-asr.cc',
    'non-streaming-speaker-diarization.cc','non-streaming-speech-denoiser.cc','non-streaming-tts.cc',
    'punctuation.cc','sherpa-onnx-node-addon-api.cc','speaker-identification.cc',
    'spoken-language-identification.cc','streaming-asr.cc','utils.cc','vad.cc','wave-reader.cc','wave-writer.cc')


def recipe(abi, paths):
    if abi!='armeabi-v7a' or set(paths)!={'source','sdk_native','ort','c_api_build','install','napi_build','node_addon'}:
        raise ValueError('one explicit original-builder OHOS32 recipe required')
    p={name:Path(value) for name,value in paths.items()}
    if any(not value.is_absolute() or '..' in value.parts for value in p.values()):
        raise ValueError('original owner must supply exact private absolute source/SDK/build paths')
    sdk=p['sdk_native']; cmake=str(sdk/'build-tools/cmake/bin/cmake')
    toolchain='-DCMAKE_TOOLCHAIN_FILE='+str(sdk/'build/cmake/ohos.toolchain.cmake')
    arch=['-DOHOS_ARCH=armeabi-v7a',toolchain,'-DCMAKE_BUILD_TYPE=Release',
          '-DCMAKE_C_FLAGS=-mfloat-abi=hard','-DCMAKE_CXX_FLAGS=-mfloat-abi=hard',
          '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DFETCHCONTENT_UPDATES_DISCONNECTED=ON',
          '-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON','-DCMAKE_INSTALL_RPATH=$ORIGIN']
    # Initial archive extraction remains enabled. The original owned worker has
    # network=none, all twelve upstream-SHA archives staged at CMAKE_SOURCE_DIR,
    # and trace replay rejects any unseen dependency/declaration/source path.
    capi=[cmake,'--trace-expand','--trace-format=json-v1',
        '--trace-redirect='+str(p['c_api_build'].parent/'c-api-trace.jsonl'),
        '-S',str(p['source']),'-B',str(p['c_api_build']),*arch,
        '-DSHERPA_ONNX_ENABLE_TTS=ON','-DSHERPA_ONNX_ENABLE_SPEAKER_DIARIZATION=ON',
        '-DSHERPA_ONNX_ENABLE_BINARY=OFF','-DBUILD_PIPER_PHONMIZE_EXE=OFF',
        '-DBUILD_PIPER_PHONMIZE_TESTS=OFF','-DBUILD_ESPEAK_NG_EXE=OFF','-DBUILD_ESPEAK_NG_TESTS=OFF',
        '-DBUILD_SHARED_LIBS=ON','-DSHERPA_ONNX_ENABLE_PYTHON=OFF','-DSHERPA_ONNX_ENABLE_TESTS=OFF',
        '-DSHERPA_ONNX_ENABLE_CHECK=OFF','-DSHERPA_ONNX_ENABLE_PORTAUDIO=OFF','-DSHERPA_ONNX_ENABLE_JNI=OFF',
        '-DSHERPA_ONNX_ENABLE_C_API=ON','-DCMAKE_INSTALL_PREFIX='+str(p['install'])]
    native=p['source']/PREFIX/'src/main/cpp'
    napi=[cmake,'--trace-expand','--trace-format=json-v1',
          '--trace-redirect='+str(p['napi_build'].parent/'napi-trace.jsonl'),
          '-S',str(native),'-B',str(p['napi_build']),*arch,
          '-DFETCHCONTENT_SOURCE_DIR_NODE_ADDON_API='+str(p['node_addon']),
          '-DFETCHCONTENT_FULLY_DISCONNECTED=ON']
    return {'schema':'source-only-livecaptions579-ohos32/v1','abi':abi,
        'sources':{'sherpa':{'url':'https://github.com/k2-fsa/sherpa-onnx.git','commit':SHERPA},
                   'node_addon':{'url':'https://github.com/nodejs/node-addon-api.git','commit':NODE_ADDON,
                     'patch':PREFIX+'/src/main/cpp/my-patch.diff','apply_once_in_fresh_private_copy':True}},
        'ort':dict(ORT),'upstream_recipe':'build-ohos-armeabi-v7a.sh',
        'c_api_source_adaptation':{'path':RPATH_SOURCE,'before_sha256':RPATH_SOURCE_SHA,
            'patch':RPATH_PATCH,'purpose':'Keep origin-relative RPATH; never append private ORT link directory'},
        'environment':{'SHERPA_ONNXRUNTIME_LIB_DIR':str(p['ort']/'lib'),
                       'SHERPA_ONNXRUNTIME_INCLUDE_DIR':str(p['ort']/'include')},
        'commands':{'c_api_configure':capi,'c_api_build':[cmake,'--build',str(p['c_api_build']),'--parallel','2'],
            'c_api_install':[cmake,'--install',str(p['c_api_build']),'--strip'],
            'napi_configure_after_actual_c_api_copy':napi,
            'napi_build':[cmake,'--build',str(p['napi_build']),'--target','sherpa_onnx','--parallel','2']},
        'copy_before_napi':{str(native/'libs/armeabi-v7a/libsherpa-onnx-c-api.so'):str(p['install']/'lib/libsherpa-onnx-c-api.so'),
                            str(native/'libs/armeabi-v7a/libonnxruntime.so'):str(p['ort']/'lib/libonnxruntime.so')},
        'napi_sources':[str(native/name) for name in NAPI_SOURCES],
        'target':'sherpa_onnx','platform_links':['libace_napi.z.so','libhilog_ndk.z.so','librawfile.z.so'],
        'har_abi_change':{'file':PREFIX+'/build-profile.json5','add_exact_abi_filter':'armeabi-v7a',
                         'preserve_existing':['arm64-v8a','x86_64']},
        'package_outputs':{'libs/armeabi-v7a/libsherpa_onnx.so':'actual sherpa_onnx target output',
            'libs/armeabi-v7a/libsherpa-onnx-c-api.so':str(p['install']/'lib/libsherpa-onnx-c-api.so'),
            'libs/armeabi-v7a/libonnxruntime.so':str(p['ort']/'lib/libonnxruntime.so'),
            'libs/armeabi-v7a/libc++_shared.so':'same admitted OHOS SDK armeabi-v7a runtime; exact actual path+SHA receipt'},
        'required_receipts':['original source HEAD and every used source SHA','actual SDK/compiler/toolchain SHA and argv',
            'every CMake transitive source/download URL+revision+SHA, original license/notice and offline cache admission',
            'node-addon-api original+patched SHA, upstream my-patch.diff SHA and actual patch argv/exit/raw',
            'every command stdout/stderr/exit/timeout; real copied source/output bytes',
            'actual 32-bit ARM OHOS ELF/float ABI/SONAME/DT_NEEDED/undefined-export and complete dependency closure',
            'full native dependency licenses/notices, including enabled TTS/diarization dependencies',
            'actual assembled HAR SHA, exact same public ETS APIs, true compiled native NAPI symbols',
            'actual root signed provider HAP/new package SHA and new guest native maps/loading/inference'],
        'feature_note':'Keep official full C API features: unchanged actual HAR NAPI links TTS/diarization exports. Disabling them without a separately reviewed source/export delta would produce a false ABI recipe.',
        'runtime_validated':False,'first_artifact_gate_passed':False}
