/* Report core Vulkan and OHOS presentation extension availability. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>

int main(void)
{
    uint32_t count = 0;
    VkResult result = vkEnumerateInstanceExtensionProperties(NULL, &count, NULL);
    if (result != VK_SUCCESS) return 1;
    VkExtensionProperties *extensions = calloc(count, sizeof(*extensions));
    if (!extensions) return 2;
    result = vkEnumerateInstanceExtensionProperties(NULL, &count, extensions);
    if (result != VK_SUCCESS) return 3;
    for (uint32_t index = 0; index < count; ++index) {
        if (strstr(extensions[index].extensionName, "surface") != NULL) {
            printf("instance_extension=%s\n", extensions[index].extensionName);
        }
    }
    free(extensions);

    VkInstanceCreateInfo create_info = {.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    VkInstance instance = VK_NULL_HANDLE;
    result = vkCreateInstance(&create_info, NULL, &instance);
    if (result != VK_SUCCESS) {
        fprintf(stderr, "vkCreateInstance=%d\n", result);
        return 4;
    }
    uint32_t physical_count = 0;
    result = vkEnumeratePhysicalDevices(instance, &physical_count, NULL);
    if (result != VK_SUCCESS || physical_count == 0) return 5;
    VkPhysicalDevice physical = VK_NULL_HANDLE;
    physical_count = 1;
    result = vkEnumeratePhysicalDevices(instance, &physical_count, &physical);
    if (result != VK_SUCCESS) return 6;
    count = 0;
    result = vkEnumerateDeviceExtensionProperties(physical, NULL, &count, NULL);
    if (result != VK_SUCCESS) return 7;
    extensions = calloc(count, sizeof(*extensions));
    if (!extensions) return 8;
    result = vkEnumerateDeviceExtensionProperties(physical, NULL, &count, extensions);
    if (result != VK_SUCCESS) return 9;
    for (uint32_t index = 0; index < count; ++index) {
        if (strstr(extensions[index].extensionName, "swapchain") != NULL ||
            strstr(extensions[index].extensionName, "OHOS") != NULL ||
            strstr(extensions[index].extensionName, "external_memory") != NULL) {
            printf("device_extension=%s\n", extensions[index].extensionName);
        }
    }
    free(extensions);
    vkDestroyInstance(instance, NULL);
    return 0;
}
