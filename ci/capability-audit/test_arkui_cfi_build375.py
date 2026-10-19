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
        self.check(cfi.COMPONENT, 'ARKUI_IDENTITY_CFI_COMPONENT_SCRIPT',
                   'verify_arkui_native_identity_cfi', populate)

if __name__ == '__main__': unittest.main()
