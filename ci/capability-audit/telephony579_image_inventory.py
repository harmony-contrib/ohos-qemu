"""Independent replay of the selected normal native layout and image reads."""
import posixpath
import re
import stat
from final579_contract import checked,doc,need


def rows(raw):
    result=[]
    for line in raw.splitlines():
        if not line:continue
        columns=line.split('/')
        need(len(columns)==8 and columns[0]==columns[-1]=='' and
            re.fullmatch('[1-9][0-9]*',columns[1]) and re.fullmatch('[0-7]{5,7}',columns[2]) and
            columns[3].isdecimal() and columns[4].isdecimal() and columns[5] and
            (not columns[6] or columns[6].isdecimal()),'complete unfiltered actual debugfs directory row')
        result.append(dict(inode=int(columns[1]),mode=int(columns[2],8),uid=int(columns[3]),gid=int(columns[4]),
            name=columns[5],bytes=int(columns[6]) if columns[6] else None))
    need(result and len(result)==len({r['name'] for r in result}) and {'.','..'}<={r['name'] for r in result},
        'complete exact physical image directory')
    return result


def verify(value,actual_command,*,selected_profile):
    images=value['images'];profile=doc(selected_profile)
    need({'system','vendor','chip_prod'}<=set(images) and value['selected_profile']==selected_profile and
        profile['archive']['sha256']==value['archive']['sha256'] and profile['dsos'],
        'all actual normal images and the same nonempty selected native profile')
    selected={p:[] for p in images}
    for name,entry in profile['dsos'].items():
        member=entry['image_member'];staged=entry['staged']['path']
        need(member.startswith(('/lib/','/lib64/')) and '..' not in member.split('/'),
            'this scope supports only the actual original root-library layout')
        partitions=[p for p in images if staged.endswith('/'+p+member)]
        need(len(partitions)==1,'selected original DSO must bind one actual image partition')
        selected[partitions[0]].append(member)
    need(selected['system'],'actual system library layout cannot be inferred from an empty traversal')
    expected_layout={p:dict(prefix='/',selected_members=sorted(m)) for p,m in selected.items()}
    need(value['layout']==expected_layout,'exact selected original image root layout')
    catalog={}
    for row in value['directories']:
        key=(row['partition'],row['member'])
        need(key not in catalog and row['image']==images[row['partition']],'unique actual image and directory')
        image={k:row['image'][k] for k in ('path','sha256','bytes') if k in row['image']}
        need(row['argv'][1:]==['-R','ls -l -p '+row['member'],str(checked(image))],
            'fixed actual image read program, no supplied directory text')
        command=actual_command(row['argv'])
        need(checked(command['stdout']).read_bytes()==checked(row['stdout']).read_bytes(),
            'inventory directory retains original profile stdout verbatim')
        parsed=rows(checked(row['stdout']).read_text());need(parsed==row['entries'],'all directory entries rebuilt from raw')
        need(not any(r['name']=='libtel_ims.z.so' for r in parsed),'actual IMS provider reopens its precise boundary')
        catalog[key]=parsed
    visited=set();configurations={};entries={};library_aliases={}
    for partition in images:
        def take(member):
            key=(partition,member)
            need(key in catalog and key not in visited,'missing/repeated real provider directory')
            visited.add(key);return catalog[key]
        root={r['name']:r for r in take('/')}
        # An alternate mount-shaped native root is unknown to the selected
        # original profile. It must reopen the scope rather than disappear.
        for name in sorted(set(images)&set(root)):
            need(stat.S_ISDIR(root[name]['mode']),'unresolved image mount-root alias')
            nested=take('/'+name)
            need(not ({r['name'] for r in nested}&{'lib','lib64','profile','etc'}),
                'alternate native layout requires independent profile/source admission')
        pending=[]
        for name in ('lib','lib64','profile'):
            if name in root:
                need(stat.S_ISDIR(root[name]['mode']),'physical native image root')
                pending.append('/'+name)
        if 'etc' in root:
            need(stat.S_ISDIR(root['etc']['mode']),'actual etc image directory')
            etc={r['name']:r for r in take('/etc')}
            if 'init' in etc:
                need(stat.S_ISDIR(etc['init']['mode']),'actual init directory')
                pending.append('/etc/init')
        while pending:
            directory=pending.pop(0)
            for row in take(directory):
                if row['name'] in ('.','..'):continue
                member=directory.rstrip('/')+'/'+row['name'];key=(partition,member)
                need(re.fullmatch(r'/[A-Za-z0-9_.+/@-]+(?:/[A-Za-z0-9_.+@-]+)*',member),'literal installed image path')
                need(key not in entries,'unique physical native tree entry');entries[key]=row
                if stat.S_ISDIR(row['mode']):pending.append(member)
                elif directory.startswith(('/profile','/etc/init')):
                    need(stat.S_ISREG(row['mode']),'profile/init alias must be resolved before source disposition')
                    configurations[key]=row
                elif stat.S_ISLNK(row['mode']):library_aliases[key]=row
                else:need(stat.S_ISREG(row['mode']),'unresolved special native library entry')
    need(visited==set(catalog),'all and only the selected physical native roots and alternate-layout probes')
    for partition,members in selected.items():
        for member in members:
            row=entries.get((partition,member))
            need(row is not None and stat.S_ISREG(row['mode']),'every selected DSO covered by this exact physical layout')
    aliases={}
    for row in value['library_aliases']:
        key=(row['partition'],row['member']);entry=library_aliases.get(key)
        need(entry is not None and key not in aliases and row['image']==images[key[0]] and row['inode']==entry['inode'],
            'all and only actual native library aliases')
        image={k:row['image'][k] for k in ('path','sha256','bytes') if k in row['image']}
        need(row['argv'][1:]==['-R','stat '+key[1],str(checked(image))],'original alias inode stat')
        command=actual_command(row['argv']);raw=checked(row['stdout']).read_text()
        need(checked(command['stdout']).read_bytes()==raw.encode(),'original complete alias stat stdout')
        inode=re.findall(r'^Inode:\s+([1-9][0-9]*)\s+Type:\s+symlink\s',raw,re.M)
        target=re.findall(r'^Fast link dest: "([^"\n]+)"$',raw,re.M)
        need(inode==[str(entry['inode'])] and len(target)==1 and target[0]==row['target'] and
            re.fullmatch(r'[A-Za-z0-9_.+/@-]{1,4095}',target[0]),'unambiguous literal fast native alias; other alias formats remain unresolved')
        aliases[key]=target[0]
    need(set(aliases)==set(library_aliases),'every actual native library alias must be independently read')
    for origin in aliases:
        current=origin;chain=set()
        while current in aliases:
            need(current not in chain and len(chain)<64,'native alias loop or excessive chain')
            chain.add(current);partition,member=current;target=aliases[current]
            if target.startswith('/'):
                parts=target.split('/');mount=parts[1] if len(parts)>1 else ''
                if mount in images:partition=mount;target=target[len(mount)+1:]
                member=posixpath.normpath(target)
            else:member=posixpath.normpath(posixpath.dirname(member)+'/'+target)
            need(member.startswith(('/lib/','/lib64/')),'native alias escapes the selected physical library roots')
            current=(partition,member)
        resolved=entries.get(current)
        need(resolved is not None and stat.S_ISREG(resolved['mode']),
            'unresolved, directory, cross-layout or broken native alias must reopen provider scope')
    seen=set()
    for row in value['service_configurations']:
        key=(row['partition'],row['member'])
        need(key in configurations and key not in seen and row['image']==images[row['partition']] and
            row['inode']==configurations[key]['inode'],'complete actual independently dumped service config coverage')
        seen.add(key);file=checked(row['file']);need(file.stat().st_size==configurations[key]['bytes'],'complete image configuration')
        image={k:row['image'][k] for k in ('path','sha256','bytes') if k in row['image']}
        need(row['argv'][1:]==['-R','dump '+row['member']+' '+str(file),str(checked(image))],'actual exact-image config dump')
        actual_command(row['argv'])
    need(seen==set(configurations),'every selected profile/init file read without provider-name filtering')
    return dict(partitions=sorted(images),complete_directories=len(visited),complete_service_configs=len(seen),
        resolved_regular_file_aliases=len(aliases),selected_profile=selected_profile,
        scope='original-profile-selected-root-lib-lib64-profile-etc-init-only',
        actual_image_reads_replayed=True,not_a_runtime_or_unsupported_verdict=True)
