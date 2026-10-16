"""Synthetic UI counterexamples; no layout here is a captured guest dialog."""
from copy import deepcopy
import hashlib,json
from pathlib import Path
import unittest

from guest_ui import NodeNotReady
from photos_dialog_contract import ZH,select_dialog

OWNER='org.harmonycontrib.wallpaperchallenge'


def node(kind, text='', identifier='', children=None, **attributes):
    return {'attributes': dict(bundleName=OWNER,type=kind,text=text,id=identifier,visible='true',
        enabled='true',clickable='true',bounds='[10,10][100,100]',**attributes), 'children': children or []}


def dialog(allow_id='advanced_dialog_button_0', *, title='允许“Wallpaper challenge”保存 1 张图片？'):
    allow=node('Button',identifier=allow_id,children=[node('Text','允许')])
    allow['children'][0]['attributes']['clickable']='false'
    deny=node('Button',identifier='advanced_dialog_button_1',children=[node('Text','禁止')])
    return node('Column',children=[node('Text',title),allow,deny])


class PhotosDialogTests(unittest.TestCase):
    def select(self, value):return select_dialog(value,OWNER,'save',label='Wallpaper challenge',count=1)

    def test_vertical_reversed_or_redrawn_indices_do_not_select_deny(self):
        for identifier in ('advanced_dialog_button_0','advanced_dialog_button_7'):
            selected,contract=self.select(dialog(identifier))
            self.assertEqual(selected['attributes']['id'],identifier)
            self.assertEqual(selected['attributes']['type'],'Button')
            self.assertEqual(contract['allow'],'允许')

    def test_wrong_caller_count_or_title_and_duplicate_button_are_refused(self):
        for title in ('允许“another app”保存 1 张图片？','允许“Wallpaper challenge”保存 28 张图片？','是否删除此图片？'):
            with self.assertRaises(NodeNotReady):self.select(dialog(title=title))
        tree=dialog();tree['children'].append(deepcopy(tree['children'][1]))
        with self.assertRaisesRegex(ValueError,'ambiguous'):self.select(tree)

    def test_disabled_actual_dialog_cannot_escape_to_background_allow_button(self):
        tree=dialog();tree['children'][1]['attributes']['enabled']='false'
        background=node('Button','允许',identifier='unrelated-background-allow')
        with self.assertRaises(NodeNotReady):self.select(node('Root',children=[tree,background]))

    def test_fixed_resources_match_actual_source_contract(self):
        path=Path(__file__).resolve().parents[2]/'docs/capability-audit/parallel/system/round18-knowledge-UI-contract/ui-contract.json'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),'e65ed60b7d4f022b19c2ebe5ca836992bce595d1d72ba0dc6b81b36a2e4b54df')
        source=json.loads(path.read_text())
        actual=source['photo_save']['plural_templates']['third_save_picture']['zh_CN'][0]['value']
        self.assertEqual(ZH['save']['title'],actual.replace('%1$s','%s').replace('%2$d','%d'))
        self.assertEqual(ZH['save']['allow'],source['photo_save']['allow_text']['zh_CN'])
        delete=source['photo_delete_browser']['ordinary_single_image']
        self.assertEqual(ZH['delete'],dict(title=delete['title']['zh_CN'],allow=delete['confirm_text']['zh_CN'],deny=delete['cancel_text']['zh_CN']))
        self.assertEqual(source['photo_delete_browser']['toolbar_key'],'ToolBarButtonDelete')


if __name__=='__main__':unittest.main()
