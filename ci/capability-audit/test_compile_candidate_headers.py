"""New exact headers and per-TU subsets must never bypass dependency evidence."""
import unittest
from compile_contact_sync_mode import candidate_headers


class CandidateHeadersTests(unittest.TestCase):
    def test_default_still_requires_every_component_header(self):
        files = {'a.cpp': 'source', 'a.h': 'old', 'new.h': None}
        self.assertEqual(candidate_headers(files, True, None), ('a.h', 'new.h'))
        self.assertEqual(candidate_headers(files, False, None), ())

    def test_explicit_exact_subset_includes_a_new_header(self):
        self.assertEqual(candidate_headers({'a.h': 'old', 'new.h': None}, True, ('new.h',)), ('new.h',))

    def test_reject_no_overlay_empty_unknown_duplicate_or_non_header(self):
        for overlay, selected in ((False, ('a.h',)), (True, ()), (True, ('fake.h',)),
                                  (True, ('a.h', 'a.h')), (True, ('a.cpp',))):
            with self.assertRaises(ValueError):
                candidate_headers({'a.h': 'old', 'a.cpp': 'source'}, overlay, selected)


if __name__ == '__main__':
    unittest.main()
