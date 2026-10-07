/* Isolate a Vulkan ICD from the OHOS loader and its implicit layers. */
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <vulkan/vulkan.h>

static void report(const char *name, VkResult result)
{
    printf("%s=%d\n", name, result);
    fflush(stdout);
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) {
        fprintf(stderr, "dlopen: %s\n", dlerror());
        return 1;
    }
    PFN_vkGetInstanceProcAddr get =
        (PFN_vkGetInstanceProcAddr)dlsym(library, "vk_icdGetInstanceProcAddr");
    if (!get) return 3;
    PFN_vkCreateInstance create_instance =
        (PFN_vkCreateInstance)get(VK_NULL_HANDLE, "vkCreateInstance");
    if (!create_instance) return 4;
    VkApplicationInfo app = {
        .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
        .pApplicationName = "direct-icd-probe",
        .apiVersion = VK_API_VERSION_1_0,
    };
    VkInstanceCreateInfo instance_info = {
        .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        .pApplicationInfo = &app,
    };
    VkInstance instance = VK_NULL_HANDLE;
    VkResult result = create_instance(&instance_info, NULL, &instance);
    report("direct_vkCreateInstance", result);
    if (result != VK_SUCCESS) _exit(5);
    PFN_vkEnumeratePhysicalDevices enumerate =
        (PFN_vkEnumeratePhysicalDevices)get(instance, "vkEnumeratePhysicalDevices");
    PFN_vkGetPhysicalDeviceQueueFamilyProperties queues =
        (PFN_vkGetPhysicalDeviceQueueFamilyProperties)get(instance, "vkGetPhysicalDeviceQueueFamilyProperties");
    PFN_vkCreateDevice create_device = (PFN_vkCreateDevice)get(instance, "vkCreateDevice");
    if (!enumerate || !queues || !create_device) _exit(6);
    uint32_t count = 0;
    result = enumerate(instance, &count, NULL);
    report("direct_vkEnumeratePhysicalDevices", result);
    printf("physical_devices=%u\n", count);
    fflush(stdout);
    if (result != VK_SUCCESS || count == 0) _exit(7);
    VkPhysicalDevice physical = VK_NULL_HANDLE;
    count = 1;
    result = enumerate(instance, &count, &physical);
    if (result != VK_SUCCESS || !physical) _exit(8);
    uint32_t family_count = 0;
    queues(physical, &family_count, NULL);
    printf("queue_families=%u\n", family_count);
    fflush(stdout);
    if (!family_count) _exit(9);
    float priority = 1.0f;
    VkDeviceQueueCreateInfo queue_info = {
        .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .queueFamilyIndex = 0,
        .queueCount = 1,
        .pQueuePriorities = &priority,
    };
    VkDeviceCreateInfo device_info = {
        .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .queueCreateInfoCount = 1,
        .pQueueCreateInfos = &queue_info,
    };
    VkDevice device = VK_NULL_HANDLE;
    result = create_device(physical, &device_info, NULL, &device);
    report("direct_vkCreateDevice", result);
    _exit(result == VK_SUCCESS ? 0 : 10);
}
