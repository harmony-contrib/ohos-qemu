#!/usr/bin/env python3
"""Generate the QEMU repo manifests from the reviewed repository catalog."""
import argparse
import copy
import json
from pathlib import Path
import xml.etree.ElementTree as ET

BRANCH = 'OpenHarmony-7.0-Release-qemu'


def write_xml(path, root):
    ET.indent(root, space='  ')
    path.write_bytes(ET.tostring(root, encoding='utf-8', xml_declaration=True) + b'\n')


def root_manifest():
    root = ET.Element('manifest')
    ET.SubElement(root, 'remote', name='qemu', fetch='https://github.com/openharmony-qemu/')
    ET.SubElement(root, 'default', remote='qemu', revision=BRANCH, **{'sync-j': '8'})
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--resolved-ohos', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())
    original = {p.get('path', p.get('name')): p
                for p in ET.parse(args.resolved_ohos).getroot().findall('project')}
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    ohos = ET.Element('manifest')
    for project in catalog['checkouts']['ohos']:
        source = original[project['path']]
        if source.get('name').removesuffix('.git') != project['name']:
            raise ValueError('Original project identity differs: ' + project['path'])
        node = ET.SubElement(ohos, 'project', name=project['name'], path=project['path'])
        if source.get('groups'):
            node.set('groups', source.get('groups'))
        for child in source:
            if child.tag in ('linkfile', 'copyfile'):
                node.append(copy.deepcopy(child))
    ET.SubElement(ohos, 'project', name='busmanager_serial_manager',
                  path='base/busmanager/serial_manager', groups='default,qemu:2in1')
    write_xml(output / 'ohos.xml', ohos)
    default = root_manifest()
    ET.SubElement(default, 'include', name='ohos.xml')
    write_xml(output / 'default.xml', default)
    arkweb = root_manifest()
    for project in catalog['checkouts']['arkweb']:
        node = ET.SubElement(arkweb, 'project', name=project['name'], path=project['path'])
        for link in project['links']:
            ET.SubElement(node, 'linkfile', **link)
    write_xml(output / 'arkweb.xml', arkweb)
    tools = root_manifest()
    for project in catalog['repositories']:
        for entry in project['inputs']:
            if entry['tree'] == 'external' and project['name'] != 'busmanager_serial_manager':
                ET.SubElement(tools, 'project', name=project['name'], path=entry['path'])
    write_xml(output / 'external.xml', tools)
    # Upstream identity remains separate from the eventually published lock of
    # hosted QEMU commits, especially when GitHub requires LFS conversion.
    (output / 'repositories.json').write_text(json.dumps(catalog, indent=2) + '\n')
    products = []
    for product, arch, kernel in [('arm64_virt', 'arm64', 'Image'),
                                  ('x86_64_virt', 'x86_64', 'bzImage'),
                                  ('armv7a_virt', 'armv7a', 'zImage')]:
        for device in ('phone', '2in1'):
            products.append(dict(product=product, guest_arch=arch, device_type=device,
                archive=f'openharmony-qemu-{arch}-{product}-{device}.tar.gz', kernel=kernel,
                profile='qemu_' + device + '_full_source'))
    contract = dict(schema_version=1, baseline_branch=BRANCH, products=products,
        required_images=['ramdisk.img', 'system.img', 'vendor.img', 'userdata.img',
                         'sys_prod.img', 'chip_prod.img', 'updater.img'],
        required_launchers=['launch/linux.sh', 'launch/macos.command', 'launch/windows.ps1'],
        required_tools=['tools/sign-hap.sh', 'tools/install-hap-signer.sh'],
        required_evidence=['manifest.json', 'device-profile.json', 'resolved-manifest.xml',
                           'source-baseline.json', 'kernel.config', 'kernel-inputs.json'],
        matrix_evidence=['SHA256SUMS', 'matrix-manifest.json'],
        validation='Build and runtime validation are deferred by user instruction; no acceptance claimed.')
    (output / 'products.json').write_text(json.dumps(contract, indent=2) + '\n')
    locations = {}
    for tree, manifest in (('ohos', ohos), ('arkweb', arkweb), ('external', tools)):
        for node in manifest.findall('project'):
            locations.setdefault((node.get('name'), node.get('path')), set()).add(tree)

    def dependency_checkouts(project):
        result = []
        for entry in project['inputs']:
            available = locations.get((project['name'], entry['path']), set())
            tree = entry['tree']
            if tree not in available:
                if len(available) != 1:
                    raise ValueError('Missing or ambiguous dependency checkout: ' + project['name'])
                tree = next(iter(available))
            # The catalog retains original provenance. Serial SIG is selected
            # into the system tree by this manifest, so dependency paths must
            # describe the actual checkout location.
            result.append(dict(entry, tree=tree))
        return result

    dependencies = dict(schema_version=1, scope='repository_selection_and_cross_tree_prerequisites',
        component_dependency_authority=['bundle.json', 'BUILD.gn', 'vendor/ohemu product profiles'],
        stages=[
            dict(name='ohos_sources', manifest='default.xml', requires=[]),
            dict(name='external_sources', manifest='external.xml', requires=[]),
            dict(name='arkweb_sources', manifest='arkweb.xml', requires=[]),
            dict(name='ohos_sdk', requires=['ohos_sources']),
            dict(name='arkweb_m144', requires=['arkweb_sources', 'ohos_sdk', 'external_sources'],
                 outputs=['ArkWebCore.hap', 'libv8_shared.so', 'libvk_swiftshader.so', 'libopenh264.so']),
            dict(name='mesa_llvm', requires=['arkweb_sources', 'ohos_sdk', 'external_sources'],
                 outputs=['libllvm.a']),
            dict(name='system_images', requires=['ohos_sources', 'external_sources', 'arkweb_m144', 'mesa_llvm']),
            dict(name='qemu_packages', requires=['system_images'], contract='products.json')],
        source_dependencies=[dict(repository=project['name'], consumers=project['consumers'],
                                  checkouts=dependency_checkouts(project))
                             for project in catalog['repositories'] if project.get('consumers')])
    (output / 'dependencies.json').write_text(json.dumps(dependencies, indent=2) + '\n')
    print(f'Wrote {len(original)} system projects, Serial SIG, ArkWeb and external manifests to {output}')


if __name__ == '__main__':
    main()
