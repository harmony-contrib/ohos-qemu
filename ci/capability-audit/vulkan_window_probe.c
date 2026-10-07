/* SPDX-License-Identifier: Apache-2.0
 * Present actual Vulkan frames into an ArkUI XComponent. Host screenshot
 * pixel verification is mandatory; this status alone is NOT visual proof.
 */
#define QEMU_VULKAN_SURFACE_HELPERS_ONLY
#include "vulkan_ohos_surface_probe.c"
#include <ace/xcomponent/native_interface_xcomponent.h>
#include <napi/native_api.h>
#include <pthread.h>
#include <stdatomic.h>

static pthread_t worker;
static int worker_exists;
static atomic_uint frames, width, height, cleaned, destroyed, generation;

static void *render_window(void *argument)
{
    OHNativeWindow *window = argument;
    int32_t w = 0, h = 0;
    REQUIRE(OH_NativeWindow_NativeWindowHandleOpt(window, GET_BUFFER_GEOMETRY, &h, &w) == 0);
    REQUIRE(w > 0 && h > 0 && w <= 4096 && h <= 4096);
    atomic_store(&width, (unsigned)w);
    atomic_store(&height, (unsigned)h);
    const char *extensions[] = {VK_KHR_SURFACE_EXTENSION_NAME, VK_OHOS_SURFACE_EXTENSION_NAME};
    VkApplicationInfo app = {.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO, .apiVersion = VK_API_VERSION_1_0};
    VkInstanceCreateInfo instance_info = {.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        .pApplicationInfo = &app, .enabledExtensionCount = 2, .ppEnabledExtensionNames = extensions};
    VkInstance instance;
    VK_OK(vkCreateInstance(&instance_info, NULL, &instance));
    PFN_vkCreateSurfaceOHOS create_surface = (PFN_vkCreateSurfaceOHOS)vkGetInstanceProcAddr(instance, "vkCreateSurfaceOHOS");
    REQUIRE(create_surface != NULL);
    VkSurfaceCreateInfoOHOS surface_info = {.sType = VK_STRUCTURE_TYPE_SURFACE_CREATE_INFO_OHOS, .window = window};
    VkSurfaceKHR surface;
    VK_OK(create_surface(instance, &surface_info, NULL, &surface));
    uint32_t count = 0;
    VK_OK(vkEnumeratePhysicalDevices(instance, &count, NULL));
    REQUIRE(count > 0);
    VkPhysicalDevice *physicals = calloc(count, sizeof(*physicals));
    REQUIRE(physicals != NULL);
    VK_OK(vkEnumeratePhysicalDevices(instance, &count, physicals));
    VkPhysicalDevice physical = physicals[0];
    free(physicals);
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, NULL);
    VkQueueFamilyProperties *families = calloc(count, sizeof(*families));
    REQUIRE(families != NULL);
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, families);
    uint32_t family = count;
    for (uint32_t i = 0; i < count; ++i) {
        VkBool32 supported = VK_FALSE;
        VK_OK(vkGetPhysicalDeviceSurfaceSupportKHR(physical, i, surface, &supported));
        if (supported && (families[i].queueFlags & VK_QUEUE_GRAPHICS_BIT)) {family = i; break;}
    }
    free(families);
    REQUIRE(family < count);
    float priority = 1.0f;
    VkDeviceQueueCreateInfo queue_info = {.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .queueFamilyIndex = family, .queueCount = 1, .pQueuePriorities = &priority};
    const char *device_extensions[] = {VK_KHR_SWAPCHAIN_EXTENSION_NAME};
    VkDeviceCreateInfo device_info = {.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .queueCreateInfoCount = 1, .pQueueCreateInfos = &queue_info,
        .enabledExtensionCount = 1, .ppEnabledExtensionNames = device_extensions};
    struct Context context = {0};
    VK_OK(vkCreateDevice(physical, &device_info, NULL, &context.device));
    vkGetDeviceQueue(context.device, family, 0, &context.queue);
    VkCommandPoolCreateInfo pool_info = {.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT, .queueFamilyIndex = family};
    VkCommandPool pool;
    VK_OK(vkCreateCommandPool(context.device, &pool_info, NULL, &pool));
    VkCommandBufferAllocateInfo allocate = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .commandPool = pool, .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1};
    VK_OK(vkAllocateCommandBuffers(context.device, &allocate, &context.command));
    VkFenceCreateInfo fence_info = {.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    VK_OK(vkCreateFence(context.device, &fence_info, NULL, &context.fence));
    VkSwapchainKHR swapchain = make_swapchain(physical, context.device, surface, (uint32_t)w, (uint32_t)h);
    for (unsigned i = 0; i < 5; ++i) {
        VK_OK(draw_present(&context, swapchain));
        atomic_store(&frames, i + 1);
        // Give the real RenderService consumer time to consume each frame.
        (void)poll(NULL, 0, 100);
    }
    VK_OK(vkDeviceWaitIdle(context.device));
    vkDestroySwapchainKHR(context.device, swapchain, NULL);
    vkDestroyFence(context.device, context.fence, NULL);
    vkDestroyCommandPool(context.device, pool, NULL);
    vkDestroyDevice(context.device, NULL);
    vkDestroySurfaceKHR(instance, surface, NULL);
    vkDestroyInstance(instance, NULL);
    REQUIRE(OH_NativeWindow_NativeObjectUnreference(window) == 0);
    atomic_store(&cleaned, 1);
    return NULL;
}

static void surface_created(OH_NativeXComponent *component, void *window)
{
    REQUIRE(window != NULL);
    uint64_t w = 0, h = 0;
    REQUIRE(OH_NativeXComponent_GetXComponentSize(component, window, &w, &h) == OH_NATIVEXCOMPONENT_RESULT_SUCCESS);
    REQUIRE(w > 0 && h > 0 && w <= 4096 && h <= 4096);
    REQUIRE(OH_NativeWindow_NativeWindowHandleOpt(window, SET_BUFFER_GEOMETRY, (int32_t)w, (int32_t)h) == 0);
    if (worker_exists) {REQUIRE(pthread_join(worker, NULL) == 0); worker_exists = 0;}
    atomic_store(&frames, 0);
    atomic_store(&cleaned, 0);
    atomic_store(&destroyed, 0);
    atomic_fetch_add(&generation, 1);
    REQUIRE(OH_NativeWindow_NativeObjectReference(window) == 0);
    REQUIRE(pthread_create(&worker, NULL, render_window, window) == 0);
    worker_exists = 1;
}

static void surface_changed(OH_NativeXComponent *component, void *window)
{
    (void)component;
    (void)window;
    // Resize/out-of-date boundaries are tested by the independent CPU
    // consumer probe. Keep this fixed-size surface a pure compositor test.
}

static void surface_destroyed(OH_NativeXComponent *component, void *window)
{
    (void)component;
    (void)window;
    if (worker_exists) {REQUIRE(pthread_join(worker, NULL) == 0); worker_exists = 0;}
    atomic_store(&destroyed, 1);
}

static void touch(OH_NativeXComponent *component, void *window) {(void)component; (void)window;}
static OH_NativeXComponent_Callback callbacks = {surface_created, surface_changed, surface_destroyed, touch};

static napi_value status(napi_env env, napi_callback_info info)
{
    (void)info;
    char output[200];
    snprintf(output, sizeof(output), "frames=%u width=%u height=%u cleaned=%u destroyed=%u generation=%u",
             atomic_load(&frames), atomic_load(&width), atomic_load(&height), atomic_load(&cleaned),
             atomic_load(&destroyed), atomic_load(&generation));
    napi_value result;
    REQUIRE(napi_create_string_utf8(env, output, NAPI_AUTO_LENGTH, &result) == napi_ok);
    return result;
}

static napi_value init(napi_env env, napi_value exports)
{
    napi_value object;
    OH_NativeXComponent *component = NULL;
    REQUIRE(napi_get_named_property(env, exports, OH_NATIVE_XCOMPONENT_OBJ, &object) == napi_ok);
    REQUIRE(napi_unwrap(env, object, (void **)&component) == napi_ok && component != NULL);
    REQUIRE(OH_NativeXComponent_RegisterCallback(component, &callbacks) == OH_NATIVEXCOMPONENT_RESULT_SUCCESS);
    napi_property_descriptor property = {.utf8name = "getStatus", .method = status, .attributes = napi_default};
    REQUIRE(napi_define_properties(env, exports, 1, &property) == napi_ok);
    return exports;
}

static napi_module module = {.nm_version = 1, .nm_register_func = init, .nm_modname = "vulkanwindowprobe"};
__attribute__((constructor)) static void register_module(void) {napi_module_register(&module);}
