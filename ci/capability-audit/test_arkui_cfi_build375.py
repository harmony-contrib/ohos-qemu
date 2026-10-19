"""Execute the actual product GN source-verifier recipe before/after applying."""
from pathlib import Path
import unittest
import test_product_component_verifier_cli as recipe
import test_batch_location375_identity_cfi as cfi

class CFIBuildRecipe(unittest.TestCase):
    files = recipe.ProductVerifierCLI.files
    check = recipe.ProductVerifierCLI.check

    def test_product_recipe_requires_complete_current_cfi_component(self):
        def populate(root):
            for name, _, _ in cfi.source.FILES:
                target = root / cfi.PROJECT / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((cfi.COMPONENT / 'fixtures/original' / cfi.PROJECT / name).read_bytes())
            # The actual old entry preflights the complete upgraded sibling set.
            coverage = cfi.COMPONENT.parent / 'cfi_coverage'
            for field in ('BUILD.gn', 'adapter/ohos/entrance/ui_content_impl.cpp',
                          'adapter/ohos/build/BUILD.gn', 'build/ace_lib.gni',
                          'frameworks/core/components_ng/pattern/smart_layout/engine/BUILD.gn'):
                target = root / cfi.PROJECT / field
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((coverage / 'fixtures/original' / cfi.PROJECT / field).read_bytes())
            for project, component in (
                ('commonlibrary/qrcode_generator', 'common/commonlibrary/qrcode_generator/cfi_metadata'),
                ('third_party/bounds_checking_function', 'common/third_party/bounds_checking_function/ace_cfi'),
            ):
                target = root / project / 'BUILD.gn'
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((cfi.ROOT / 'patches' / component / 'fixtures/original' / project / 'BUILD.gn').read_bytes())
        self.check(cfi.COMPONENT, 'ARKUI_IDENTITY_CFI_COMPONENT_SCRIPT',
                   'verify_arkui_native_identity_cfi', populate)

if __name__ == '__main__': unittest.main()
