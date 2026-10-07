/* Vulkan loader, ICD, logical-device and host-visible-memory smoke test. */
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>

static int fail(const char *step, VkResult result)
{
    fprintf(stderr, "%s: VkResult=%d\n", step, result);
    return 1;
}

int main(void)
{
    uint32_t version = 0;
    VkResult result = vkEnumerateInstanceVersion(&version);
    if (result != VK_SUCCESS) return fail("vkEnumerateInstanceVersion", result);
    printf("loader_api=%u.%u.%u\n", VK_VERSION_MAJOR(version), VK_VERSION_MINOR(version),
           VK_VERSION_PATCH(version));

    const VkApplicationInfo application = {
        .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
        .pApplicationName = "ohos-qemu-vulkan-probe",
        .apiVersion = VK_API_VERSION_1_0,
    };
    const VkInstanceCreateInfo instance_info = {
        .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        .pApplicationInfo = &application,
    };
    VkInstance instance = VK_NULL_HANDLE;
    result = vkCreateInstance(&instance_info, NULL, &instance);
    if (result != VK_SUCCESS) return fail("vkCreateInstance", result);
    printf("instance=ok\n");

    uint32_t device_count = 0;
    result = vkEnumeratePhysicalDevices(instance, &device_count, NULL);
    if (result != VK_SUCCESS || device_count == 0) {
        vkDestroyInstance(instance, NULL);
        return fail("vkEnumeratePhysicalDevices(count)", result);
    }
    VkPhysicalDevice *devices = calloc(device_count, sizeof(*devices));
    if (!devices) return 2;
    result = vkEnumeratePhysicalDevices(instance, &device_count, devices);
    if (result != VK_SUCCESS) return fail("vkEnumeratePhysicalDevices(list)", result);
    VkPhysicalDevice physical = devices[0];
    free(devices);
    VkPhysicalDeviceProperties properties;
    vkGetPhysicalDeviceProperties(physical, &properties);
    printf("physical_devices=%u name=%s api=%u.%u.%u\n", device_count,
           properties.deviceName, VK_VERSION_MAJOR(properties.apiVersion),
           VK_VERSION_MINOR(properties.apiVersion), VK_VERSION_PATCH(properties.apiVersion));

    uint32_t queue_count = 0;
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &queue_count, NULL);
    VkQueueFamilyProperties *queues = calloc(queue_count, sizeof(*queues));
    if (!queues) return 2;
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &queue_count, queues);
    uint32_t family = queue_count;
    for (uint32_t index = 0; index < queue_count; ++index) {
        if (queues[index].queueCount && (queues[index].queueFlags & VK_QUEUE_COMPUTE_BIT)) {
            family = index;
            break;
        }
    }
    free(queues);
    if (family == queue_count) {
        fprintf(stderr, "no compute queue\n");
        return 3;
    }
    const float priority = 1.0f;
    const VkDeviceQueueCreateInfo queue_info = {
        .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .queueFamilyIndex = family,
        .queueCount = 1,
        .pQueuePriorities = &priority,
    };
    const VkDeviceCreateInfo device_info = {
        .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .queueCreateInfoCount = 1,
        .pQueueCreateInfos = &queue_info,
    };
    VkDevice device = VK_NULL_HANDLE;
    result = vkCreateDevice(physical, &device_info, NULL, &device);
    if (result != VK_SUCCESS) return fail("vkCreateDevice", result);
    VkQueue queue = VK_NULL_HANDLE;
    vkGetDeviceQueue(device, family, 0, &queue);
    if (!queue) {
        fprintf(stderr, "vkGetDeviceQueue returned null\n");
        return 4;
    }
    printf("logical_device=ok compute_queue_family=%u\n", family);

    const VkBufferCreateInfo buffer_info = {
        .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .size = 4096,
        .usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT,
        .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
    };
    VkBuffer buffer = VK_NULL_HANDLE;
    result = vkCreateBuffer(device, &buffer_info, NULL, &buffer);
    if (result != VK_SUCCESS) return fail("vkCreateBuffer", result);
    VkMemoryRequirements requirements;
    vkGetBufferMemoryRequirements(device, buffer, &requirements);
    VkPhysicalDeviceMemoryProperties memory_properties;
    vkGetPhysicalDeviceMemoryProperties(physical, &memory_properties);
    uint32_t memory_type = memory_properties.memoryTypeCount;
    for (uint32_t index = 0; index < memory_properties.memoryTypeCount; ++index) {
        VkMemoryPropertyFlags flags = memory_properties.memoryTypes[index].propertyFlags;
        if ((requirements.memoryTypeBits & (1u << index)) &&
            (flags & (VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)) ==
                (VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)) {
            memory_type = index;
            break;
        }
    }
    if (memory_type == memory_properties.memoryTypeCount) {
        fprintf(stderr, "no host-visible coherent buffer memory\n");
        return 5;
    }
    const VkMemoryAllocateInfo allocation_info = {
        .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .allocationSize = requirements.size,
        .memoryTypeIndex = memory_type,
    };
    VkDeviceMemory memory = VK_NULL_HANDLE;
    result = vkAllocateMemory(device, &allocation_info, NULL, &memory);
    if (result != VK_SUCCESS) return fail("vkAllocateMemory", result);
    result = vkBindBufferMemory(device, buffer, memory, 0);
    if (result != VK_SUCCESS) return fail("vkBindBufferMemory", result);
    void *mapped = NULL;
    result = vkMapMemory(device, memory, 0, 4096, 0, &mapped);
    if (result != VK_SUCCESS) return fail("vkMapMemory", result);
    memset(mapped, 0x5a, 4096);
    printf("mapped_buffer=ok byte=%02x size=%" PRIu64 "\n", ((unsigned char *)mapped)[0],
           (uint64_t)requirements.size);

    /* Submit real device work; a mapped host buffer alone does not exercise
     * the ICD's command execution or device-to-host visibility. */
    const VkCommandPoolCreateInfo pool_info = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .queueFamilyIndex = family,
    };
    VkCommandPool pool = VK_NULL_HANDLE;
    result = vkCreateCommandPool(device, &pool_info, NULL, &pool);
    if (result != VK_SUCCESS) return fail("vkCreateCommandPool", result);
    const VkCommandBufferAllocateInfo command_info = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .commandPool = pool,
        .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
        .commandBufferCount = 1,
    };
    VkCommandBuffer command = VK_NULL_HANDLE;
    result = vkAllocateCommandBuffers(device, &command_info, &command);
    if (result != VK_SUCCESS) return fail("vkAllocateCommandBuffers", result);
    const VkCommandBufferBeginInfo begin_info = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
    };
    result = vkBeginCommandBuffer(command, &begin_info);
    if (result != VK_SUCCESS) return fail("vkBeginCommandBuffer", result);
    const uint32_t pattern = 0x12345678;
    vkCmdFillBuffer(command, buffer, 0, 4096, pattern);
    const VkBufferMemoryBarrier barrier = {
        .sType = VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER,
        .srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
        .dstAccessMask = VK_ACCESS_HOST_READ_BIT,
        .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .buffer = buffer,
        .offset = 0,
        .size = 4096,
    };
    vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_HOST_BIT,
                         0, 0, NULL, 1, &barrier, 0, NULL);
    result = vkEndCommandBuffer(command);
    if (result != VK_SUCCESS) return fail("vkEndCommandBuffer", result);
    const VkSubmitInfo submit_info = {
        .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .commandBufferCount = 1,
        .pCommandBuffers = &command,
    };
    result = vkQueueSubmit(queue, 1, &submit_info, VK_NULL_HANDLE);
    if (result != VK_SUCCESS) return fail("vkQueueSubmit", result);
    result = vkQueueWaitIdle(queue);
    if (result != VK_SUCCESS) return fail("vkQueueWaitIdle", result);
    const uint32_t *words = mapped;
    for (uint32_t index = 0; index < 4096 / sizeof(*words); ++index) {
        if (words[index] != pattern) {
            fprintf(stderr, "device_fill readback mismatch: word=%u value=%08x\n", index, words[index]);
            return 6;
        }
    }
    printf("device_fill=ok words=1024 pattern=%08x\n", pattern);
    vkDestroyCommandPool(device, pool, NULL);
    vkUnmapMemory(device, memory);
    vkDestroyBuffer(device, buffer, NULL);
    vkFreeMemory(device, memory, NULL);
    vkDestroyDevice(device, NULL);
    vkDestroyInstance(instance, NULL);
    return 0;
}
