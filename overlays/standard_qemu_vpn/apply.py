#!/usr/bin/env python3

import json
import re
import sys
from pathlib import Path


SUPPORTED_PRODUCTS = {
    "armv7a_virt": (
        "device/qemu/common/virt_full/kernel/arm_virt_defconfig",
        "device/qemu/common/virt_full/kernel/configs/arm_virt_defconfig",
    ),
    "arm64_virt": (
        "device/qemu/common/virt_full/kernel/arm64_virt_defconfig",
    ),
    "x86_64_virt": (
        "device/qemu/common/virt_full/kernel/x86_64_virt_defconfig",
    ),
}

VPN_KERNEL_OPTIONS = (
    "CONFIG_NAMESPACES",
    "CONFIG_NET",
    "CONFIG_UNIX",
    "CONFIG_INET",
    "CONFIG_NET_NS",
    "CONFIG_NETDEVICES",
    "CONFIG_TUN",
    "CONFIG_IP_ADVANCED_ROUTER",
    "CONFIG_IP_MULTIPLE_TABLES",
    "CONFIG_IPV6",
    "CONFIG_IPV6_MULTIPLE_TABLES",
    "CONFIG_SYSTEM_DATA_VERIFICATION",
    "CONFIG_FS_VERITY",
    "CONFIG_FS_VERITY_BUILTIN_SIGNATURES",
)

VPN_DIALOG_TARGET = (
    "//foundation/communication/netmanager_ext/frameworks/vpn_dialog/"
    "dialog_ui/vpn_dialog:dialog_hap"
)

QEMU_GRAPHICS_FEATURES = {
    # Keep the common RS/Canvas/OpenGL ABI compiled in so existing QEMU build
    # caches remain reusable. The RenderService source fix below forces QEMU's
    # composer onto its raster path without changing the public graphics ABI.
    "graphic_2d_feature_ace_enable_gpu": True,
    "graphic_2d_feature_enable_opengl": True,
    "graphic_2d_feature_enable_vulkan": False,
    "graphic_2d_feature_rs_enable_eglimage": True,
    # Upstream only defines rs_enable_parallel_render in the true branch, but
    # render_service references it unconditionally during GN evaluation.
    "graphic_2d_feature_parallel_render_enable": True,
}

RENDER_ENGINE_PATH = (
    "foundation/graphic/graphic_2d/rosen/modules/render_service/composer/"
    "composer_service/external_depend/engine/rs_base_render_engine.cpp"
)

RS_MAIN_THREAD_PATH = (
    "foundation/graphic/graphic_2d/rosen/modules/render_service/core/pipeline/"
    "main_thread/rs_main_thread.cpp"
)


def die(message: str) -> None:
    raise SystemExit(message)


def read_text(path: Path) -> str:
    if not path.is_file():
        die(f"required OpenHarmony source file is missing: {path}")
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def set_config_bool(content: str, option: str) -> str:
    replacement = f"{option}=y"
    pattern = re.compile(
        rf"^(?:{re.escape(option)}=.*|# {re.escape(option)} is not set)$",
        re.MULTILINE,
    )
    if pattern.search(content):
        return pattern.sub(replacement, content)
    if content and not content.endswith("\n"):
        content += "\n"
    return content + replacement + "\n"


def configure_kernel(root: Path, product: str) -> None:
    configured = 0
    for relative in SUPPORTED_PRODUCTS[product]:
        path = root / relative
        if not path.exists():
            continue
        content = read_text(path)
        updated = content
        for option in VPN_KERNEL_OPTIONS:
            updated = set_config_bool(updated, option)
        if updated != content:
            write_text(path, updated)
            print(f"configured standard VPN kernel options: {path}")
        configured += 1
    if configured == 0:
        die(f"no QEMU kernel defconfig found for {product}")


def set_gni_bool(content: str, name: str, value: bool) -> str:
    replacement = f"  {name} = {'true' if value else 'false'}"
    pattern = re.compile(rf"^[ \t]*{re.escape(name)}[ \t]*=.*$", re.MULTILINE)
    if not pattern.search(content):
        die(f"OpenHarmony netmanager_ext option is missing: {name}")
    return pattern.sub(replacement, content)


def configure_netmanager_ext(root: Path) -> None:
    path = root / "foundation/communication/netmanager_ext/netmanager_ext_config.gni"
    content = read_text(path)
    updated = set_gni_bool(content, "netmanager_ext_feature_vpn", True)
    updated = set_gni_bool(updated, "netmanager_ext_feature_vpnext", True)
    if updated != content:
        write_text(path, updated)
        print(f"enabled VPN and VpnExtension features: {path}")


def configure_vpn_dialog_build(root: Path) -> None:
    dialog_build = (
        root
        / "foundation/communication/netmanager_ext/frameworks/vpn_dialog/"
        "dialog_ui/vpn_dialog/BUILD.gn"
    )
    read_text(dialog_build)

    path = root / "applications/standard/hap/ohos.build"
    document = json.loads(read_text(path))
    try:
        modules = document["parts"]["prebuilt_hap"]["module_list"]
    except (KeyError, TypeError):
        die(f"unexpected applications HAP build structure: {path}")
    if not isinstance(modules, list):
        die(f"applications HAP module_list is not an array: {path}")
    if VPN_DIALOG_TARGET not in modules:
        modules.append(VPN_DIALOG_TARGET)
        write_text(path, json.dumps(document, ensure_ascii=False, indent=2) + "\n")
        print(f"added the VPN authorization dialog build target: {path}")


def require_json_entry(path: Path, predicate, description: str) -> None:
    document = json.loads(read_text(path))
    entries = document.get("install_list") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        die(f"expected an install_list array in {path}")
    if not any(isinstance(entry, dict) and predicate(entry) for entry in entries):
        die(f"{description} is missing from {path}")


def set_component_bool_feature(features: list, name: str, value: bool) -> bool:
    assignment = f"{name} = {'true' if value else 'false'}"
    pattern = re.compile(rf"^[ \t]*{re.escape(name)}[ \t]*=")
    matching = [
        index
        for index, feature in enumerate(features)
        if isinstance(feature, str) and pattern.match(feature)
    ]
    if not matching:
        features.append(assignment)
        return True

    changed = features[matching[0]] != assignment or len(matching) > 1
    features[matching[0]] = assignment
    for index in reversed(matching[1:]):
        del features[index]
    return changed


def configure_portable_qemu_graphics(root: Path, relative: str) -> None:
    path = root / relative
    document = json.loads(read_text(path))
    subsystems = document.get("subsystems") if isinstance(document, dict) else None
    if not isinstance(subsystems, list):
        die(f"expected a subsystems array in {path}")

    graphic_2d = None
    for subsystem in subsystems:
        if not isinstance(subsystem, dict) or subsystem.get("subsystem") != "graphic":
            continue
        for component in subsystem.get("components", []):
            if (
                isinstance(component, dict)
                and component.get("component") == "graphic_2d"
            ):
                graphic_2d = component
                break
    if graphic_2d is None:
        die(f"graphic_2d is missing from QEMU product configuration: {path}")

    features = graphic_2d.get("features")
    if not isinstance(features, list):
        die(f"graphic_2d features are not an array in {path}")
    changed = False
    for name, value in QEMU_GRAPHICS_FEATURES.items():
        changed |= set_component_bool_feature(features, name, value)
    if changed:
        write_text(path, json.dumps(document, ensure_ascii=False, indent=2) + "\n")
        print(f"configured portable software rendering for QEMU: {path}")


def configure_portable_render_context(root: Path) -> None:
    path = root / RENDER_ENGINE_PATH
    content = read_text(path)
    supported_guards = (
        "#if (defined RS_ENABLE_GL) || (defined RS_ENABLE_VK)\n"
        "    renderContext_ = RenderContext::Create();",
        "#if (defined(RS_ENABLE_GL) && defined(RS_ENABLE_EGLIMAGE)) || "
        "defined(RS_ENABLE_VK)\n"
        "    renderContext_ = RenderContext::Create();",
    )
    render_context_guard = supported_guards[0]
    legacy_portable_guard = (
        "#if defined(RS_ENABLE_VK)\n"
        "    renderContext_ = RenderContext::Create();"
    )
    updated = content
    if render_context_guard not in updated:
        for supported_guard in (*supported_guards[1:], legacy_portable_guard):
            if supported_guard in updated:
                updated = updated.replace(
                    supported_guard, render_context_guard, 1
                )
                break
        else:
            die(f"RenderService context initialization guard has changed: {path}")

    gl_gpu_setup = (
        "#else\n"
        "    renderContext_->SetUpGpuContext();\n"
        "#endif\n"
        "#endif // RS_ENABLE_GL || RS_ENABLE_VK"
    )
    portable_gl_gpu_setup = (
        "#else\n"
        '    RS_LOGI("QEMU portable raster composition skips GPU context setup");\n'
        "#endif\n"
        "#endif // RS_ENABLE_GL || RS_ENABLE_VK"
    )
    if portable_gl_gpu_setup not in updated:
        if gl_gpu_setup not in updated:
            die(f"RenderService OpenGL initialization has changed: {path}")
        updated = updated.replace(gl_gpu_setup, portable_gl_gpu_setup, 1)

    manager_guard = (
        "#if (defined(RS_ENABLE_EGLIMAGE) && defined(RS_ENABLE_GPU)) || "
        "defined(RS_ENABLE_VK)\n"
        "    imageManager_ = RSImageManager::Create(renderContext_);"
    )
    portable_manager_guard = (
        "#if defined(RS_ENABLE_VK)\n"
        "    imageManager_ = RSImageManager::Create(renderContext_);"
    )
    if portable_manager_guard not in updated:
        if manager_guard not in updated:
            die(f"RenderService image manager guard has changed: {path}")
        updated = updated.replace(manager_guard, portable_manager_guard, 1)

    force_cpu = "    bool forceCPU = false;"
    portable_force_cpu = "    bool forceCPU = true;"
    if portable_force_cpu not in updated:
        if force_cpu not in updated:
            die(f"RenderService CPU composition default has changed: {path}")
        updated = updated.replace(force_cpu, portable_force_cpu, 1)

    if updated != content:
        write_text(path, updated)
        print(f"configured portable raster composition for QEMU: {path}")


def configure_portable_main_thread(root: Path) -> None:
    path = root / RS_MAIN_THREAD_PATH
    content = read_text(path)
    gpu_cache_setup = """        auto gpuContext = isUniRender_? GetRenderEngine()->GetRenderContext()->GetDrGPUContext() :
            renderEngine_->GetRenderContext()->GetDrGPUContext();
        if (gpuContext == nullptr) {
            RS_LOGE("Init gpuContext is nullptr!");
            return;
        }
        int32_t maxResources = 0;
        size_t maxResourcesSize = 0;
        gpuContext->GetResourceCacheLimits(&maxResources, &maxResourcesSize);
        if (maxResourcesSize > 0) {
            gpuContext->SetResourceCacheLimits(cacheLimitsTimes * maxResources, cacheLimitsTimes *
                std::fmin(maxResourcesSize, DEFAULT_SKIA_CACHE_SIZE));
        } else {
            gpuContext->SetResourceCacheLimits(DEFAULT_SKIA_CACHE_COUNT, DEFAULT_SKIA_CACHE_SIZE);
        }"""
    portable_gpu_cache_setup = """        auto gpuContext = isUniRender_? GetRenderEngine()->GetRenderContext()->GetDrGPUContext() :
            renderEngine_->GetRenderContext()->GetDrGPUContext();
        if (gpuContext == nullptr) {
            RS_LOGI("GPU context is unavailable; continuing with QEMU CPU raster composition");
        } else {
            int32_t maxResources = 0;
            size_t maxResourcesSize = 0;
            gpuContext->GetResourceCacheLimits(&maxResources, &maxResourcesSize);
            if (maxResourcesSize > 0) {
                gpuContext->SetResourceCacheLimits(cacheLimitsTimes * maxResources, cacheLimitsTimes *
                    std::fmin(maxResourcesSize, DEFAULT_SKIA_CACHE_SIZE));
            } else {
                gpuContext->SetResourceCacheLimits(DEFAULT_SKIA_CACHE_COUNT, DEFAULT_SKIA_CACHE_SIZE);
            }
        }"""

    updated = content
    if portable_gpu_cache_setup not in updated:
        if gpu_cache_setup not in updated:
            die(f"RenderService GPU cache initialization has changed: {path}")
        updated = updated.replace(gpu_cache_setup, portable_gpu_cache_setup, 1)

    if updated != content:
        write_text(path, updated)
        print(f"configured CPU-raster main-thread startup for QEMU: {path}")


def validate_product_integration(root: Path, products: list[str]) -> None:
    common_files = set()
    for product in products:
        if product == "x86_64_virt":
            common_files.add("vendor/ohemu/virt/virt_common_x86_64.json")
        else:
            common_files.add("vendor/ohemu/virt/virt_common.json")

    for relative in sorted(common_files):
        configure_portable_qemu_graphics(root, relative)
        path = root / relative
        document = json.loads(read_text(path))
        subsystems = document.get("subsystems") if isinstance(document, dict) else None
        if not isinstance(subsystems, list):
            die(f"expected a subsystems array in {path}")
        components = [
            component.get("component")
            for subsystem in subsystems
            if isinstance(subsystem, dict)
            for component in subsystem.get("components", [])
            if isinstance(component, dict)
        ]
        if "netmanager_ext" not in components:
            die(f"netmanager_ext is missing from QEMU product configuration: {path}")

    install_list = root / "vendor/ohemu/virt/preinstall-config/install_list.json"
    require_json_entry(
        install_list,
        lambda entry: entry.get("app_dir") == "/system/app/VpnDialog"
        and entry.get("removable") is False,
        "non-removable /system/app/VpnDialog",
    )

    capability_list = (
        root / "vendor/ohemu/virt/preinstall-config/install_list_capability.json"
    )
    require_json_entry(
        capability_list,
        lambda entry: entry.get("bundleName") == "com.ohos.vpndialog"
        and entry.get("allowAppUsePrivilegeExtension") is True,
        "com.ohos.vpndialog privileged-extension capability",
    )

    settings_data = root / "applications/standard/hap/SettingsData.hap"
    if not settings_data.is_file():
        die(f"SettingsData HAP is missing: {settings_data}")


def main() -> None:
    if len(sys.argv) < 2:
        die(
            "usage: apply.py OHOS_ROOT "
            "[armv7a_virt|arm64_virt|x86_64_virt ...]"
        )
    root = Path(sys.argv[1]).resolve()
    products = sys.argv[2:] or list(SUPPORTED_PRODUCTS)
    unsupported = sorted(set(products) - set(SUPPORTED_PRODUCTS))
    if unsupported:
        die(f"unsupported QEMU VPN products: {', '.join(unsupported)}")

    for product in products:
        configure_kernel(root, product)
    configure_netmanager_ext(root)
    configure_vpn_dialog_build(root)
    configure_portable_render_context(root)
    configure_portable_main_thread(root)
    validate_product_integration(root, products)
    print(f"standard VPN support configured for: {' '.join(products)}")


if __name__ == "__main__":
    main()
