cmake_minimum_required(VERSION 3.6)

project(ImageEditor CXX)

option (ENABLE_HITEST_COV "Use hitest cov" OFF)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set (CMAKE_CXX_FLAGS_DEBUG "-w -O0 -g")
set (CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O2 -fstack-protector-all -D_FORTIFY_SOURCE=2")

set (CMAKE_SKIP_RPATH TRUE)

if(ENABLE_HITEST_COV)
    set_property(GLOBAL PROPERTY RULE_LAUNCH_COMPILE hitestwrapper)
    set_property(GLOBAL PROPERTY RULE_LAUNCH_LINK hitestwrapper)
endif()

set(SRC_DIR 	${PROJECT_SOURCE_DIR}/../../src)
set(LIBS_DIR	${PROJECT_SOURCE_DIR}/../../libs)
set(PAF_LIBS_DIR	${PROJECT_SOURCE_DIR}/../../../../../../oh_modules)

include_directories(${PROJECT_SOURCE_DIR}/../../include)
include_directories(${PROJECT_SOURCE_DIR}/../../interface)

include_directories(${SRC_DIR}/Base)
include_directories(${SRC_DIR}/Engine)
include_directories(${SRC_DIR}/Service)
include_directories(${SRC_DIR}/Bridge)

include_directories(${LIBS_DIR}/JsonCpp/include)

link_directories(${LIBS_DIR}/JsonCpp/ohos/${OHOS_ARCH})

file(GLOB_RECURSE BASE_SRC        "${SRC_DIR}/Base/*.cpp")
file(GLOB_RECURSE ENGINE_IMAGE_SRC      "${SRC_DIR}/Engine/image/*.cpp")
file(GLOB_RECURSE ENGINE_RENDER_SRC     "${SRC_DIR}/Engine/render/*.cpp")
file(GLOB_RECURSE BRIDGE_SRC      "${SRC_DIR}/Bridge/*.cpp")
file(GLOB_RECURSE SERVICE_SRC      "${SRC_DIR}/Service/*.cpp")
add_library(${PROJECT_NAME} SHARED  ${BASE_SRC} ${ENGINE_AIRETOUCH_SRC} ${ENGINE_IMAGE_SRC} ${ENGINE_RENDER_SRC} ${BRIDGE_SRC} ${SERVICE_SRC})

target_link_libraries(${PROJECT_NAME} PRIVATE
    EGL
    GLESv3
    ace_ndk.z
    ace_napi.z
    uv
    hilog_ndk.z
    hitrace_ndk.z
    pixelmap_ndk.z
    OpenSLES
    JsonCpp
    native_media_codecbase
    native_media_vdec
    native_media_venc
    native_media_core
    native_media_adec
    native_media_aenc
    native_image
    native_buffer
    image_effect
    image_source_ndk.z
    image_source
    pixelmap
    picture
    native_color_space_manager
    image_common
    image_packer
    native_window
    rawfile.z
    ffrt.z
    z
    mindspore_lite_ndk
    hilog_ndk.z
    rawfile.z
    ace_napi.z
    native_vsync)

#裁剪包大小，本地编译不开启，流水线开启（gradlew配置）
add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD COMMAND ${CMAKE_STRIP} -s ${CMAKE_LIBRARY_OUTPUT_DIRECTORY}/lib${PROJECT_NAME}.so)
