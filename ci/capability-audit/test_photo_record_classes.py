"""Execute actual patched JS record classes, not gallery/provider emulation."""
from pathlib import Path
import subprocess
import unittest

from test_access_token_kernel import patch_sections

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/common/foundation/multimedia/media_library/public_record_classes/0001-export-public-photo-data-records.patch'


class PhotoRecordClassesTests(unittest.TestCase):
    def test_actual_classes_unset_fields_no_shared_arrays_and_require_new(self):
        sections = patch_sections(PATCH)
        self.assertEqual(len(sections), 1)
        body = '\n'.join(next(iter(sections.values()))[0][2])
        classes = body.split('export default')[0]
        subprocess.run(['node', '-e', classes + r'''
const assert = require('node:assert/strict');
for (const Constructor of [DefaultCoverOrderInfo, PhotoViewMimeTypeFileSizeFilter,
                          RecentPhotoOptions, RecentPhotoInfo, RequestReadPermissionResult]) {
  for (let repeat = 0; repeat < 256; repeat++) {
    const first = new Constructor(), second = new Constructor();
    assert(first instanceof Constructor && second instanceof Constructor && first !== second);
    assert.deepEqual(Object.keys(first), []); assert.deepEqual(Object.keys(second), []);
    first.authorizedUris = ['owned']; second.authorizedUris = [];
    first.authorizedUris.push('changed'); assert.deepEqual(second.authorizedUris, []);
    first.period = 17; second.period = 29; assert.equal(first.period, 17); assert.equal(second.period, 29);
    assert.throws(() => Constructor(), TypeError);
  }
}
'''], check=True, capture_output=True, text=True)
        for name in ('DefaultCoverOrderInfo', 'PhotoViewMimeTypeFileSizeFilter', 'RecentPhotoOptions',
                     'RecentPhotoInfo', 'RequestReadPermissionResult'):
            self.assertIn('  ' + name + ',', body)

    def test_shared_recipe_orders_after_existing_photo_source_patches(self):
        text = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        call = 'bash "${PHOTO_RECORD_CLASSES_COMPONENT_SCRIPT}" --source-root'
        self.assertEqual(text.count(call), 1)
        for name in ('PHOTO_FUSION_ASSET_TYPE_COMPONENT_SCRIPT', 'PHOTO_PUBLIC_ENUMS_COMPONENT_SCRIPT',
                     'PHOTO_SEARCH_ENUMS_COMPONENT_SCRIPT', 'PHOTOS_RECENT_INFO_COMPONENT_SCRIPT', 'PHOTOS_FACARD_COMPONENT_SCRIPT'):
            self.assertLess(text.index('bash "${' + name + '}" --source-root'), text.index(call))


if __name__ == '__main__':
    unittest.main()
