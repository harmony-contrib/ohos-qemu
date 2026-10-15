"""Exact caller/profile permission boundaries; fixtures are never actual grants."""
import copy
import unittest
from build_arkui_selection_probe import BUNDLE, ROLES, PERMISSION, module
from sign_arkui_selection_probe import configure_profile


class SelectionPermissionProfiles(unittest.TestCase):
    def compiled(self,role):
        value=module(role);value['app']={'bundleName':BUNDLE}
        if role=='reader':value['module']['requestPermissions'][0]['reasonId']=16777218
        return value

    def test_all_roles_remain_ordinary_and_reader_has_only_exact_permission(self):
        for role in ROLES:
            profile={'bundle-info':{},'debug-info':{},'acls':{},'permissions':{}}
            actual=configure_profile(profile,role,'1'*64,self.compiled(role))
            self.assertEqual(actual['bundle-info']['app-feature'],'hos_normal_app')
            self.assertEqual(actual['bundle-info']['apl'],'normal' if role=='normal' else 'system_basic')
            self.assertEqual(actual['acls']['allowed-acls'],[PERMISSION] if role=='reader' else [])
            self.assertEqual(actual['permissions']['restricted-permissions'],actual['acls']['allowed-acls'])
            self.assertEqual(actual['debug-info']['device-ids'],['1'*64])

    def test_reader_resource_and_request_forgery_are_rejected(self):
        for change in ('missing-id','wrong-id','other-permission','extra-permission','wrong-reason','wrong-scene','other-bundle'):
            value=self.compiled('reader');row=value['module']['requestPermissions'][0]
            if change=='missing-id':row.pop('reasonId')
            elif change=='wrong-id':row['reasonId']=True
            elif change=='other-permission':row['name']='ohos.permission.GET_BUNDLE_INFO_PRIVILEGED'
            elif change=='extra-permission':value['module']['requestPermissions'].append({'name':'ohos.permission.INTERNET'})
            elif change=='wrong-reason':row['reason']='$string:other'
            elif change=='wrong-scene':row['usedScene']['abilities']=['OtherAbility']
            else:value['app']['bundleName']='other.bundle'
            with self.subTest(change=change),self.assertRaises(ValueError):
                configure_profile({'bundle-info':{},'debug-info':{},'acls':{},'permissions':{}},'reader','1'*64,value)

    def test_undeclared_or_elevated_unknown_role_cannot_borrow_reader_profile(self):
        for role in ('normal','reader-denied','system_core','root'):
            with self.subTest(role=role),self.assertRaises(ValueError):
                configure_profile({'bundle-info':{},'debug-info':{},'acls':{},'permissions':{}},role,'1'*64,self.compiled('reader'))
        with self.assertRaises(ValueError):configure_profile({},'reader','old-device',self.compiled('reader'))


if __name__=='__main__':unittest.main()
