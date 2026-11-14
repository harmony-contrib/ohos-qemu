import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from materialize_component_recipes import materialize


class RecipesTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.payload=self.root/'payload'
        self.index=self.root/'index.json'
        self.output=self.root/'result'
        self.parts=[]
        for name,data in [('left',b'#!/bin/sh\n'),('right',b'echo preserved\n')]:
            path=self.payload/name/'files/.qemu/part'
            path.parent.mkdir(parents=True);path.write_bytes(data)
            self.parts.append(dict(repository=name,path='.qemu/part',sha256=hashlib.sha256(data).hexdigest()))
        self.record=dict(schema_version=1,repositories={'left':[],'right':[]},files=[dict(
            path='patches/example/apply.sh',mode='100755',parts=self.parts,
            sha256=hashlib.sha256(b'#!/bin/sh\necho preserved\n').hexdigest())])

    def run_materializer(self):
        self.index.write_text(json.dumps(self.record))
        return materialize(self.index,{},self.output,self.payload)

    def test_cross_repository_order_and_mode(self):
        self.assertEqual(self.run_materializer(),1)
        result=self.output/'patches/example/apply.sh'
        self.assertEqual(result.read_bytes(),b'#!/bin/sh\necho preserved\n')
        self.assertEqual(result.stat().st_mode&0o777,0o755)
        with self.assertRaises(ValueError):self.run_materializer()

    def test_tampering_does_not_publish_partial_tree(self):
        (self.payload/'right/files/.qemu/part').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'checksum'):self.run_materializer()
        self.assertFalse(self.output.exists())

    def test_order_is_verified_against_original(self):
        self.parts.reverse()
        with self.assertRaisesRegex(ValueError,'Reassembled'):self.run_materializer()
        self.assertFalse(self.output.exists())

    def test_symlink_and_traversal_rejected(self):
        target=self.payload/'right/files/.qemu/part';target.unlink();target.symlink_to('/etc/hosts')
        with self.assertRaisesRegex(ValueError,'regular file'):self.run_materializer()
        self.record['files'][0]['path']='../escape'
        with self.assertRaisesRegex(ValueError,'Unsafe'):self.run_materializer()
        self.assertFalse((self.root/'escape').exists())

    def test_duplicate_destination_rejected(self):
        self.record['files'].append(self.record['files'][0].copy())
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.run_materializer()


if __name__=='__main__':unittest.main()
