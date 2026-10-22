"""Fixed source/link/image DATA on original normal export/profile callbacks.

No owner, SDK, compiler, guest or independent tool runner is constructed. Image
reads use only the existing profile producer's recorded debugfs callback.
"""
from pathlib import Path
import posixpath
import re
import stat
from produce_media579_product import raw_export,load,checked,ref,save,two,need,dependencies,command

SONAME='libnetsys_native_manager.z.so'
BASE='foundation/communication/netmanager_base/services/netmanagernative/'
NATIVE={BASE+'BUILD.gn':'ca34a5f72e51f2b7f297ffd1924a8e5b21993f89ea913b42491ab32591250ec9',
    BASE+'src/netsys_native_service.cpp':'cba1bf384b844a3ca3bd97d4b4d34a27fab2d35308978567ecde7f4598f020f2',
    BASE+'src/qemu_modem_tun.cpp':'02ceb1c09861ed5fdee3944e6022439a9d1d0fd0134fb8869c8218dbb3b6e0fd',
    BASE+'include/qemu_modem_tun.h':'6507372cf9854bfadfc3fb067b33adfa268a7797abacf3b3ba9929ecd4058887'}


def directory_rows(text):
    rows=[]
    for line in text.splitlines():
        if not line:continue
        match=re.fullmatch(r'/([0-9]+)/([0-7]{5,7})/([0-9]+)/([0-9]+)/([^/]+)/([^/]*)/',line)
        need(match is not None,'complete debugfs -p directory row; no ignored diagnostic/truncated line')
        inode,mode,uid,gid,name,size=match.groups()
        need(int(inode)>0 and (not size or size.isdecimal()) and '\0' not in name,
            'actual physical image directory inode and file name')
        rows.append(dict(inode=int(inode),mode=int(mode,8),uid=int(uid),gid=int(gid),name=name,
            bytes=int(size) if size else None))
    need(rows and {r['name'] for r in rows}>={'.','..'} and len(rows)==len({r['name'] for r in rows}),
        'complete unambiguous image directory with its two real dot entries')
    return rows


def extend_profile(*,output,images,debugfs,call,source_commit,archive,selected_profile):
    output=Path(output);base=output/'telephony-image-inventory';need(not base.exists(),'fresh original profile child');base.mkdir()
    records=[];dumped=[];aliases=[];walked=set();counter=0;entries={}
    need({'system','vendor','chip_prod'}<=set(images),'all original native product images required')
    profile=load(selected_profile);need(profile['archive']['sha256']==archive['sha256'] and profile['dsos'],
        'same actual package and original nonempty selected native profile')
    layout={p:dict(prefix='/',selected_members=[]) for p in images}
    for entry in profile['dsos'].values():
        member=entry['image_member']
        need(member.startswith(('/lib/','/lib64/')) and '..' not in member.split('/'),'original selected physical library-root contract')
        partitions=[p for p in images if entry['staged']['path'].endswith('/'+p+member)]
        need(len(partitions)==1,'actual selected DSO has one physical image partition')
        layout[partitions[0]]['selected_members'].append(member)
    for item in layout.values():item['selected_members'].sort()
    need(layout['system']['selected_members'],'an empty traversal cannot establish the actual selected system layout')
    for partition,image in sorted(images.items()):
        checked(image)
        def listing(member):
            nonlocal counter
            need((partition,member) not in walked and counter<4096,'finite complete image traversal, no repeated directory')
            walked.add((partition,member));counter+=1
            argv=[str(debugfs),'-R','ls -l -p '+member,str(checked(image))]
            raw=call(argv,'telephony-dir-'+str(counter));rows=directory_rows(raw)
            file=base/('directory-'+str(counter)+'.stdout');file.write_text(raw)
            records.append(dict(partition=partition,image=image,member=member,argv=argv,stdout=ref(file),entries=rows))
            return rows
        names={r['name']:r for r in listing('/')}
        for name in sorted(set(images)&set(names)):
            need(stat.S_ISDIR(names[name]['mode']),'unresolved alternate mount-root alias')
            nested=listing('/'+name)
            need(not ({r['name'] for r in nested}&{'lib','lib64','profile','etc'}),
                'alternate native layout needs its own selected-profile/source admission')
        pending=[]
        for name in ('lib','lib64','profile'):
            if name in names:
                need(stat.S_ISDIR(names[name]['mode']),'native library/profile root must be a real directory')
                pending.append('/'+name)
        if 'etc' in names:
            need(stat.S_ISDIR(names['etc']['mode']),'actual etc directory')
            etc={r['name']:r for r in listing('/etc')}
            if 'init' in etc:
                need(stat.S_ISDIR(etc['init']['mode']),'actual init directory')
                pending.append('/etc/init')
        while pending:
            member=pending.pop(0)
            for row in listing(member):
                if row['name'] in ('.','..'):continue
                logical=member.rstrip('/')+'/'+row['name'];key=(partition,logical)
                need(re.fullmatch(r'/[A-Za-z0-9_.+/@-]+(?:/[A-Za-z0-9_.+@-]+)*',logical),'literal bounded actual installed native path')
                need(key not in entries,'unique actual native entry');entries[key]=row
                if stat.S_ISDIR(row['mode']):pending.append(logical)
                elif member.startswith(('/profile','/etc/init')):
                    need(stat.S_ISREG(row['mode']) and row['bytes'] is not None and row['bytes']<2*1024*1024,
                        'complete regular normal service profile/init config; aliases remain unresolved')
                    destination=base/('config-'+str(len(dumped))+'.bin')
                    argv=[str(debugfs),'-R','dump '+logical+' '+str(destination),str(checked(image))]
                    call(argv,'telephony-config-'+str(len(dumped)))
                    need(destination.is_file() and destination.stat().st_size==row['bytes'],'actual complete image config dump')
                    dumped.append(dict(partition=partition,image=image,member=logical,argv=argv,file=ref(destination),inode=row['inode']))
                elif stat.S_ISLNK(row['mode']):
                    argv=[str(debugfs),'-R','stat '+logical,str(checked(image))]
                    raw=call(argv,'telephony-alias-'+str(len(aliases)))
                    inode=re.findall(r'^Inode:\s+([1-9][0-9]*)\s+Type:\s+symlink\s',raw,re.M)
                    target=re.findall(r'^Fast link dest: "([^"\n]+)"$',raw,re.M)
                    need(inode==[str(row['inode'])] and len(target)==1 and
                        re.fullmatch(r'[A-Za-z0-9_.+/@-]{1,4095}',target[0]),
                        'complete literal native fast alias; unhandled alias formats reopen scope')
                    file=base/('alias-'+str(len(aliases))+'.stdout');file.write_text(raw)
                    aliases.append(dict(partition=partition,image=image,member=logical,argv=argv,stdout=ref(file),inode=row['inode'],target=target[0]))
                else:need(stat.S_ISREG(row['mode']),'unresolved special native entry')
    for partition,item in layout.items():
        for member in item['selected_members']:
            row=entries.get((partition,member))
            need(row is not None and stat.S_ISREG(row['mode']),'all selected DSOs covered by this physical library layout')
    targets={(r['partition'],r['member']):r['target'] for r in aliases}
    for origin in targets:
        current=origin;visited=set()
        while current in targets:
            need(current not in visited and len(visited)<64,'native alias loop or excessive chain')
            visited.add(current);partition,member=current;target=targets[current]
            if target.startswith('/'):
                mount=target.split('/')[1]
                if mount in images:partition=mount;target=target[len(mount)+1:]
                member=posixpath.normpath(target)
            else:member=posixpath.normpath(posixpath.dirname(member)+'/'+target)
            need(member.startswith(('/lib/','/lib64/')),'native alias escapes the selected physical library roots')
            current=(partition,member)
        row=entries.get(current)
        need(row is not None and stat.S_ISREG(row['mode']),'directory, broken or unknown-layout native alias remains unresolved')
    inventory=save(output/'telephony579-image-inventory.json',dict(schema='telephony579-actual-native-provider-image-inventory/v1',
        source_commit=source_commit,archive=archive,images=images,selected_profile=selected_profile,layout=layout,
        directories=records,service_configurations=dumped,library_aliases=aliases,
        scope='original-profile-selected-root-lib-lib64-profile-etc-init-only',
        complete_selected_native_library_profile_init_trees=True,unsupported_decision=None,runtime_pass=False))
    return dict(telephony579_image_inventory=inventory)


def produce(*,export_receipt,profile_receipt,package_receipt,media_product,output):
    raw,owner=raw_export(export_receipt);report=load(profile_receipt);package=load(package_receipt);media=load(media_product)
    need(report['exit_code']==package['exit_code']==0 and report['source_commit']==package['source_commit']==raw['source_commit']==media['source_commit'] and
        owner['package_build_receipt']==two(package_receipt) and report['export_receipt']['sha256']==export_receipt['sha256'] and
        two(package['package'])==two(media['archive'])==two(report['package']),'one actual new normal source/package/RO/profile production')
    output=Path(output);need(not output.exists() and output.parent.is_dir(),'fresh pure telephony DATA output');output.mkdir()
    source=load(media['source_export']);profile=load(report['media579_installed_profile'])
    need(source['files']==raw['files'] and SONAME in profile['dsos'],'same completed source export and independent new image profile')
    selected={}
    for logical,digest in NATIVE.items():
        selected[logical]=raw['files'][logical]
        need(ref(checked(selected[logical]))['sha256']==digest,'complete actual reviewed modem product source')
    units=raw['telephony_native']['translation_units'][SONAME]
    need({BASE+'src/qemu_modem_tun.cpp',BASE+'src/netsys_native_service.cpp'}<=set(units),'both new module and actual lifecycle normal compiled TUs')
    for logical,unit in units.items():
        need(Path(raw['source_root'])/logical in dependencies(unit,raw),'every actual native full TU dependency source')
    native=raw['telephony_native']['libraries'][SONAME];entry=profile['dsos'][SONAME]
    need(native['translation_units']==units,'one complete actual separate telephony normal TU map')
    need(checked(native['linked_output']).read_bytes()==checked(entry['image_file']).read_bytes(),
        'actual normal native link equals independent exact-package image DSO')
    library=save(output/'native-library.json',dict(schema='telephony579-whole-product-DSO/v1',source_commit=package['source_commit'],
        archive_sha256=package['package']['sha256'],product=raw['product'],soname=SONAME,source_export=media['source_export'],
        installed_runtime_profile=report['media579_installed_profile'],source_root=raw['source_root'],build_directory=raw['build_directory'],
        image_file=entry['image_file'],linked_output=native['linked_output'],linked_output_logical=native['linked_output_logical'],
        ninja_target=native['ninja_target'],link=native['link'],translation_units=units,
        complete_compile_commands=raw['complete_compile_commands'],complete_compile_query=raw['complete_compile_query'],
        complete_ninja_log=raw['complete_ninja_log'],runtime_pass=False))
    inventory=load(report['telephony579_image_inventory'])
    need(inventory['source_commit']==package['source_commit'] and two(inventory['archive'])==two(package['package']) and
        inventory['images']==report['images'],'all native-provider image inventories from this exact actual profile')
    rtt=checked(export_receipt).parent/'rtt-source-facts579/SOURCE.json'
    need(rtt.is_file() and ref(rtt)['sha256']==owner['rtt_source_facts']['sha256'],'complete original current RTT/provider source facts')
    actual=save(output/'TELEPHONY.json',dict(schema='telephony579-actual-product-input-export/v1',source_commit=package['source_commit'],
        archive=two(package['package']),product=raw['product'],normal_source_context=media['normal_source_context'],
        source_export=media['source_export'],installed_runtime_profile=report['media579_installed_profile'],
        native_sources=selected,library=library,rtt_source_facts=ref(rtt),original_export_receipt=export_receipt,
        original_profile_receipt=profile_receipt,ims_image_inventory=report['telephony579_image_inventory']))
    return dict(telephony579_product_export=actual,runtime_pass=False,first_artifact_behavior_gate_passed=False)


def produce_number_seeds(*, package_receipt, profile_receipt, output):
    """Retain the exact newly packaged local corpora; no lookup pass claim."""
    import hashlib
    import json
    import tarfile
    from production579_target import archive_manifest
    package = load(package_receipt)
    profile = load(profile_receipt)
    archive = package['package']
    need(package['exit_code'] == profile['exit_code'] == 0 and
         package['source_commit'] == profile['source_commit'] and
         two(archive) == two(profile['package']),
         'one completed new package/profile for Number seed DATA')
    context = archive_manifest(checked(archive))['context']
    need(context['device'] == 'phone', 'Number supported-local corpus is phone only')
    prefix = context['package_root'] + '/'
    selected = {prefix + 'number-identity-local-evidence.json': 4 * 1024 * 1024,
                prefix + 'number-local-seeds/numberlocation.data': 16 * 1024 * 1024,
                prefix + 'number-local-seeds/yellowpage.data': 16 * 1024 * 1024}
    retained = {}
    with tarfile.open(checked(archive), 'r:gz') as stream:
        for member in stream:
            if member.name not in selected:
                continue
            need(member.name not in retained and member.isfile() and
                 0 < member.size <= selected[member.name],
                 'one bounded regular exact Number archive member')
            handle = stream.extractfile(member)
            need(handle is not None, 'actual Number member data required')
            with handle:
                raw = handle.read(member.size + 1)
            need(len(raw) == member.size, 'complete actual Number archive member')
            retained[member.name] = raw
    need(set(retained) == set(selected), 'all two seeds and their actual image receipt required')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate actual Number image receipt key')
            result[key] = value
        return result
    evidence_name = prefix + 'number-identity-local-evidence.json'
    image_receipt = json.loads(retained[evidence_name], object_pairs_hook=unique)
    image = profile['images']['system']
    checked(image)
    need(image_receipt['status'] == 'pass' and image_receipt['failures'] == [] and
         image_receipt['source_revision'] == '50e1330646432ce166e7981c577f25f46c90e7ac' and
         image_receipt['system_image_sha256'] == image['sha256'] and
         image_receipt['provider_runtime_validated'] is False and
         image_receipt['local_subset_runtime_validated'] is False and
         image_receipt['first_artifact_behavior_gate_passed'] is False and
         set(image_receipt['local_seed_files']) == {'numberlocation.data', 'yellowpage.data'},
         'actual same-image source-bound receipt only; no runtime or aggregate substitution')
    output = Path(output)
    need(output.is_absolute() and output.parent.resolve() == output.parent and
         not output.exists() and not output.is_symlink(), 'fresh canonical Number seed DATA output')
    output.mkdir(mode=0o700)
    evidence = output / 'packaged-image-evidence.json'
    evidence.write_bytes(retained[evidence_name])
    files = {}
    for name in ('numberlocation.data', 'yellowpage.data'):
        raw = retained[prefix + 'number-local-seeds/' + name]
        row = image_receipt['local_seed_files'][name]
        digest = hashlib.sha256(raw).hexdigest()
        need(row['sha256'] == row['source_sha256'] == digest and row['bytes'] == len(raw) and
             row['source_relative'] == 'base/telephony/number_identity/etc/' + name and
             row['source_revision'] == image_receipt['source_revision'] and
             row['system_image_sha256'] == image['sha256'] and
             type(row['image_inode']) is int and row['image_inode'] > 0 and
             row['image_path'] in row['image_path_aliases'] and
             set(row['image_path_aliases']) <= {'/etc/telephony/' + name, '/system/etc/telephony/' + name} and
             row['runtime_validated'] is False,
             'full actual packaged seed/image/source identity differs')
        destination = output / name
        destination.write_bytes(raw)
        files[name] = dict(file=ref(destination), image_proof=row)
    return save(output / 'NUMBER-SEEDS.json', dict(schema='number580-actual-packaged-local-seeds/v1',
        source_commit=package['source_commit'], archive=two(archive), target=context,
        system_image=image, package_receipt=package_receipt, profile_receipt=profile_receipt,
        packaged_image_evidence=ref(evidence), files=files,
        provider_selected_seed_runtime_proof_required=True,
        runtime_pass=False, first_artifact_behavior_gate_passed=False))


def produce_number_permission(*, export_receipt, profile_receipt, package_receipt, seed_receipt, output):
    """Join completed real producers only; all business replay remains required."""
    _raw, exported = raw_export(export_receipt)
    profile = load(profile_receipt)
    package = load(package_receipt)
    seed = load(seed_receipt)
    source_ref = exported['number_permission_source_export']
    installed_ref = profile['number580_permission_installed_profile']
    source = load(source_ref)
    installed = load(installed_ref)
    image_ref = seed['packaged_image_evidence']
    image = load(image_ref)
    need(package['exit_code'] == profile['exit_code'] == exported['exit_code'] == 0 and
         package['source_commit'] == profile['source_commit'] == exported['source_commit'] ==
         seed['source_commit'] == source['source_commit'] == installed['source_commit'] and
         source['schema'] == 'number580-actual-source-compile-export/v1' and
         installed['schema'] == 'number580-actual-permission-installed-profile/v1' and
         source['source_ro'] is True and source['out_ro'] is True and
         source['archive_sha256'] == package['package']['sha256'] == seed['archive']['sha256'] ==
         installed['archive']['sha256'] and source['device'] == installed['device'] == 'phone' and
         installed['source_export'] == source_ref and
         two(installed['package_receipt']) == two(package_receipt) and
         image['status'] == 'pass' and image['failures'] == [] and
         image['system_image_sha256'] == installed['images']['system']['sha256'],
         'current actual source/compiled library/independent image/profile/seed producers must agree')
    required = {'libnumber_identity.z.so', 'libnumberidentity.z.so', 'libnumberlookup.z.so'}
    number_images = {Path(name).name: value for name, value in image['native_libraries'].items()}
    need(set(number_images) == required and required <= set(installed['entries']),
         'all original Number image libraries must remain represented')
    for name in sorted(required):
        entry = installed['entries'][name]
        need(ref(checked(entry['image_file']))['sha256'] == number_images[name]['sha256'] ==
             ref(checked(entry['staged_file']))['sha256'],
             'actual packaged Number image ELF differs from independent image/staged bytes: ' + name)
    return save(Path(output), dict(schema='number580-actual-permission-translation/v1',
        source_commit=package['source_commit'], archive_sha256=package['package']['sha256'],
        source_export=source_ref, image_report=image_ref, installed_profile=installed_ref))
