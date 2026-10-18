"""Frozen peer-source derivation checks only; never SDK, TLS or guest proof."""
import difflib
import hashlib
import json
from pathlib import Path
import unittest


FIX = Path(__file__).resolve().parent / 'fixtures/batch_network/openvpn_owned_peer'
ORIGINS = {
    'VpnPeerEntryAbility.ets': ('f5eca699439836b5f039c03fc9690d1ed2e2affe7353ac58192c6bb50e4849e6', 4538),
    'InternetNonceEntryAbility.ets': ('e6e41ebcffbcbc6130445703d287b42470971930539390d83f363b8f78520f96', 5991),
}
OLD = b'this.context.filesDir'
NEW = b'this.context.getApplicationContext().filesDir'


class OwnedPeerFilesTests(unittest.TestCase):
    def check_derivation(self, name, raw):
        self.assertEqual(raw.count(NEW), 1)
        self.assertNotIn(OLD, raw)
        if name == 'VpnPeerEntryAbility.ets':
            value = json.loads((FIX / 'source-origin.json').read_text())
            patch = (FIX / 'owner-lifecycle.diff').read_bytes()
            row = value['owner_lifecycle_patch']
            self.assertEqual(row, {'file': 'owner-lifecycle.diff', 'format': 'python-ndiff/v1',
                                  'sha256': hashlib.sha256(patch).hexdigest(), 'bytes': len(patch)})
            before = ''.join(difflib.restore(patch.decode().splitlines(True), 1)).encode()
            after = ''.join(difflib.restore(patch.decode().splitlines(True), 2)).encode()
            self.assertEqual(raw, after)
            self.assertEqual(hashlib.sha256(before).hexdigest(),
                             '4705b914ace8b0ad0d1522ac4ad3da56cdfe7781281a6d2be98c441ab9966742')
            original = before.replace(NEW, OLD)
        else: original = raw.replace(NEW, OLD)
        digest, size = ORIGINS[name]
        self.assertEqual((hashlib.sha256(original).hexdigest(), len(original)), (digest, size))

    def test_IO_and_explicit_owner_lifecycle_derive_from_exact_frozen_sources(self):
        value = json.loads((FIX / 'source-origin.json').read_text())
        self.assertEqual(value['schema'], 'frozen-owned-peer-fixture-derivation/v2')
        self.assertEqual(value['scope'], 'source-only_NOT_SDK_or_guest_or_TLS_TUN_proof')
        self.assertEqual(value['replacement'], {'before': OLD.decode(), 'after': NEW.decode(), 'count_per_file': 1})
        self.assertEqual(set(value['sources']), set(ORIGINS))
        self.assertEqual({p.name for p in FIX.iterdir()}, set(ORIGINS) | {'source-origin.json', 'owner-lifecycle.diff'})
        for name, (digest, size) in ORIGINS.items():
            with self.subTest(name=name):
                raw = (FIX / name).read_bytes(); self.check_derivation(name, raw)
                row = value['sources'][name]
                self.assertEqual((row['origin_sha256'], row['origin_bytes']), (digest, size))
                self.assertEqual(row['origin'], '.tmp/parallel-capability-20261016/openvpn-owned-peer-review/fixtures/' + name)
                self.assertEqual((row['derived_sha256'], row['derived_bytes']), (hashlib.sha256(raw).hexdigest(), len(raw)))

    def test_ordinary_owner_lifecycle_never_adopts_or_removes_foreign_configs(self):
        source = (FIX / 'VpnPeerEntryAbility.ets').read_text()
        for text in ('await vpn.getSysVpnConfigList()', 'await vpn.addSysVpnConfig(this.config())',
                     "await vpn.getSysVpnConfig('__VPN_ID__')", "await vpn.deleteSysVpnConfig('__VPN_ID__')",
                     'if (!this.stored)', 'if (this.addAttempted || this.baseline !== undefined)',
                     "this.row(r, 'error', detail.code, JSON.stringify(detail))",
                     'JSON.stringify(others) !== JSON.stringify(this.baseline)',
                     "this.row(r, 'config-state', 0, JSON.stringify(observation))"):
            self.assertIn(text, source)
        self.assertNotIn('VpnExtension', source)
        self.assertNotIn('JSON.stringify(this.config())', source)
        self.assertLess(source.index("this.observeConfig(r, 'before-store'"), source.index('await vpn.addSysVpnConfig'))
        self.assertLess(source.index("this.observeConfig(r, 'before-remove'"), source.index('await vpn.deleteSysVpnConfig'))
        self.assertLess(source.index('await this.exactOwnConfig();', source.index('if (own.length === 1)')),
                        source.index('await vpn.deleteSysVpnConfig'))

    def test_old_module_context_and_business_changes_are_rejected(self):
        for name in ORIGINS:
            raw = (FIX / name).read_bytes()
            faults = [raw.replace(NEW, OLD), raw + b'\n// unreviewed change\n',
                      raw.replace(b"this.row(r, 'complete');", b"this.row(r, 'confirmed');")]
            if name == 'VpnPeerEntryAbility.ets':
                faults += [raw.replace(b'vpn.createVpnConnection(this.context)',
                                       b'vpn.createVpnConnection(this.context.getApplicationContext())'),
                           raw.replace(b'await this.connection.destroy()', b'Promise.resolve()'),
                           raw.replace(b'await vpn.getConnectedSysVpnConfig()', b'undefined')]
            else:
                faults += [raw.replace(b'ohos.permission.INTERNET', b'ohos.permission.MANAGE_VPN'),
                           raw.replace(b"result === 'VPN3 ' + prefix + ' ' + server", b'true'),
                           raw.replace(b"info.remoteInfo.address !== '10.73.0.1'", b'false')]
            for index, wrong in enumerate(faults):
                with self.subTest(name=name, fault=index):
                    self.assertNotEqual(raw, wrong)
                    with self.assertRaises(AssertionError): self.check_derivation(name, wrong)


if __name__ == '__main__': unittest.main()
