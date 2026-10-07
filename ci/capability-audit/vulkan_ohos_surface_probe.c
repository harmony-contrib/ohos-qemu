/* SPDX-License-Identifier: Apache-2.0
 * Real Vulkan -> OHOS NativeWindow -> CPU consumer pixel verification.
 * This verifies buffer-queue WSI, not a visible compositor window.
 */
#define VK_USE_PLATFORM_OHOS
#include <vulkan/vulkan.h>
#include <native_image/native_image.h>
#include <native_window/external_window.h>
#include <native_buffer/native_buffer.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#define REQUIRE(condition) do { if (!(condition)) { \
    fprintf(stderr, "failed line %d: %s\n", __LINE__, #condition); exit(1); \
} } while (0)
#define VK_OK(call) do { VkResult result_ = (call); if (result_ != VK_SUCCESS) { \
    fprintf(stderr, "failed line %d: %s = %d\n", __LINE__, #call, result_); exit(1); \
} } while (0)

struct Context {
    VkDevice device;
    VkQueue queue;
    VkCommandBuffer command;
    VkFence fence;
};

static VkResult draw_present(struct Context *context, VkSwapchainKHR swapchain)
{
    uint32_t index = 0;
    VK_OK(vkAcquireNextImageKHR(context->device, swapchain, 1000000000,
                               VK_NULL_HANDLE, context->fence, &index));
    VK_OK(vkWaitForFences(context->device, 1, &context->fence, VK_TRUE, 1000000000));
    VK_OK(vkResetFences(context->device, 1, &context->fence));
    uint32_t count = 0;
    VK_OK(vkGetSwapchainImagesKHR(context->device, swapchain, &count, NULL));
    VkImage *images = calloc(count, sizeof(*images));
    REQUIRE(images != NULL);
    VK_OK(vkGetSwapchainImagesKHR(context->device, swapchain, &count, images));
    REQUIRE(index < count);
    VK_OK(vkResetCommandBuffer(context->command, 0));
    VkCommandBufferBeginInfo begin = { .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO };
    VK_OK(vkBeginCommandBuffer(context->command, &begin));
    VkImageSubresourceRange range = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1 };
    VkImageMemoryBarrier barrier = {
        .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
        .srcAccessMask = 0, .dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
        .oldLayout = VK_IMAGE_LAYOUT_UNDEFINED,
        .newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
        .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .image = images[index], .subresourceRange = range,
    };
    vkCmdPipelineBarrier(context->command, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
                         VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL, 1, &barrier);
    VkClearColorValue color = { .float32 = { 0.2f, 0.4f, 0.6f, 1.0f } };
    vkCmdClearColorImage(context->command, images[index], VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                         &color, 1, &range);
    barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    barrier.dstAccessMask = 0;
    barrier.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
    barrier.newLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
    vkCmdPipelineBarrier(context->command, VK_PIPELINE_STAGE_TRANSFER_BIT,
                         VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, 0, 0, NULL, 0, NULL, 1, &barrier);
    VK_OK(vkEndCommandBuffer(context->command));
    VkSubmitInfo submit = {
        .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .commandBufferCount = 1, .pCommandBuffers = &context->command,
    };
    VK_OK(vkQueueSubmit(context->queue, 1, &submit, context->fence));
    VK_OK(vkWaitForFences(context->device, 1, &context->fence, VK_TRUE, 1000000000));
    VK_OK(vkResetFences(context->device, 1, &context->fence));
    VkPresentInfoKHR present = {
        .sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR,
        .swapchainCount = 1, .pSwapchains = &swapchain, .pImageIndices = &index,
    };
    VkResult result = vkQueuePresentKHR(context->queue, &present);
    free(images);
    return result;
}

static VkSwapchainKHR make_swapchain(VkPhysicalDevice physical, VkDevice device,
                                    VkSurfaceKHR surface, uint32_t width, uint32_t height)
{
    VkSurfaceCapabilitiesKHR caps;
    VK_OK(vkGetPhysicalDeviceSurfaceCapabilitiesKHR(physical, surface, &caps));
    REQUIRE(caps.currentExtent.width == width && caps.currentExtent.height == height);
    uint32_t count = 0;
    VK_OK(vkGetPhysicalDeviceSurfaceFormatsKHR(physical, surface, &count, NULL));
    REQUIRE(count > 0);
    VkSurfaceFormatKHR *formats = calloc(count, sizeof(*formats));
    REQUIRE(formats != NULL);
    VK_OK(vkGetPhysicalDeviceSurfaceFormatsKHR(physical, surface, &count, formats));
    VkSurfaceFormatKHR format = { VK_FORMAT_UNDEFINED, VK_COLOR_SPACE_SRGB_NONLINEAR_KHR };
    for (uint32_t i = 0; i < count; ++i) {
        if (formats[i].format == VK_FORMAT_B8G8R8A8_UNORM) format = formats[i];
    }
    free(formats);
    REQUIRE(format.format != VK_FORMAT_UNDEFINED);
    REQUIRE(caps.supportedUsageFlags & VK_IMAGE_USAGE_TRANSFER_DST_BIT);
    VkSwapchainCreateInfoKHR info = {
        .sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR,
        .surface = surface, .minImageCount = caps.minImageCount,
        .imageFormat = format.format, .imageColorSpace = format.colorSpace,
        .imageExtent = caps.currentExtent, .imageArrayLayers = 1,
        .imageUsage = VK_IMAGE_USAGE_TRANSFER_DST_BIT,
        .imageSharingMode = VK_SHARING_MODE_EXCLUSIVE,
        .preTransform = VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR,
        .compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR,
        .presentMode = VK_PRESENT_MODE_FIFO_KHR, .clipped = VK_TRUE,
    };
    VkSwapchainKHR swapchain;
    VK_OK(vkCreateSwapchainKHR(device, &info, NULL, &swapchain));
    return swapchain;
}

#ifndef QEMU_VULKAN_SURFACE_HELPERS_ONLY
static void verify_consumer(OH_NativeImage *consumer, int32_t width, int32_t height)
{
    OHNativeWindowBuffer *window_buffer = NULL;
    int fence = -1;
    REQUIRE(OH_NativeImage_AcquireNativeWindowBuffer(consumer, &window_buffer, &fence) == 0);
    REQUIRE(window_buffer != NULL);
    if (fence >= 0) {
        struct pollfd fd = { .fd = fence, .events = POLLIN };
        REQUIRE(poll(&fd, 1, 3000) > 0 && (fd.revents & POLLIN));
        close(fence);
    }
    OH_NativeBuffer *buffer = NULL;
    REQUIRE(OH_NativeBuffer_FromNativeWindowBuffer(window_buffer, &buffer) == 0);
    void *address = NULL;
    REQUIRE(OH_NativeBuffer_Map(buffer, &address) == 0 && address != NULL);
    OH_NativeBuffer_Config config = {0};
    OH_NativeBuffer_GetConfig(buffer, &config);
    REQUIRE(config.width == width && config.height == height);
    REQUIRE(config.format == NATIVEBUFFER_PIXEL_FMT_RGBA_8888 && config.stride >= width * 4);
    const unsigned char expected[4] = {51, 102, 153, 255};
    for (int y = 0; y < height; ++y) {
        const unsigned char *row = (const unsigned char *)address + (size_t)y * config.stride;
        for (int x = 0; x < width; ++x) {
            for (int channel = 0; channel < 4; ++channel) {
                REQUIRE(abs((int)row[x * 4 + channel] - expected[channel]) <= 1);
            }
        }
    }
    REQUIRE(OH_NativeBuffer_Unmap(buffer) == 0);
    REQUIRE(OH_NativeImage_ReleaseNativeWindowBuffer(consumer, window_buffer, -1) == 0);
}

int main(void)
{
    OH_NativeImage *consumer = OH_ConsumerSurface_Create();
    REQUIRE(consumer != NULL);
    REQUIRE(OH_ConsumerSurface_SetDefaultSize(consumer, 13, 7) == 0);
    REQUIRE(OH_ConsumerSurface_SetDefaultUsage(consumer, NATIVEBUFFER_USAGE_CPU_READ) == 0);
    OHNativeWindow *window = OH_NativeImage_AcquireNativeWindow(consumer);
    REQUIRE(window != NULL);
    REQUIRE(OH_NativeWindow_NativeWindowHandleOpt(window, SET_BUFFER_GEOMETRY, 13, 7) == 0);

    const char *extensions[] = { VK_KHR_SURFACE_EXTENSION_NAME, VK_OHOS_SURFACE_EXTENSION_NAME };
    VkApplicationInfo app = { .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
                              .apiVersion = VK_API_VERSION_1_0 };
    VkInstanceCreateInfo info = { .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        .pApplicationInfo = &app, .enabledExtensionCount = 2, .ppEnabledExtensionNames = extensions };
    VkInstance instance;
    VK_OK(vkCreateInstance(&info, NULL, &instance));
    PFN_vkCreateSurfaceOHOS create_surface = (PFN_vkCreateSurfaceOHOS)
        vkGetInstanceProcAddr(instance, "vkCreateSurfaceOHOS");
    REQUIRE(create_surface != NULL);
    VkSurfaceCreateInfoOHOS surface_info = {
        .sType = VK_STRUCTURE_TYPE_SURFACE_CREATE_INFO_OHOS, .window = window,
    };
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
        if (supported && (families[i].queueFlags & VK_QUEUE_GRAPHICS_BIT)) { family = i; break; }
    }
    free(families);
    REQUIRE(family < count);
    float priority = 1.0f;
    VkDeviceQueueCreateInfo queue_info = { .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .queueFamilyIndex = family, .queueCount = 1, .pQueuePriorities = &priority };
    const char *device_extensions[] = { VK_KHR_SWAPCHAIN_EXTENSION_NAME };
    VkDeviceCreateInfo device_info = { .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .queueCreateInfoCount = 1, .pQueueCreateInfos = &queue_info,
        .enabledExtensionCount = 1, .ppEnabledExtensionNames = device_extensions };
    struct Context context = {0};
    VK_OK(vkCreateDevice(physical, &device_info, NULL, &context.device));
    vkGetDeviceQueue(context.device, family, 0, &context.queue);
    VkCommandPoolCreateInfo pool_info = { .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT, .queueFamilyIndex = family };
    VkCommandPool pool;
    VK_OK(vkCreateCommandPool(context.device, &pool_info, NULL, &pool));
    VkCommandBufferAllocateInfo allocate = { .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .commandPool = pool, .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1 };
    VK_OK(vkAllocateCommandBuffers(context.device, &allocate, &context.command));
    VkFenceCreateInfo fence_info = { .sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO };
    VK_OK(vkCreateFence(context.device, &fence_info, NULL, &context.fence));
    VkSwapchainKHR swapchain = make_swapchain(physical, context.device, surface, 13, 7);
    for (int frame = 0; frame < 5; ++frame) {
        VK_OK(draw_present(&context, swapchain));
        verify_consumer(consumer, 13, 7);
    }
    REQUIRE(OH_NativeWindow_NativeWindowHandleOpt(window, SET_BUFFER_GEOMETRY, 19, 11) == 0);
    REQUIRE(draw_present(&context, swapchain) == VK_ERROR_OUT_OF_DATE_KHR);
    OHNativeWindowBuffer *unexpected = NULL;
    int unexpected_fence = -1;
    REQUIRE(OH_NativeImage_AcquireNativeWindowBuffer(consumer, &unexpected, &unexpected_fence) != 0);
    if (unexpected_fence >= 0) close(unexpected_fence);
    vkDestroySwapchainKHR(context.device, swapchain, NULL);
    swapchain = make_swapchain(physical, context.device, surface, 19, 11);
    for (int frame = 0; frame < 5; ++frame) {
        VK_OK(draw_present(&context, swapchain));
        verify_consumer(consumer, 19, 11);
    }
    VK_OK(vkDeviceWaitIdle(context.device));
    vkDestroySwapchainKHR(context.device, swapchain, NULL);
    vkDestroyFence(context.device, context.fence, NULL);
    vkDestroyCommandPool(context.device, pool, NULL);
    vkDestroyDevice(context.device, NULL);
    vkDestroySurfaceKHR(instance, surface, NULL);
    vkDestroyInstance(instance, NULL);
    OH_NativeImage_Destroy(&consumer);
    puts("{\"scope\":\"OHOS NativeWindow buffer-queue WSI (not compositor)\",\"presented_frames\":10,\"verified_rgba_pixels\":1500,\"resize_out_of_date\":true,\"pass\":true}");
    return 0;
}
#endif
