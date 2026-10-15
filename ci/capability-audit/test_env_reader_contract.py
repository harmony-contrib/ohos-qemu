"""Result-contract tests; expected vectors are never fresh guest acceptance."""
import json
import copy
from pathlib import Path
import tempfile
import unittest
from verify_env_reader_results import rows, verify, READER_STEPS, pixels
from guest_ui import select_node, NodeNotReady
from PIL import Image
from verify_gap_closure import behavior_results


class EnvReaderContract(unittest.TestCase):
    def test_captured_primary_roundtrip_keeps_real_pixels_text_and_direction(self):
        root=Path(__file__).with_name('fixtures')/'env_reader_primary_diagnostic'
        observation=json.loads((root/'observation.json').read_text())
        layout=json.loads((root/'initial.json').read_text())
        metrics,_=pixels(root/'initial.png',layout,observation['run_id'],'env',0,'initial',observation['density'])
        self.assertTrue(all(row['background_pixels']>=300 for row in metrics if 'background_pixels' in row))
        with Image.open(root/'initial.png') as image:
            node=select_node(layout,'org.harmonycontrib.capabilityaudit',identifier='env-reader-outer-b')
            x,y,w,h=node['rect'];colors=list(image.convert('RGB').crop((x,y,x+w,y+h)).get_flattened_data())
            self.assertGreater(colors.count((2,255,0)),300)
        # A changed challenged text or direction cannot borrow these pixels.
        with self.assertRaises(NodeNotReady):pixels(root/'initial.png',layout,'0'*32,'env',0,'initial',observation['density'])
        changed=copy.deepcopy(layout)
        a=select_node(changed,'org.harmonycontrib.capabilityaudit',identifier='env-reader-inner-a')
        b=select_node(changed,'org.harmonycontrib.capabilityaudit',identifier='env-reader-inner-b')
        a['attributes']['bounds'],b['attributes']['bounds']=b['attributes']['bounds'],a['attributes']['bounds']
        with self.assertRaisesRegex(ValueError,'inherited direction'):
            pixels(root/'initial.png',changed,observation['run_id'],'env',0,'initial',observation['density'])
    def row(self, name, values, family='env', phase=0):
        return dict(runId='1'*32,family=family,cycle=0,phase=phase,name=name,values=values,data='')
    def test_null_font_and_invalid_native_values_are_rejected(self):
        for value in (self.row('env.outside',['Auto',None]),self.row('env.outside',['Auto',float('nan')]),
                      self.row('reader.native',[180,120,5,0],'reader',2),
                      self.row('reader.native',[180,120,1,True],'reader',2),
                      self.row('identity',[0,0,12])):
            with self.subTest(value=value),self.assertRaises(ValueError):rows(json.dumps(value),'1'*32,20010038)
    def test_equality_vectors_use_width_and_height_over_width(self):
        for name,control,phase,values in READER_STEPS:
            width,height,wb,hb=values
            self.assertEqual(wb,sum(width>=v for v in (100,200,300,400)))
            self.assertEqual(hb,sum(height/width>=v for v in (.8,1.25)))
        values=self.row('reader.native',[200,160,2,1],'reader',9)
        self.assertEqual(rows(json.dumps(values),'1'*32,20010038),[values])
    def test_one_callback_cannot_close_two_factory_lifetimes(self):
        value=self.row('reader.native',[180,120,1,0],'reader',2)
        with self.assertRaises(ValueError):verify(json.dumps(value),'1'*32,20010038)
    def test_diagnostic_boot_cannot_close_the_new_package_ledger(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'env-reader').mkdir();(root/'boot').mkdir()
            (root/'env-reader/evidence.json').write_text(json.dumps(dict(status='pass',boot_id='fixture',archive_sha256='0'*64)))
            (root/'boot/boot.json').write_text(json.dumps(dict(status='pass',purpose='diagnostic',archive_sha256='0'*64,
                scope='fresh_packaged_QEMU_boot_NOT_full_behavior_gate',
                test_environment=dict(boot_id='fixture',external_keepalive=False,device_type='phone'))))
            with self.assertRaisesRegex(ValueError,'unchanged fresh acceptance'):behavior_results(root,'fixture','0'*64,'phone')


if __name__=='__main__':unittest.main()
