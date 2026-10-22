#!/usr/bin/env python3
"""Normal input production only, invoked inside Root's original held build CID.

This file creates no Owner/container/VM/lease. Fresh build/recheck is a single
explicit original-Builder helper, never an extra acceptance or a host test.
"""
from pathlib import Path
import argparse
import batch_system_build_runtime_helpers as product


def main():
 p=argparse.ArgumentParser();p.add_argument('--mode',choices=('build','recheck'),required=True)
 p.add_argument('--runtime-profile-sha256');p.add_argument('--previous-sha256');p.add_argument('--normal-link-target',required=True)
 a=p.parse_args();names=['owning_services579_napi']
 if a.mode=='build':
  if a.previous_sha256 is not None or a.runtime_profile_sha256 is None:p.error('actual fresh installed profile required')
  profile=Path('/runtime-profile/owning-services579-installed-profile.json')
  value=__import__('json').loads(profile.read_text());selected=value['product']
  builder=product.Builder('/ohos','/build/helpers',names,runtime_profile=profile,
   runtime_profile_sha256=a.runtime_profile_sha256,product=selected,normal_link_target=a.normal_link_target)
 else:
  if a.previous_sha256 is None or a.runtime_profile_sha256 is not None:p.error('original completed build report SHA required')
  previous=Path('/build/helpers/build.json');value=__import__('json').loads(previous.read_text())
  if value['normal_link_contract']['target']!=a.normal_link_target:p.error('actual normal target differs from build')
  builder=product.ExistingVerifier('/ohos','/recheck/helpers',names,previous,a.previous_sha256,product=value['product'])
 result=builder.run()
 if result['status']!='pass_compile_link_ONLY':raise SystemExit(1)
if __name__=='__main__':main()
