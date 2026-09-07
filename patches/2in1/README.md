# 2in1 patch set

`apply.sh` is the standalone 2in1 entry point. It applies the 2in1 product
profile plus every common component and requires a validated ArkWeb M144 V8
artifact directory.

```sh
bash patches/2in1/apply.sh --source-root /path/to/openharmony \
  --artifact-root /path/to/jsvm-m144 --product arm64_virt
```
