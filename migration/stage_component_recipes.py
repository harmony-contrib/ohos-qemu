#!/usr/bin/env python3
"""Stage component-owned adaptation recipes and an exact reconstruction index.

Only tracked files are admitted. Cross-component diffs are split at file diff
boundaries; ordered pieces reproduce the original patch bytes exactly. This
prepares source candidates and does not publish or execute an adaptation.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import subprocess

LIB_OWNERS = {
    'admin_provider.py': 'applications_admin_provisioning',
    'avc_artifacts.py': 'multimedia_av_codec',
    'calendar_lifecycle579.py': 'applications_calendar_data',
    'calendar_provider.py': 'applications_calendar_data',
    'communicationsetting_provider.py': 'applications_hap',
    'contacts_theme_providers.py': 'applications_hap',
    'dialog_providers579.py': 'applications_hap',
    'init_account_tables.py': 'startup_init',
    'kernel_evidence.py': 'device_qemu',
    'livecaptions579_arm32_contract.py': 'applications_hap',
    'livecaptions579_arm32_sources.py': 'applications_hap',
    'livecaptions579_inputs.py': 'applications_hap',
    'livecaptions579_native.py': 'applications_hap',
    'livecaptions_provider.py': 'applications_hap',
    'locationdialog_provider.py': 'applications_hap',
    'mms_provider.py': 'applications_mms',
    'number_identity_provider.py': 'applications_number_identity',
    'permission_profile.py': 'security_access_token',
    'preinstall_selection.py': 'bundlemanager_bundle_framework',
    'privacycenter_provider.py': 'applications_hap',
    'qemu_hap_prefix579.py': 'applications_hap',
    'qemu_ui_providers.py': 'vendor_ohemu',
    'sceneboard_assets.py': 'applications_hap',
    'sceneboard_profile.py': 'vendor_ohemu',
    'systemui_provider.py': 'applications_systemui',
    **{n + '_features.py': 'vendor_ohemu' for n in ('audio', 'camera', 'graphics', 'network', 'sensor')},
    'device_contract.py': 'vendor_ohemu',
    **{n: 'build' for n in (
        'apply_component_dir.sh', 'apply_component_stack.py', 'apply_device_type.sh',
        'apply_exact_component.py', 'apply_patch.sh', 'exact_source_states.py',
        'guarded_source_vector579.py', 'package_validation.py',
        'qemu_preserve_source_times579.py', 'qemu_source_prefix579.py')},
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_owner(path, projects):
    matches = [p for p in projects if path == p['path'] or path.startswith(p['path'] + '/')]
    return max(matches, key=lambda p: len(p['path']))['name'] if matches else None


def fallback_owner(name, projects):
    if '/sources/' in name:
        embedded_owner = source_owner(name.split('/sources/', 1)[1], projects)
        if embedded_owner:
            return embedded_owner
    relative = name.removeprefix('patches/')
    if relative.startswith('lib/'):
        return LIB_OWNERS.get(Path(name).name)
    if relative.startswith('assets/'):
        return 'applications_hap'
    if relative.startswith('resources/knowledge/'):
        return 'applications_calendar_data'
    if relative == 'README.md':
        return 'build'
    for profile in ('phone', '2in1'):
        if relative in (profile + '/README.md', profile + '/apply.sh'):
            return 'vendor_ohemu'
        if relative.startswith(profile + '/product_profile/'):
            return 'vendor_ohemu'
        if relative.startswith(profile + '/sceneboard_runtime/'):
            if name.endswith('0001-use-screen-unlocked-event.patch'):
                return 'theme_screenlock_mgr'
            if name.endswith('0002-cem-publish-user-id-param.patch'):
                return 'notification_common_event_service'
            return 'applications_hap'
    relative = re.sub(r'^(common|phone|2in1)/', '', relative)
    relative = relative.replace('kernel/linux/linux_6_6/', 'kernel/linux/linux-6.6/')
    relative = relative.replace('base/location/location_ndk/', 'base/location/location/')
    if relative.startswith(('applications/standard/callsetting/', 'applications/standard/communicationsetting/')):
        return 'applications_hap'
    if relative.startswith('standard_vpn/'):
        group = relative.split('/')[2] if relative.startswith('standard_vpn/components/') else ''
        return {'code_sign':'security_code_signature', 'device_qemu_kernel':'device_qemu',
            'graphic_2d_egl':'graphic_graphic_2d', 'linux_security':'kernel_linux_6.6',
            'musl_uapi':'third_party_musl', 'qemu_mesa':'device_qemu',
            'qemu_vulkan':'device_qemu', 'vendor_product':'vendor_ohemu',
            'vpn_dialog':'applications_hap', 'xpm':'kernel_linux_common_modules',
            'validate':'build', 'README.md':'build'}.get(group, 'build')
    arm = 'device/qemu/armv7a_product/components/'
    if relative.startswith(arm):
        return {'appspawn_cleanup':'startup_appspawn', 'build_whitelist':'build',
            'compact_child_args':'ability_ability_runtime', 'device_qemu':'device_qemu',
            'kernel':'device_qemu', 'libvpx':'third_party_libvpx',
            'mesa3d':'third_party_mesa3d', 'vendor_ohemu':'vendor_ohemu',
            'README.md':'device_qemu'}.get(relative[len(arm):].split('/')[0])
    if relative.startswith('web/arkweb/'):
        group=relative.split('/')[2]
        return {'m144_adapter_header_format':'arkweb_web_webview',
            'm144_angle_includes':'chromium_arkweb', 'm144_avc_encoder':'chromium_src',
            'm144_core_build':'chromium_src', 'm144_core_package':'chromium_arkweb',
            'm144_media_document_binding':'chromium_arkweb',
            'm144_private_contract':'chromium_arkweb',
            'm144_swiftshader':'chromium_third_party_swiftshader',
            'm144_v8_shared':'chromium_src', 'm144_webrtc_thread_id':'chromium_third_party_webrtc',
            'm144_window_contract':'chromium_arkweb'}.get(group)
    return source_owner(relative, projects)


def patch_parts(data):
    # Diff boundaries, not hunks: every segment remains a complete file diff.
    matches=list(re.finditer(rb'^diff --git a/[^\n]+ b/([^\n]+)\n', data, re.M))
    if not matches:
        matches=list(re.finditer(rb'^--- [^\n]+\n\+\+\+ b/([^\n\t]+)[^\n]*\n', data, re.M))
    if not matches:
        raise ValueError('Unsupported patch format')
    return [(m.group(1).decode(), data[0 if i == 0 else m.start():
                matches[i+1].start() if i+1 < len(matches) else len(data)])
            for i,m in enumerate(matches)]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--catalog',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--index',type=Path,required=True)
    args=ap.parse_args()
    catalog=json.loads(args.catalog.read_text())
    projects=catalog['checkouts']['ohos'] + [dict(name=p['name'],path=i['path'])
        for p in catalog['repositories'] for i in p['inputs'] if i['tree']=='external']
    repos={p['name']:p for p in catalog['repositories']}
    entries=[]; staged=collections.defaultdict(list); errors=[]
    tracked=subprocess.check_output(['git','ls-files','--stage','-z','patches']).decode().split('\0')
    if subprocess.check_output(['git','rev-parse','--show-object-format'],text=True).strip()!='sha1':
        raise ValueError('This source journal expects SHA-1 Git object IDs')
    if args.output.exists():
        raise ValueError('Fresh output directory required')
    for record in filter(None,tracked):
        meta,name=record.split('\t',1);mode,oid,stage=meta.split()
        if stage!='0': raise ValueError('Unmerged input: '+name)
        path=Path(name);data=path.read_bytes()
        computed=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if computed!=oid:
            raise ValueError('Uncommitted input requires review: '+name)
        fallback=fallback_owner(name,projects)
        pieces=[]
        if name.endswith('.patch'):
            tree=catalog['checkouts']['arkweb'] if '/web/arkweb/' in name else projects
            for target,part in patch_parts(data):
                owner=source_owner(target,tree) or fallback
                if name.startswith('patches/common/third_party/mesa3d/') and target.startswith('src/'):
                    owner='qemu_dep_mesa3d_21_3'
                if pieces and pieces[-1][0]==owner: pieces[-1]=(owner,pieces[-1][1]+part)
                else: pieces.append((owner,part))
        else: pieces=[(fallback,data)]
        if any(owner not in repos for owner,_ in pieces):
            errors.append(name); continue
        assert b''.join(part for _,part in pieces)==data
        item=dict(path=name,mode=mode,sha256=sha(data),original_git_blob=oid,parts=[])
        for i,(owner,part) in enumerate(pieces):
            target='.qemu/adaptations/'+name+(f'.part-{i:03d}' if len(pieces)>1 else '')
            dest=args.output/owner/'files'/target;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(part)
            entry=dict(path=target,sha256=sha(part),mode=oct(int(mode,8)&0o777))
            if part.startswith((b'\x7fELF',b'\xcf\xfa\xed\xfe')):
                entry['existing_tracked_asset']=dict(original_path=name,original_git_blob=oid)
            staged[owner].append(entry)
            item['parts'].append(dict(repository=owner,path=target,sha256=sha(part)))
        entries.append(item)
    if errors: raise ValueError('Unassigned recipes: '+json.dumps(errors))
    materializer = Path(__file__).with_name('materialize_component_recipes.py').read_bytes()
    materializer_path = '.qemu/materialize_adaptations.py'
    target = args.output/'build'/'files'/materializer_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(materializer)
    staged['build'].append(dict(path=materializer_path, sha256=sha(materializer), mode='0o755'))
    for owner,files in staged.items():
        revisions={i['revision'] for i in repos[owner]['inputs']}
        if len(revisions)!=1: raise ValueError('Unresolved baseline '+owner)
        dest=args.output/owner
        (dest/'tracked.patch').write_bytes(b'')
        (dest/'export.json').write_text(json.dumps(dict(name=owner,
            upstream_revision=next(iter(revisions)),tracked=[],added=files,omitted=[],
            scope='component_owned_adaptation_recipes_NOT_build_or_runtime_validation'),indent=2)+'\n')
    index=dict(schema_version=1,baseline_branch='OpenHarmony-7.0-Release-qemu',
        repositories={n:repos[n]['inputs'] for n in sorted(staged)},files=entries,
        materializer=dict(repository='build', path=materializer_path,
                          sha256=sha(materializer), mode='100755'),
        validation='Original tracked recipe bytes and executable modes preserved; runtime deferred.')
    args.index.parent.mkdir(parents=True,exist_ok=True)
    args.index.write_text(json.dumps(index,indent=2)+'\n')
    print(f'Staged {len(entries)} tracked files into {len(staged)} owners; '
          f'{sum(len(e["parts"])>1 for e in entries)} cross-component patches split')


if __name__=='__main__':main()
