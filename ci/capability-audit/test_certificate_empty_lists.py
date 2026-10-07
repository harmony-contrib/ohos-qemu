"""Actual patched helpers with mocked NAPI/allocation sinks, not guest proof."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/base/security/certificate_manager/empty_lists'
PATCH = COMPONENT / '0001-preserve-empty-certificate-lists-and-free-list-owners.patch'


class CertificateEmptyListTests(unittest.TestCase):
    def test_actual_converters_and_owner_cleanup_under_sanitizers(self):
        hunks = next(iter(patch_sections(PATCH).values()))
        functions = '\n\n'.join('\n'.join(new) for _, _, new in hunks)
        source = r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>
struct Value {
    enum Kind { ARRAY, OBJECT, TEXT, BOOLEAN } kind;
    std::vector<Value *> elements;
    std::map<std::string, Value *> properties;
    std::string text;
    bool boolean = false;
};
using napi_value = Value *;
using napi_env = void *;
using napi_status = int;
constexpr int napi_ok = 0, NAPI_AUTO_LENGTH = -1;
static bool failArray = false;
static std::vector<std::unique_ptr<Value>> values;
static napi_value Make(Value::Kind kind) {
    auto value = std::make_unique<Value>(); value->kind = kind;
    auto pointer = value.get(); values.push_back(std::move(value)); return pointer;
}
static napi_status napi_create_array(napi_env, napi_value *result) {
    if (failArray) return 1;
    *result = Make(Value::ARRAY); return napi_ok;
}
static napi_status napi_create_object(napi_env, napi_value *result) {
    *result = Make(Value::OBJECT); return napi_ok;
}
static napi_status napi_create_string_latin1(napi_env, const char *text, int, napi_value *result) {
    *result = Make(Value::TEXT); (*result)->text = text; return napi_ok;
}
static napi_status napi_get_boolean(napi_env, bool state, napi_value *result) {
    *result = Make(Value::BOOLEAN); (*result)->boolean = state; return napi_ok;
}
static napi_status napi_set_named_property(napi_env, napi_value result, const char *key, napi_value value) {
    result->properties[key] = value; return napi_ok;
}
static napi_status napi_set_element(napi_env, napi_value result, uint32_t index, napi_value value) {
    assert(index == result->elements.size()); result->elements.push_back(value); return napi_ok;
}
#define NAPI_CALL(env, operation) do { if ((operation) != napi_ok) return nullptr; } while (0)
struct CertAbstract { const char *uri; const char *certAlias; const char *subjectName; bool status; };
struct CredentialAbstract { const char *type; const char *alias; const char *keyUri; };
struct Credential { int identifier; };
struct CertList { CertAbstract *certAbstract; };
struct CredentialList { CredentialAbstract *credentialAbstract; };
static const std::string CM_CERT_PROPERTY_URI = "uri", CM_CERT_PROPERTY_CERTALIAS = "certAlias",
    CM_CERT_PROPERTY_STATUS = "status", CM_CERT_PROPERTY_STATE = "state", CM_CERT_PROPERTY_SUBJECTNAME = "subjectName",
    CM_CERT_PROPERTY_TYPE = "type", CM_CERT_PROPERTY_CREDENTIAL_ALIAS = "alias", CM_CERT_PROPERTY_KEY_URI = "keyUri";
static napi_value GenerateUkeyCertInfo(napi_env, const Credential *credential) {
    auto result = Make(Value::TEXT); result->text = std::to_string(credential->identifier); return result;
}
static std::set<void *> allocations;
static void *Allocate(size_t size) {
    auto pointer = std::calloc(1, size); assert(pointer); assert(allocations.insert(pointer).second); return pointer;
}
static void CmFree(void *pointer) {
    assert(pointer && allocations.erase(pointer) == 1); std::free(pointer);
}
static void FreeCertAbstract(CertAbstract *&pointer) {
    if (pointer) { CmFree(pointer); pointer = nullptr; }
}
static void FreeCredentialAbstract(CredentialAbstract *&pointer) {
    if (pointer) { CmFree(pointer); pointer = nullptr; }
}
''' + functions + r'''
int main() {
    CertAbstract certificates[2] = { {"uri-a", "alias-a", "subject-a", true}, {"uri-b", "alias-b", "subject-b", false} };
    CredentialAbstract credentials[2] = { {"type-a", "alias-a", "key-a"}, {"type-b", "alias-b", "key-b"} };
    Credential ukeys[2] = {{11}, {22}};
    for (bool nullStorage : {false, true}) {
        auto cert = GenerateCertAbstractArray(nullptr, nullStorage ? nullptr : certificates, 0);
        auto cred = GenerateCredentialAbstractArray(nullptr, nullStorage ? nullptr : credentials, 0);
        auto ukey = GenerateCredentialArray(nullptr, nullStorage ? nullptr : ukeys, 0);
        assert(cert && cert->kind == Value::ARRAY && cert->elements.empty());
        assert(cred && cred->kind == Value::ARRAY && cred->elements.empty());
        assert(ukey && ukey->kind == Value::ARRAY && ukey->elements.empty());
    }
    for (uint32_t count : {1u, 2u}) {
        assert(GenerateCertAbstractArray(nullptr, nullptr, count) == nullptr);
        assert(GenerateCredentialAbstractArray(nullptr, nullptr, count) == nullptr);
        assert(GenerateCredentialArray(nullptr, nullptr, count) == nullptr);
        auto cert = GenerateCertAbstractArray(nullptr, certificates, count);
        auto cred = GenerateCredentialAbstractArray(nullptr, credentials, count);
        auto ukey = GenerateCredentialArray(nullptr, ukeys, count);
        assert(cert->elements.size() == count && cred->elements.size() == count && ukey->elements.size() == count);
        for (uint32_t index = 0; index < count; index++) {
            auto c = cert->elements[index]; auto r = cred->elements[index];
            assert(c->properties.size() == 5 && r->properties.size() == 3);
            assert(c->properties["uri"]->text == certificates[index].uri);
            assert(c->properties["certAlias"]->text == certificates[index].certAlias);
            assert(c->properties["subjectName"]->text == certificates[index].subjectName);
            assert(c->properties["status"]->boolean == certificates[index].status);
            assert(c->properties["state"]->boolean == certificates[index].status);
            assert(r->properties["type"]->text == credentials[index].type);
            assert(r->properties["alias"]->text == credentials[index].alias);
            assert(r->properties["keyUri"]->text == credentials[index].keyUri);
            assert(ukey->elements[index]->text == std::to_string(ukeys[index].identifier));
        }
    }
    failArray = true;
    for (uint32_t count : {0u, 1u}) {
        assert(GenerateCertAbstractArray(nullptr, certificates, count) == nullptr);
        assert(GenerateCredentialAbstractArray(nullptr, credentials, count) == nullptr);
        assert(GenerateCredentialArray(nullptr, ukeys, count) == nullptr);
    }
    failArray = false;
    CertList *nullCert = nullptr; CredentialList *nullCred = nullptr;
    FreeCertList(nullCert); FreeCredentialList(nullCred); assert(allocations.empty());
    for (int repeat = 0; repeat < 2048; repeat++) {
        for (bool childStorage : {false, true}) {
            auto cert = static_cast<CertList *>(Allocate(sizeof(CertList)));
            auto cred = static_cast<CredentialList *>(Allocate(sizeof(CredentialList)));
            if (childStorage) {
                cert->certAbstract = static_cast<CertAbstract *>(Allocate(sizeof(CertAbstract)));
                cred->credentialAbstract = static_cast<CredentialAbstract *>(Allocate(sizeof(CredentialAbstract)));
            }
            FreeCertList(cert); FreeCredentialList(cred);
            assert(cert == nullptr && cred == nullptr && allocations.empty());
            FreeCertList(cert); FreeCredentialList(cred); assert(allocations.empty());
        }
    }
}
'''
        compile_run(source, language='c++')

    def test_component_fresh_repeat_and_unknown_rejected_even_with_old_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); write_preimages(root, (PATCH,))
            source = root / next(iter(patch_sections(PATCH)))
            tail = '\n// unrelated certificate storage/permission sentinel\n'
            source.write_text(source.read_text() + tail)
            original = source.read_bytes()
            # Minimal source fixtures do not have the actual full-source hashes.
            # A private component copy binds only this synthetic fixture; the
            # actual three-product checker separately uses the pinned real file.
            relative = COMPONENT.relative_to(ROOT)
            fixture_repo = root / 'fixture-repo'
            fixture_component = fixture_repo / relative
            shutil.copytree(COMPONENT, fixture_component)
            shutil.copytree(ROOT / 'patches/lib', fixture_repo / 'patches/lib')
            patched = original.decode()
            for _, before, after in next(iter(patch_sections(PATCH).values())):
                before_text, after_text = '\n'.join(before), '\n'.join(after)
                self.assertEqual(patched.count(before_text), 1)
                patched = patched.replace(before_text, after_text)
            verifier = fixture_component / 'verify_source.py'
            verifier.write_text(verifier.read_text().replace(
                '1886825f602b6d391fea761abb752490c81289efb9567fc28fb70a9d561ecbfd',
                hashlib.sha256(original).hexdigest()).replace(
                'ff3c3d31531600f836c64e0817532a24147a44e99e21237d961515fef6bb1c20',
                hashlib.sha256(patched.encode()).hexdigest()))
            command = ['bash', str(fixture_component / 'apply.sh'), '--source-root', str(root)]
            for _ in range(2):
                subprocess.run(command, check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'apply', '--check', '--reverse', str(PATCH)],
                           check=True, capture_output=True)
            self.assertTrue(source.read_text().endswith(tail))
            marker = root / '.ohos-qemu-patches' / 'untrusted-legacy-marker'
            marker.write_text('must not authorize a skip')
            source.write_text(source.read_text().replace('if (certCount != 0 && certAbstract == nullptr)',
                                                        'if (certCount == 123 && certAbstract == nullptr)'))
            before = source.read_bytes()
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(source.read_bytes(), before)

    def test_only_conversion_guards_and_null_owner_guards_change(self):
        hunks = next(iter(patch_sections(PATCH).values()))
        changes = []
        for _, old, new in hunks:
            self.assertEqual(len(old), len(new))
            changes += [(before, after) for before, after in zip(old, new) if before != after]
        self.assertEqual(len(changes), 5)
        for before, after in changes:
            self.assertTrue(before.strip().startswith('if (') and after.strip().startswith('if ('))
        plan = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text().split(
            'apply_qemu_capability_patch_plan() {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('CERTIFICATE_EMPTY_LISTS_COMPONENT_SCRIPT', plan)


if __name__ == '__main__':
    unittest.main()
