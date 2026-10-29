# Phone patch set

`apply.sh` calls the full Docker builder's single ordered capability patch plan
for phone. Run inside the prepared local Ubuntu 22.04 Docker source environment.
It requires all four validated release dependencies and does not build/package.

```sh
bash patches/phone/apply.sh --source-root /path/to/openharmony \
  --v8-artifact-root /path/to/jsvm-m144 \
  --core-artifact-root /path/to/source-arkweb-core \
  --vulkan-artifact-root /path/to/swiftshader-m144 \
  --avc-artifact-root /path/to/avc-m144 \
  --lfs-asset-root /path/to/openharmony-7.0-lfs \
  --product arm64_virt
```
