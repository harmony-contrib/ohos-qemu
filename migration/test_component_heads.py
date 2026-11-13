import json
from pathlib import Path
import tempfile
import unittest
from component_heads import published_heads


class HeadReceiptsTest(unittest.TestCase):
    def test_lineage_is_independent_of_journal_order(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'source';recipes=Path(root)/'recipes'
            source.write_text('\n'.join(json.dumps(r) for r in [
                dict(name='component',status='published',qemu_commit='source',parent='baseline'),
                dict(name='component',status='published',qemu_commit='next-source',parent='recipe')]))
            recipes.write_text(json.dumps(dict(name='component',status='published',qemu_commit='recipe',parent='source')))
            self.assertEqual(published_heads([source,recipes]),{'component':'next-source'})
            self.assertEqual(published_heads([recipes,source]),{'component':'next-source'})
            with recipes.open('a') as f:
                f.write('\n'+json.dumps(dict(name='component',status='published',qemu_commit='divergent',parent='source')))
            with self.assertRaisesRegex(ValueError,'lineage review'):published_heads([source,recipes])


if __name__=='__main__':unittest.main()
