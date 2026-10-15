"""Captured old-image menu regression; no fixture is package acceptance."""
import copy
import json
from pathlib import Path
import unittest
from guest_ui import NodeNotReady
from selection_menu_runtime import menu_button

FIXTURE=Path(__file__).parent/'fixtures/selection_menu_diagnostic.json'
BUNDLE='org.harmonycontrib.capabilityaudit'


class SelectionMenuTests(unittest.TestCase):
    def setUp(self):self.layout=json.loads(FIXTURE.read_text())

    def find(self,node,kind,text=None):
        roots=node if isinstance(node,list) else [node]
        for root in roots:
            if root['attributes'].get('type')==kind and (text is None or root['attributes'].get('text')==text):return root
            found=self.find(root.get('children',[]),kind,text)
            if found:return found
        return None

    def test_actual_label_leaf_selects_its_real_clickable_parent(self):
        for label in ('全选','复制'):
            selected=menu_button(self.layout,BUNDLE,(label,))
            self.assertEqual(selected['attributes']['type'],'SelectMenuButton')
            self.assertEqual(selected['label_attributes']['type'],'SelectMenuButtonText')
            self.assertEqual(selected['attributes']['clickable'],'true')
            self.assertEqual(selected['label_attributes']['clickable'],'false')

    def test_foreign_or_missing_menu_labels_are_not_guessed(self):
        for bundle,label in (('other.bundle','复制'),(BUNDLE,'missing')):
            with self.assertRaises(NodeNotReady):menu_button(self.layout,bundle,(label,))

    def test_disabled_ancestor_and_escaping_label_are_rejected(self):
        for change in ('disabled','outside'):
            layout=copy.deepcopy(self.layout);leaf=self.find(layout,'SelectMenuButtonText','复制')
            if change=='outside':leaf['attributes']['bounds']='[1,1][20,20]'
            else:
                for parent in self.walk(layout):
                    if leaf in parent.get('children',[]):parent['attributes']['enabled']='false'
            with self.subTest(change=change),self.assertRaises(ValueError):menu_button(layout,BUNDLE,('复制',))

    def walk(self,node):
        roots=node if isinstance(node,list) else [node]
        for root in roots:
            yield root
            yield from self.walk(root.get('children',[]))

    def test_multiple_matching_buttons_are_ambiguous(self):
        layout=copy.deepcopy(self.layout);root=layout[0] if isinstance(layout,list) else layout
        duplicate=next(parent for parent in self.walk(layout) if any(
            child['attributes'].get('text')=='复制' for child in parent.get('children',[])))
        duplicate=copy.deepcopy(duplicate);duplicate['attributes']['bundleName']=BUNDLE
        root['children'].append(duplicate)
        with self.assertRaisesRegex(ValueError,'ambiguous'):menu_button(layout,BUNDLE,('复制',))


if __name__=='__main__':unittest.main()
