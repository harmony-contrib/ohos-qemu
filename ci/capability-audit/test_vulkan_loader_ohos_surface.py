#!/usr/bin/env python3
"""Exercise the patched OHOS surface terminator's dispatch and cleanup logic.

Host-side mocks cover failure paths. They do not replace new-image WSI E2E.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/common/third_party/vulkan-loader/ohos_surface_dispatch/0001-dispatch-and-track-ohos-surfaces-per-icd.patch"

MOCKS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#define VKAPI_ATTR
#define VKAPI_CALL
#define VK_SUCCESS 0
#define VK_ERROR_INITIALIZATION_FAILED -3
#define VK_ERROR_EXTENSION_NOT_PRESENT -7
#define VK_ERROR_OUT_OF_HOST_MEMORY -1
#define VK_NULL_HANDLE 0
#define ICD_VER_SUPPORTS_ICD_SURFACE_KHR 3
#define VK_ICD_WSI_PLATFORM_OHOS 17
typedef int VkResult;
typedef void *VkInstance;
typedef uintptr_t VkSurfaceKHR;
typedef void VkAllocationCallbacks;
typedef struct { void *window; } VkSurfaceCreateInfoOHOS;
typedef struct { int platform; } VkIcdSurfaceBase;
typedef struct { VkIcdSurfaceBase base; void *window; } VkIcdSurfaceOHOS;
typedef struct { VkIcdSurfaceOHOS ohos_surf; uint32_t surface_index; } VkIcdSurface;
typedef VkResult (*CreateFn)(VkInstance, const VkSurfaceCreateInfoOHOS *,
                              const VkAllocationCallbacks *, VkSurfaceKHR *);
struct scanned_icd { int interface_version; };
struct loader_icd_term {
    struct loader_icd_term *next;
    struct scanned_icd *scanned_icd;
    struct { CreateFn CreateSurfaceOHOS; } dispatch;
    VkInstance instance;
    struct { VkSurfaceKHR *list; } surface_list;
};
struct loader_instance { bool wsi_ohos_surface_enabled; struct loader_icd_term *icd_terms; };
struct driver { int id; VkResult result; int calls; };
static int loader_lock, locked, locks, unlocks, allocations, releases, destroys;
static bool fail_allocate;
static struct loader_instance *loader_get_instance(VkInstance instance) { return instance; }
static void loader_platform_thread_lock_mutex(int *lock) {
    (void)lock; assert(!locked); locked = 1; ++locks;
}
static void loader_platform_thread_unlock_mutex(int *lock) {
    (void)lock; assert(locked); locked = 0; ++unlocks;
}
static VkResult allocate_icd_surface_struct(struct loader_instance *instance, size_t base,
    size_t platform, const VkAllocationCallbacks *allocator, VkIcdSurface **surface) {
    (void)instance; (void)allocator; assert(locked);
    assert(base == sizeof(VkIcdSurfaceBase)); assert(platform == sizeof(VkIcdSurfaceOHOS));
    if (fail_allocate) return VK_ERROR_OUT_OF_HOST_MEMORY;
    *surface = calloc(1, sizeof(**surface)); assert(*surface);
    (*surface)->surface_index = 7; ++allocations; return VK_SUCCESS;
}
static void cleanup_surface_creation(struct loader_instance *instance, VkResult result,
    VkIcdSurface *surface, const VkAllocationCallbacks *allocator) {
    (void)allocator; assert(locked);
    if (result != VK_SUCCESS && surface) {
        for (struct loader_icd_term *term = instance->icd_terms; term; term = term->next) {
            VkSurfaceKHR *slot = &term->surface_list.list[surface->surface_index];
            if (*slot) { ++destroys; *slot = VK_NULL_HANDLE; }
        }
        free(surface); ++releases;
    }
}
static VkResult create_surface(VkInstance instance, const VkSurfaceCreateInfoOHOS *info,
    const VkAllocationCallbacks *allocator, VkSurfaceKHR *surface) {
    (void)allocator; assert(locked); assert(info && info->window);
    struct driver *driver = instance; ++driver->calls;
    if (driver->result == VK_SUCCESS) *surface = 100 + driver->id;
    return driver->result;
}
'''

CASES = r'''
int main(void) {
    struct scanned_icd scanned[2] = {{3}, {7}};
    struct driver drivers[2] = {{1, VK_SUCCESS, 0}, {2, VK_SUCCESS, 0}};
    VkSurfaceKHR lists[2][16] = {{0}, {0}};
    struct loader_icd_term terms[2] = {
        {NULL, &scanned[0], {create_surface}, &drivers[0], {lists[0]}},
        {NULL, &scanned[1], {create_surface}, &drivers[1], {lists[1]}}
    };
    struct loader_instance instance = {false, &terms[0]};
    VkSurfaceCreateInfoOHOS info = {(void *)123};
    VkSurfaceKHR surface = 999;
    assert(terminator_CreateSurfaceOHOS(&instance, &info, NULL, &surface) == VK_ERROR_EXTENSION_NOT_PRESENT);
    assert(!surface && !allocations && !drivers[0].calls);
    instance.wsi_ohos_surface_enabled = true;
    assert(terminator_CreateSurfaceOHOS(&instance, NULL, NULL, &surface) == VK_ERROR_INITIALIZATION_FAILED);
    assert(!surface && !allocations);
    info.window = NULL;
    assert(terminator_CreateSurfaceOHOS(&instance, &info, NULL, &surface) == VK_ERROR_INITIALIZATION_FAILED);
    info.window = (void *)123;
    assert(terminator_CreateSurfaceOHOS(&instance, &info, NULL, NULL) == VK_ERROR_INITIALIZATION_FAILED);
    fail_allocate = true;
    assert(terminator_CreateSurfaceOHOS(&instance, &info, NULL, &surface) == VK_ERROR_OUT_OF_HOST_MEMORY);
    assert(!surface && !allocations);
    fail_allocate = false;
    terms[0].dispatch.CreateSurfaceOHOS = NULL;
    assert(terminator_CreateSurfaceOHOS(&instance, &info, NULL, &surface) == VK_ERROR_EXTENSION_NOT_PRESENT);
    assert(!surface && allocations == 1 && releases == 1);
    terms[0].dispatch.CreateSurfaceOHOS = create_surface;
    assert(terminator_CreateSurfaceOHOS(&instance, &info, NULL, &surface) == VK_SUCCESS);
    VkIcdSurface *wrapper = (VkIcdSurface *)surface;
    assert(wrapper->surface_index == 7 && wrapper->ohos_surf.window == info.window);
    assert(wrapper->ohos_surf.base.platform == VK_ICD_WSI_PLATFORM_OHOS);
    assert(lists[0][7] == 101 && drivers[0].calls == 1);
    assert(surface != lists[0][7]); // App handle is not the driver's handle.
    free(wrapper); ++releases; lists[0][7] = 0;
    terms[0].next = &terms[1]; drivers[1].result = -99;
    assert(terminator_CreateSurfaceOHOS(&instance, &info, NULL, &surface) == -99);
    assert(!surface && lists[0][7] == 0 && lists[1][7] == 0 && destroys == 1);
    drivers[1].result = VK_SUCCESS;
    assert(terminator_CreateSurfaceOHOS(&instance, &info, NULL, &surface) == VK_SUCCESS);
    assert(lists[0][7] == 101 && lists[1][7] == 102);
    free((void *)surface); ++releases; lists[0][7] = lists[1][7] = 0;
    terms[0].next = NULL; scanned[0].interface_version = 2;
    terms[0].dispatch.CreateSurfaceOHOS = NULL;
    assert(terminator_CreateSurfaceOHOS(&instance, &info, NULL, &surface) == VK_SUCCESS);
    assert(((VkIcdSurface *)surface)->ohos_surf.window == info.window && lists[0][7] == 0);
    free((void *)surface); ++releases;
    assert(!locked && locks == unlocks && allocations == releases);
}
'''


class OHOSSurfaceDispatchTests(unittest.TestCase):
    def test_dispatch_failure_cleanup_and_indexed_representation(self):
        compiler = shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(compiler, "C compiler required for loader boundary tests")
        section = PATCH.read_text().split("+++ b/third_party/vulkan-loader/loader/wsi.c\n", 1)[1]
        function = "\n".join(line[1:] for line in section.splitlines()
                              if line.startswith((" ", "+")))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "test.c"
            source.write_text(MOCKS + function + "\n" + CASES)
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", str(source), "-o", str(root / "test")], check=True)
            subprocess.run([str(root / "test")], check=True)


if __name__ == "__main__":
    unittest.main()
