"""Typed source/role overlay for root's ORIGINAL API26 caller builder and signer.

No compiler/SDK discovery, subprocess, resource launcher or standalone main.
The existing root callback writes these exact bytes before its ordinary build.
"""
from pathlib import Path
import re

from apps_ui578_contract import ASSETS, CASES, ROLES, bundle, nonce, permissions, require

IMPORTS = {
    'notification-settings': {'notification'}, 'notification-subscription': {'subscription'},
    'intelligent-scene': {'intelligentScene'}, 'certificate-dialog': {'CertificateProgram'},
    'network-policy': {'policy','process','sim'}, 'apn': {'cellular','sim'}, 'shortkey': {'shortKey'},
    'enterprise': {'admin','Want'}, 'accessibility-settings': {'SettingsProgram'},
    'accessibility-input': set(),
}


def provider_page(kind):
    """Compile only this fixed case's real API imports; no unrelated NAPI loads.

    The checked-in typed page is the authoring template. Exact top-level clause
    delimiters below are builder input structure, not a permissive source parser.
    Unknown/moved delimiters fail rather than selecting another source file.
    """
    text=(ASSETS/'ProviderPage.ets').read_text()
    starts=list(re.finditer(r"      } else if \(CASE === '([a-z-]+)'\) \{",text))
    require([m[1] for m in starts]==list(IMPORTS),'fixed typed case template clauses changed')
    fallback="      } else { throw new Error('unimplemented apps578 public API case'); }\n"
    end=text.index(fallback)
    chosen=next(i for i,m in enumerate(starts) if m[1]==kind)
    body=text[starts[chosen].end():starts[chosen+1].start() if chosen+1<len(starts) else end]
    result=text[:starts[0].start()]+'      } else {'+body+'      }\n'+text[end+len(fallback):]
    dnd_marker = "    if (CASE === 'intelligent-scene' && this.embeddedDnd) {\n"
    net_marker = "    if (CASE === 'network-policy' && this.embeddedNetwork) {\n"
    end_marker = "    }.width('100%').height('100%')\n"
    require(result.count(dnd_marker) == result.count(net_marker) == 1, 'fixed embedded-provider clauses changed')
    prefix, remaining = result.split(dnd_marker)
    dnd_body, remaining = remaining.split(net_marker)
    net_body, suffix = remaining.split(end_marker, 1)
    result = prefix + (dnd_marker + dnd_body if kind == 'intelligent-scene' else '') + (
        net_marker + net_body if kind == 'network-policy' else '') + end_marker + suffix
    lines=[]
    for line in result.splitlines(keepends=True):
        if line.startswith('import { CertificateProgram }') and kind!='certificate-dialog':continue
        if line.startswith('import { SettingsProgram }') and kind!='accessibility-settings':continue
        if line.startswith('import { ApnProgram }') and kind!='apn':continue
        imported=re.match(r'import (\w+) from ',line)
        if imported and imported[1] not in IMPORTS[kind]|{'common'}:
            continue
        lines.append(line)
    return ''.join(lines)


def source_files(run, kind, role):
    nonce(run)
    require(kind in CASES and role in ROLES, 'exact apps578 compiled persona required')
    replacements = {'__APPS578_RUN__': run, '__APPS578_CASE__': kind,
        '__APPS578_ROLE__': role, '__APPS578_BUNDLE__': bundle(role)}
    mapping = {'EntryAbility.ets': 'entry/src/main/ets/entryability/EntryAbility.ets',
        'Journal.ets': 'entry/src/main/ets/common/Journal.ets',
        ('BlinkPage.ets' if kind == 'blink' else 'ProviderPage.ets'): 'entry/src/main/ets/pages/Index.ets'}
    if kind == 'notification-subscription' and role in ('a','b'):
        mapping['Subscription.ets'] = 'entry/src/main/ets/subscriber/Subscriber578.ets'
        mapping['Observer.ets'] = 'entry/src/main/ets/common/Observer.ets'
    if kind == 'enterprise' and role in ('a','b'):
        mapping['AdminExtension.ets'] = 'entry/src/main/ets/admin/Admin578.ets'
        mapping['Observer.ets'] = 'entry/src/main/ets/common/Observer.ets'
    if kind == 'blink':
        mapping['AccountProgram.ets'] = 'entry/src/main/ets/common/AccountProgram.ets'
    if kind == 'accessibility-settings':
        mapping['SettingsProgram.ets']='entry/src/main/ets/common/SettingsProgram.ets'
    if kind == 'apn':
        mapping['ApnProgram.ets'] = 'entry/src/main/ets/common/ApnProgram.ets'
    if kind == 'certificate-dialog':
        mapping['CertificateProgram.ets'] = 'entry/src/main/ets/common/CertificateProgram.ets'
    out = {}
    for src, dest in mapping.items():
        text = (provider_page(kind) if src=='ProviderPage.ets' else apn_program(role) if src=='ApnProgram.ets' else (ASSETS/src).read_text())
        for old, new in replacements.items():
            text = text.replace(old, new)
        out[dest] = text
    if kind == 'intelligent-scene' and role in ('a','b'):
        label = label_overlay(run, kind, role)
        import json
        out['AppScope/resources/base/element/apps578_dnd.json'] = json.dumps({
            'string': [{'name': label['resource_name'], 'value': label['label']}]}, indent=2) + '\n'
    return out



def apn_program(role):
    require(role in ('normal','system-denied','a','b'), 'fixed APN role only')
    if role in ('a','b'):
        return (ASSETS/'ApnProgram.ets').read_text()
    # Public negative callers never load a system-only DataShare implementation.
    return """import common from '@ohos.app.ability.common';
import data from '@ohos.telephony.data';
import sim from '@ohos.telephony.sim';
export class ApnProgram {
  constructor(context: common.UIAbilityContext) {}
  async environment(): Promise<string> {
    const slot = await data.getDefaultCellularDataSlotId();
    const max = sim.getMaxSimCount();
    const active = slot >= 0 && slot < max ? await sim.isSimActive(slot) : false;
    return JSON.stringify({ slot, max, active });
  }
  async read(): Promise<string> { return JSON.stringify(await data.queryAllApns()); }
}
"""


def label_overlay(run, kind, role):
    nonce(run)
    require(kind == 'intelligent-scene' and role in ('a','b'), 'fixed DND role label only')
    return {'label': 'apps578' + role + run[:8], 'resource_name': 'apps578_dnd_label',
            'app_label': '$string:apps578_dnd_label'}


def module_fields(kind, role):
    # Root keeps the existing actual build module's entry/window/resource fields.
    # It must replace, not union, permissions and apply this exact bundle name.
    fields = {'requestPermissions': [{'name': p} for p in permissions(kind, role)], 'extensionAbilities':[]}
    if kind == 'notification-subscription' and role in ('a','b'):
        fields['extensionAbilities'] = [{'name':'Subscriber578',
            'srcEntry':'./ets/subscriber/Subscriber578.ets', 'type':'notificationSubscriber',
            'exported':False}]
    elif kind == 'enterprise' and role in ('a','b'):
        fields['extensionAbilities'] = [{'name':'Admin578', 'srcEntry':'./ets/admin/Admin578.ets',
            'type':'enterpriseAdmin', 'exported':True}]
    return fields


def module_matches(compiled,kind,role):
    if kind == 'intelligent-scene' and role in ('a','b'):
        require(compiled['app'].get('label')=='$string:apps578_dnd_label' and
            type(compiled['app'].get('labelId')) is int and compiled['app']['labelId']>0,
            'actual compiled AppScope DND label resource missing')
    expected=module_fields(kind,role)
    actual=compiled['module'].get('requestPermissions',[])
    require(isinstance(actual,list) and len(actual)==len(expected['requestPermissions']) and
        sorted(r['name'] for r in actual)==permissions(kind,role), 'extra/missing compiled caller permission')
    actual=compiled['module'].get('extensionAbilities',[])
    require(isinstance(actual,list) and len(actual)==len(expected['extensionAbilities']), 'extra/missing compiled caller extension')
    for row,wanted in zip(actual,expected['extensionAbilities']):
        require(all(row.get(key)==value for key,value in wanted.items()), 'compiled caller extension boundary differs')
        require(not row.get('permissions'), 'caller extension acquired an unexpected permission gate')
    return True


def configure_profile(kind):
    require(kind in CASES, 'fixed root callback case required')
    def configure(profile, role, udid, compiled):
        from re import fullmatch
        require(role in ROLES and fullmatch('[0-9a-fA-F]{64}', udid or ''), 'same actual guest UDID required')
        require(compiled['app']['bundleName'] == bundle(role) and module_matches(compiled,kind,role),
            'actual compiled role permissions/bundle differ')
        expected = permissions(kind, role)
        profile['bundle-info']['bundle-name'] = bundle(role)
        profile['bundle-info']['apl'] = 'normal' if role == 'normal' else 'system_core'
        profile['bundle-info']['app-feature'] = 'hos_normal_app' if role == 'normal' else 'hos_system_app'
        profile['debug-info']['device-ids'] = [udid]
        profile['acls']['allowed-acls'] = expected
        profile['permissions']['restricted-permissions'] = expected
        # Fixed BMS537 privilege set is SERVICE/DATASHARE/UI_SERVICE only;
        # neither of these two extension types needs a privilege capability.
        # Negative callers declare no extensions and gain no widened profile.
        profile['app-privilege-capabilities'] = []
        return profile
    return configure


def validate_prepared(spec, run, kind, role, udid):
    """Verify actual artifacts, not the callback's boolean pass assertion."""
    import json
    import zipfile
    from apps_ui578_contract import load_ref, sha, decode
    require(set(spec) == {'project','unsigned','signed','signing'}, 'fixed original builder artifacts required')
    project = Path(spec['project'])
    require(project.is_absolute() and project.is_dir() and not project.is_symlink(), 'actual caller source project required')
    for rel, text in source_files(run,kind,role).items():
        p = project/rel
        require(p.is_file() and not p.is_symlink() and p.read_text() == text, 'actual compiled input differs: '+rel)
    unsigned, signed = Path(spec['unsigned']['path']), Path(spec['signed']['path'])
    require(sha(unsigned) == spec['unsigned']['sha256'] and sha(signed) == spec['signed']['sha256'],
            'actual current compiled/signed caller changed')
    with zipfile.ZipFile(signed) as hap:
        compiled = decode(hap.read('module.json').decode())
        require('ets/modules.abc' in hap.namelist() and len(hap.read('ets/modules.abc')) > 0,
                'real API26 compiled caller ABC missing')
    receipt = decode(load_ref(spec['signing']))
    profile = receipt['verified_profile']
    require(receipt['signed_sha256'] == sha(signed) and receipt['unsigned_sha256'] == sha(unsigned) and
        receipt['role'] == role and configure_profile(kind)(json.loads(json.dumps(profile)),role,udid,compiled) == profile,
        'original signer verified profile/role/current artifact differ')
    module_matches(compiled,kind,role)
    return compiled
