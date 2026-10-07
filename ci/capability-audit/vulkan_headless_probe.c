/* Exercise SwiftShader's headless WSI without claiming OHOS native-window WSI. */
#include <stdio.h>
#include <stdlib.h>
#include <vulkan/vulkan.h>

static int check(const char *step, VkResult result)
{
    if (result == VK_SUCCESS) return 0;
    fprintf(stderr, "%s: VkResult=%d\n", step, result);
    return 1;
}

int main(void)
{
    const char *instance_extensions[] = {
        VK_KHR_SURFACE_EXTENSION_NAME,
        VK_EXT_HEADLESS_SURFACE_EXTENSION_NAME,
    };
    VkInstanceCreateInfo instance_info = {
        .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        .enabledExtensionCount = 2,
        .ppEnabledExtensionNames = instance_extensions,
    };
    VkInstance instance = VK_NULL_HANDLE;
    if (check("vkCreateInstance", vkCreateInstance(&instance_info, NULL, &instance))) return 1;
    PFN_vkCreateHeadlessSurfaceEXT create_surface =
        (PFN_vkCreateHeadlessSurfaceEXT)vkGetInstanceProcAddr(instance, "vkCreateHeadlessSurfaceEXT");
    if (!create_surface) {
        fprintf(stderr, "vkCreateHeadlessSurfaceEXT unavailable\n");
        return 2;
    }
    VkHeadlessSurfaceCreateInfoEXT surface_info = {
        .sType = VK_STRUCTURE_TYPE_HEADLESS_SURFACE_CREATE_INFO_EXT,
    };
    VkSurfaceKHR surface = VK_NULL_HANDLE;
    if (check("vkCreateHeadlessSurfaceEXT", create_surface(instance, &surface_info, NULL, &surface))) return 3;

    uint32_t physical_count = 0;
    if (check("vkEnumeratePhysicalDevices", vkEnumeratePhysicalDevices(instance, &physical_count, NULL)) ||
        physical_count == 0) return 4;
    VkPhysicalDevice physical = VK_NULL_HANDLE;
    physical_count = 1;
    if (check("vkEnumeratePhysicalDevices(list)",
              vkEnumeratePhysicalDevices(instance, &physical_count, &physical))) return 5;
    uint32_t queue_count = 0;
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &queue_count, NULL);
    uint32_t family = queue_count;
    for (uint32_t index = 0; index < queue_count; ++index) {
        VkBool32 supported = VK_FALSE;
        if (check("vkGetPhysicalDeviceSurfaceSupportKHR",
                  vkGetPhysicalDeviceSurfaceSupportKHR(physical, index, surface, &supported))) return 6;
        if (supported) {
            family = index;
            break;
        }
    }
    if (family == queue_count) {
        fprintf(stderr, "no headless present queue\n");
        return 7;
    }
    VkSurfaceCapabilitiesKHR capabilities;
    if (check("vkGetPhysicalDeviceSurfaceCapabilitiesKHR",
              vkGetPhysicalDeviceSurfaceCapabilitiesKHR(physical, surface, &capabilities))) return 8;
    uint32_t format_count = 0;
    if (check("vkGetPhysicalDeviceSurfaceFormatsKHR",
              vkGetPhysicalDeviceSurfaceFormatsKHR(physical, surface, &format_count, NULL)) ||
        format_count == 0) return 9;
    VkSurfaceFormatKHR *formats = calloc(format_count, sizeof(*formats));
    if (!formats) return 10;
    if (check("vkGetPhysicalDeviceSurfaceFormatsKHR(list)",
              vkGetPhysicalDeviceSurfaceFormatsKHR(physical, surface, &format_count, formats))) return 11;
    float priority = 1.0f;
    VkDeviceQueueCreateInfo queue_info = {
        .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .queueFamilyIndex = family,
        .queueCount = 1,
        .pQueuePriorities = &priority,
    };
    const char *device_extensions[] = {VK_KHR_SWAPCHAIN_EXTENSION_NAME};
    VkDeviceCreateInfo device_info = {
        .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .queueCreateInfoCount = 1,
        .pQueueCreateInfos = &queue_info,
        .enabledExtensionCount = 1,
        .ppEnabledExtensionNames = device_extensions,
    };
    VkDevice device = VK_NULL_HANDLE;
    if (check("vkCreateDevice", vkCreateDevice(physical, &device_info, NULL, &device))) return 12;
    VkSwapchainCreateInfoKHR swapchain_info = {
        .sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR,
        .surface = surface,
        .minImageCount = capabilities.minImageCount,
        .imageFormat = formats[0].format,
        .imageColorSpace = formats[0].colorSpace,
        .imageExtent = {64, 64},
        .imageArrayLayers = 1,
        .imageUsage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT,
        .imageSharingMode = VK_SHARING_MODE_EXCLUSIVE,
        .preTransform = capabilities.currentTransform,
        .compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR,
        .presentMode = VK_PRESENT_MODE_FIFO_KHR,
        .clipped = VK_TRUE,
    };
    free(formats);
    VkSwapchainKHR swapchain = VK_NULL_HANDLE;
    if (check("vkCreateSwapchainKHR", vkCreateSwapchainKHR(device, &swapchain_info, NULL, &swapchain))) return 13;
    uint32_t image_count = 0;
    if (check("vkGetSwapchainImagesKHR", vkGetSwapchainImagesKHR(device, swapchain, &image_count, NULL)) ||
        image_count == 0) return 14;
    printf("headless_surface=ok queue_family=%u swapchain_images=%u\n", family, image_count);
    vkDestroySwapchainKHR(device, swapchain, NULL);
    vkDestroyDevice(device, NULL);
    vkDestroySurfaceKHR(instance, surface, NULL);
    vkDestroyInstance(instance, NULL);
    return 0;
}
