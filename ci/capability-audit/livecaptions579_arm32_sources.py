"""Fixed upstream inputs for a genuine OHOS32 build, never a build result.

Archive SHA256 values are the actual declarations in sherpa v1.11.2 CMake.
No mirror/main URL or JSON-supplied compiler recipe is accepted.
"""
SHERPA = ('https://github.com/k2-fsa/sherpa-onnx.git',
          '419f7fea0a9a3f7b047dee53ad7da266767a425f', 'refs/tags/v1.11.2')
NODE = ('https://github.com/nodejs/node-addon-api.git',
        'c679f6f4c9dc6bf9fc0d99cbe5982bd24a5e2c7b',
        'c679f6f4c9dc6bf9fc0d99cbe5982bd24a5e2c7b')
BASE_HAR_SHA = 'd196941c571f4bd7dd98e6c03097aa4873b9a934ceced64800fb85b25892e6a0'
BASE_NOTICES_SHA = '23a28ff194d9611ce38979598b16923b6a0d0f205dd3d0e2f5a1513e52c7858b'
ORT_SHA = 'cecbae2a8404a26ad1595f3ff0886e2e1353933c0883e2dfa846f063dfe34902'
ORT_BYTES = 5252542
LIBS = ('libc++_shared.so', 'libonnxruntime.so', 'libsherpa-onnx-c-api.so', 'libsherpa_onnx.so')
# FetchContent name -> local archive basename, primary URL, upstream SHA256.
DEPENDENCIES = {
 'kaldi_native_fbank': ('kaldi-native-fbank-1.21.1.tar.gz',
  'https://github.com/csukuangfj/kaldi-native-fbank/archive/refs/tags/v1.21.1.tar.gz',
  '37c1aa230b00fe062791d800d8fc50aa3de215918d3dce6440699e67275d859e'),
 'kaldi_decoder': ('kaldi-decoder-0.2.6.tar.gz',
  'https://github.com/k2-fsa/kaldi-decoder/archive/refs/tags/v0.2.6.tar.gz',
  'b13c78b37495cafc6ef3f8a7b661b349c55a51abbd7f7f42f389408dcf86a463'),
 'simple-sentencepiece': ('simple-sentencepiece-0.7.tar.gz',
  'https://github.com/pkufool/simple-sentencepiece/archive/refs/tags/v0.7.tar.gz',
  '1748a822060a35baa9f6609f84efc8eb54dc0e74b9ece3d82367b7119fdc75af'),
 'websocketpp': ('websocketpp-b9aeec6eaf3d5610503439b4fae3581d9aff08e8.zip',
  'https://github.com/zaphoyd/websocketpp/archive/b9aeec6eaf3d5610503439b4fae3581d9aff08e8.zip',
  '1385135ede8191a7fbef9ec8099e3c5a673d48df0c143958216cd1690567f583'),
 'asio': ('asio-asio-1-24-0.tar.gz',
  'https://github.com/chriskohlhoff/asio/archive/refs/tags/asio-1-24-0.tar.gz',
  'cbcaaba0f66722787b1a7c33afe1befb3a012b5af3ad7da7ff0f6b8c9b7a8a5b'),
 'espeak_ng': ('espeak-ng-f6fed6c58b5e0998b8e68c6610125e2d07d595a7.zip',
  'https://github.com/csukuangfj/espeak-ng/archive/f6fed6c58b5e0998b8e68c6610125e2d07d595a7.zip',
  '70cbf4050e7a014aae19140b05e57249da4720f56128459fbe3a93beaf971ae6'),
 'piper_phonemize': ('piper-phonemize-78a788e0b719013401572d70fef372e77bff8e43.zip',
  'https://github.com/csukuangfj/piper-phonemize/archive/78a788e0b719013401572d70fef372e77bff8e43.zip',
  '89641a46489a4898754643ce57bda9c9b54b4ca46485fdc02bf0dc84b866645d'),
 'cppjieba': ('cppjieba-sherpa-onnx-2024-04-19.tar.gz',
  'https://github.com/csukuangfj/cppjieba/archive/refs/tags/sherpa-onnx-2024-04-19.tar.gz',
  '03e5264687f0efaef05487a07d49c3f4c0f743347bfbf825df4b30cc75ac5288'),
 'hclust_cpp': ('hclust-cpp-2024-09-29.tar.gz',
  'https://github.com/csukuangfj/hclust-cpp/archive/refs/tags/2024-09-29.tar.gz',
  'abab51448a3cb54272aae07522970306e0b2cc6479d59d7b19e7aee4d6cedd33'),
 'kaldifst': ('kaldifst-1.7.11.tar.gz',
  'https://github.com/k2-fsa/kaldifst/archive/refs/tags/v1.7.11.tar.gz',
  'b43b3332faa2961edc730e47995a58cd4e22ead21905d55b0c4a41375b4a525f'),
 'openfst': ('openfst-sherpa-onnx-2024-06-19.tar.gz',
  'https://github.com/csukuangfj/openfst/archive/refs/tags/sherpa-onnx-2024-06-19.tar.gz',
  '5c98e82cc509c5618502dde4860b8ea04d843850ed57e6d6b590b644b268853d'),
 'eigen': ('eigen-3.4.0.tar.gz',
  'https://gitlab.com/libeigen/eigen/-/archive/3.4.0/eigen-3.4.0.tar.gz',
  '8586084f71f9bde545ee7fa6d00288b264a2b7ac3607b974e54d13e7162c1c72'),
}
OWNER_SOURCE_SHA = '02dcc35db074c625cb070ca7af29446ba917e585d45cb015fc86ff4b8863e4eb'

# Exact bounded build-source adaptation. The upstream root enables automatic
# install-RPATH link-directory appends, which would embed the private ORT path.
# Only this project-root assignment changes; dependency sources remain exact.
RPATH_SOURCE = 'CMakeLists.txt'
RPATH_SOURCE_SHA = '8a8e18c23dbb35130b0b49699e600c62a7cb4334c0943565a5d4ed27c8017f94'
RPATH_BEFORE = '  set(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)'
RPATH_AFTER = '  set(CMAKE_INSTALL_RPATH_USE_LINK_PATH FALSE)'
RPATH_PATCH = """--- a/CMakeLists.txt
+++ b/CMakeLists.txt
@@ -58,7 +58,7 @@
 if(NOT WIN32)
   set(CMAKE_SKIP_BUILD_RPATH FALSE)
   set(BUILD_RPATH_USE_ORIGIN TRUE)
-  set(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)
+  set(CMAKE_INSTALL_RPATH_USE_LINK_PATH FALSE)
 endif()
 
 if(NOT APPLE)
"""
