"""Normal QEMU source preparation: finite public kernel/USB/MTP adaptations.

Source edits only. This does not build, launch, sign, grant an app permission,
change SELinux enforcement, claim a UDC, or report runtime capability success.
"""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    options=parser.parse_args();root=options.source_root.resolve();here=Path(__file__).resolve().parent
    if not root.is_dir() or root==Path('/'):
        raise ValueError('actual OpenHarmony normal source root required')
    spec=json.loads((here/'edits.json').read_bytes())
    if spec['schema']!='qemu-standard-usb-midi-mtp-source-edits/v1':raise ValueError('fixed component edit schema')
    for row in spec['edits']:
        relative=Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0]=='out':raise ValueError('fixed source only')
        path=root/relative
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):raise ValueError('regular original source required: '+str(relative))
        text=path.read_bytes().decode();changed=False
        for cut in row['cuts']:
            before,after=cut['before'],cut['after']
            if text.count(after)==1:continue
            if text.count(before)!=1:raise ValueError('unreviewed original source at '+str(relative))
            text=text.replace(before,after,1);changed=True
        if changed:path.write_bytes(text.encode())
    for row in spec['new_files']:
        path=root/row['path'];source=here/row['source'];body=source.read_bytes()
        if hashlib.sha256(body).hexdigest()!=row['sha256']:raise ValueError('normal component source changed')
        if path.exists():
            if path.is_symlink() or path.read_bytes()!=body:raise ValueError('different existing product implementation')
        else:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body);path.chmod(0o644)
    print('prepared ordinary dummy_hcd/configfs/USB-MIDI and standard FunctionFS MTP product sources; no runtime verdict')
    return 0


if __name__=='__main__':raise SystemExit(main())
