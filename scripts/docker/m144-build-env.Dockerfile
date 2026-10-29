ARG BASE_IMAGE=ubuntu:22.04
FROM ${BASE_IMAGE}
COPY scripts/prepare_m144_build_host.sh /usr/local/lib/ohos-qemu/prepare-m144-host.sh
COPY scripts/prepare_m144_host_cache.py /usr/local/lib/ohos-qemu/prepare_m144_host_cache.py
RUN M144_RELEASE_STAGE=native M144_CORE_SKIP_APT=0 \
    bash /usr/local/lib/ohos-qemu/prepare-m144-host.sh
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
