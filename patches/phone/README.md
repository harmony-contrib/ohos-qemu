# Phone patch set

`apply.sh` is the standalone phone entry point. It applies the phone product
profile plus every common component and requires a validated ArkWeb M144 V8
artifact directory.

```sh
bash patches/phone/apply.sh --source-root /path/to/openharmony \
  --artifact-root /path/to/jsvm-m144 --product arm64_virt
```
