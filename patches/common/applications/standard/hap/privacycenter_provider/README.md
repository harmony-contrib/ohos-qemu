# PrivacyCenter provider staging

This component stages the one canonical signed `SecurityPrivacyCenter.hap` from
`SCENEBOARD_RUNTIME_ASSET_ROOT` and adds its missing BMS scan entry. It leaves the
four SceneBoard modules and all existing grants, capabilities and uninstall
policies unchanged. Shared build/package/recipe integration belongs to root.

Root's `r58-PrivacyCenter-canonical-sign-01/receipt.json` records real signing and
verification. Its canonical HAP is SHA-256
`e955901c2f23c23edb819b92493fb7455873656815e21ac693681fa6af453f6a`
(419639 bytes). The known source original is
`d150dedbbf732b57ddc376e4a11dc4d873a75281d749bb74873ae0081d35e7e4`
(417639 bytes). Every original ZIP member, including ABC and resources, remains
byte identical. `public/` contains exact copies of the reviewed public evidence;
the library pins every fixture SHA. No HAP binary or private key is vendored here.

The original authenticated release profile authorized a different application
certificate from the original HAP's actual leaf. The canonical profile changes
only `bundle-info.distribution-certificate` to the existing public OS application
release certificate. Its `normal` APL, `hos_system_app`, ACLs, permissions,
privilege capabilities and legacy validity timestamps are preserved exactly.
The original module's debug flag, SDK version and `sys/commonUI` extension are
also preserved; this component makes no claim that they were freshly compiled.
It does not add `AllowAppUsePrivilegeExtension`, extend profile validity, sign,
grant a permission or infer that a 2023 date was the observed installation error.

Example root-owned staging (run only when the shared source writer is leased):

```sh
python3 patches/common/applications/standard/hap/privacycenter_provider/apply.py \
  --source-root /ohos --asset-root "$SCENEBOARD_RUNTIME_ASSET_ROOT" \
  --native-source-revision "$NATIVE_SOURCE_REVISION" --device phone
```

`--device 2in1` selects its independent `virt_2in1_full.meta.json`. The revision
argument records the root-supplied native build identity; this component does
not derive or claim a native compilation. `--verify-only` replays the installed
source checks without mutation and does not require `--asset-root`.
`--java` and `--openssl` select verification executables; the actual HAP verifier
JAR must have the fixed reviewed SHA. Verification uses no keystore. The four
original signing-input SHAs in `provenance.json` are recorded root provenance,
not a request to read or use key material during staging.

All verification completes before source writes. The only write set is the HAP,
`vendor/ohemu/virt/preinstall-config/install_list.json` and the selected device
metadata. A single exact `app_dir` with JSON `removable:false` is idempotent;
duplicate/aliased/different entries fail. Any existing PrivacyCenter reference
in another preinstall policy, including a veto or recover policy, fails for
review. Unknown source HAPs or component metadata also fail. Preimages include
bytes, mode, owner, inode, link count and parent identity; policies also have a
directory inventory. Each write rechecks inputs. Rollback restores only files
actually written by this transaction and still owned by it. External edits or
alias changes are preserved and reported as conflicts.

Root-owned actual image verification:

```sh
python3 scripts/verify_privacycenter_provider_image.py \
  --source-root /ohos --system-image /output/system.img \
  --native-source-revision "$NATIVE_SOURCE_REVISION" --device phone \
  --output /evidence/privacycenter-image.json
```

The image verifier checks both `/app/...` and `/system/app/...` by actual debugfs
stat. Only an exact absent-path diagnostic permits an absent alias. Existing
nonregular paths, unsafe modes, hardlinks, divergent inodes or differing bytes
fail. It records actual image SHA, inode/stat/aliases, HAP SHA and command output;
the HAP repeats the same payload/JAR/profile/CMS checks as source staging. The
four image policy files must equal their audited source bytes. Reports are
offline evidence only: `provider_runtime_validated:false` and
`first_artifact_behavior_gate_passed:false`. Fresh BMS installation, permission
boundaries and UI remain root-owned runtime work.

No tests, Java/CMS commands, SDK builds, debugfs, Docker or guests were executed
by the authoring agent for this delivery. Root should run the host counterexamples
and then the real source/image verifier. Host models explicitly do not establish
cryptographic, native or runtime success.

```sh
cd ci/capability-audit
python3 -m unittest -v test_privacycenter_provider
```
