"""Explicit normal-product NAPI recipe; existing selected GN anchors only.

Parent production registers this single recipe explicitly. No HELPERS mutation,
new provider target, alternate SDK ABI, disabled CFI or fabricated object proof.
Each product must supply its actual normal PIE target and installed profile.
"""
from pathlib import Path
HERE=Path(__file__).resolve().parent
ANCHORS=(
 dict(graph='obj/base/hiviewdfx/hidumper/services/hidumper_client.ninja',
  object='obj/base/hiviewdfx/hidumper/services/native/src/hidumper_client/dump_manager_client.o',
  source='base/hiviewdfx/hidumper/services/native/src/dump_manager_client.cpp',
  header='base/hiviewdfx/hidumper/interfaces/native/innerkits/include/dump_manager_client.h'),
 dict(graph='obj/base/security/device_security_level/interfaces/inner_api/dslm_sdk.ninja',
  object='obj/base/security/device_security_level/interfaces/inner_api/src/standard/dslm_sdk/device_security_info.o',
  source='base/security/device_security_level/interfaces/inner_api/src/standard/device_security_info.cpp',
  header='base/security/device_security_level/interfaces/inner_api/include/device_security_info.h'),
 dict(graph='obj/base/security/device_auth/services/deviceauth_sdk.ninja',
  object='obj/base/security/device_auth/frameworks/src/deviceauth_sdk/ipc_sdk.o',
  source='base/security/device_auth/frameworks/src/ipc_sdk.c',
  header='base/security/device_auth/interfaces/inner_api/device_auth.h'))

def helper_recipes():
 return {'owning_services579_napi':dict(
  fixture='../owning_services579/native/ServicesNative.cpp',source_file=str(HERE/'owning_services579/native/ServicesNative.cpp'),
  kind='shared_napi',output_basename='libowning_services579.so',anchors=[dict(a) for a in ANCHORS],
  libraries=['hiviewdfx/hidumper/libhidumper_client.z.so','security/dataclassification/libdata_transit_mgr.z.so',
   'security/device_security_level/libdslm_sdk.z.so','security/device_auth/libdeviceauth_sdk.z.so',
   'arkui/napi/libace_napi.z.so','communication/ipc/libipc_single.z.so'],
  headers=[a['header'] for a in ANCHORS]+['base/security/dataclassification/interfaces/inner_api/datatransmitmgr/include/dev_slinfo_mgr.h'],
  extra_includes=['base/hiviewdfx/hidumper/interfaces/native/innerkits/include',
   'base/security/dataclassification/interfaces/inner_api/datatransmitmgr/include',
   'base/security/device_security_level/interfaces/inner_api/include','base/security/device_auth/interfaces/inner_api',
   'foundation/arkui/napi/interfaces/kits'])}
