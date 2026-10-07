// Include the exact RotJpegImg body extracted by the validator. Every JPEG
// operation below calls the genuine libjpeg-turbo 3.1 implementation.
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
extern "C" {
#include <jpeglib.h>
#include <transupp.h>
}

static bool tracking = false;
static int created = 0;
static int destroyed = 0;
static int destinations = 0;
extern "C" {
void __real_jpeg_CreateCompress(j_compress_ptr, int, size_t);
void __real_jpeg_CreateDecompress(j_decompress_ptr, int, size_t);
void __real_jpeg_destroy_compress(j_compress_ptr);
void __real_jpeg_destroy_decompress(j_decompress_ptr);
void __real_jpeg_mem_dest(j_compress_ptr, unsigned char **, unsigned long *);
void __wrap_jpeg_CreateCompress(j_compress_ptr info, int version, size_t size)
{
    __real_jpeg_CreateCompress(info, version, size);
    if (tracking) ++created;
}
void __wrap_jpeg_CreateDecompress(j_decompress_ptr info, int version, size_t size)
{
    __real_jpeg_CreateDecompress(info, version, size);
    if (tracking) ++created;
}
void __wrap_jpeg_destroy_compress(j_compress_ptr info)
{
    __real_jpeg_destroy_compress(info);
    if (tracking) ++destroyed;
}
void __wrap_jpeg_destroy_decompress(j_decompress_ptr info)
{
    __real_jpeg_destroy_decompress(info);
    if (tracking) ++destroyed;
}
void __wrap_jpeg_mem_dest(j_compress_ptr info, unsigned char **buffer, unsigned long *size)
{
    __real_jpeg_mem_dest(info, buffer, size);
    if (tracking) ++destinations;
}
}

// The Camera logger is immaterial to this host-only function regression.
#define CAMERA_LOGE(...) ((void)0)
#include "rotation_under_test.inc"

static void require(bool condition, const char *message)
{
    if (!condition) {
        std::fprintf(stderr, "FAIL: %s\n", message);
        std::exit(2);
    }
}

static void add16(std::vector<uint8_t>& bytes, uint16_t value)
{
    bytes.push_back(value & 255);
    bytes.push_back(value >> 8);
}

static void add32(std::vector<uint8_t>& bytes, uint32_t value)
{
    add16(bytes, value & 65535);
    add16(bytes, value >> 16);
}

static void entry(std::vector<uint8_t>& bytes, uint16_t tag, uint16_t type, uint32_t value)
{
    add16(bytes, tag);
    add16(bytes, type);
    add32(bytes, 1);
    add32(bytes, value);
}

static std::vector<uint8_t> exif(unsigned width, unsigned height)
{
    std::vector<uint8_t> bytes = {'E', 'x', 'i', 'f', 0, 0, 'I', 'I', 42, 0, 8, 0, 0, 0};
    add16(bytes, 2);
    entry(bytes, 0x0112, 3, 1); // Existing Orientation=1 remains unchanged.
    entry(bytes, 0x8769, 4, 38);
    add32(bytes, 0);
    add16(bytes, 2);
    entry(bytes, 0xa002, 4, width);
    entry(bytes, 0xa003, 4, height);
    add32(bytes, 0);
    return bytes;
}

static const std::vector<uint8_t> comment = {'c', 'a', 'm', 'e', 'r', 'a', '-', 'c', 'o', 'm'};
static const std::vector<uint8_t> icc = {'I', 'C', 'C', '_', 'P', 'R', 'O', 'F', 'I', 'L', 'E', 0, 1, 1, 17, 23};
static const std::vector<uint8_t> app3 = {'c', 'a', 'm', 'e', 'r', 'a', '-', 'a', 'p', 'p', '3'};

static std::vector<uint8_t> encode(unsigned width, unsigned height)
{
    jpeg_compress_struct info = {};
    jpeg_error_mgr errors;
    info.err = jpeg_std_error(&errors);
    jpeg_create_compress(&info);
    uint8_t *buffer = nullptr;
    unsigned long size = 0;
    jpeg_mem_dest(&info, &buffer, &size);
    info.image_width = width;
    info.image_height = height;
    info.input_components = 3;
    info.in_color_space = JCS_RGB;
    jpeg_set_defaults(&info);
    for (int i = 0; i < 3; ++i) {
        info.comp_info[i].h_samp_factor = 1;
        info.comp_info[i].v_samp_factor = 1;
    }
    info.write_JFIF_header = FALSE; // EXIF is the first saved marker.
    jpeg_set_quality(&info, 95, TRUE);
    jpeg_start_compress(&info, TRUE);
    const auto metadata = exif(width, height);
    jpeg_write_marker(&info, JPEG_APP0 + 1, metadata.data(), metadata.size());
    jpeg_write_marker(&info, JPEG_APP0 + 2, icc.data(), icc.size());
    jpeg_write_marker(&info, JPEG_APP0 + 3, app3.data(), app3.size());
    jpeg_write_marker(&info, JPEG_COM, comment.data(), comment.size());
    std::vector<uint8_t> row(width * 3);
    while (info.next_scanline < height) {
        for (unsigned x = 0; x < width; ++x) {
            row[x * 3] = 20 + (x / 8) * 40;
            row[x * 3 + 1] = 15 + (info.next_scanline / 8) * 30;
            row[x * 3 + 2] = 35 + ((x / 8 + info.next_scanline / 8) % 4) * 45;
        }
        JSAMPROW pointer = row.data();
        jpeg_write_scanlines(&info, &pointer, 1);
    }
    jpeg_finish_compress(&info);
    jpeg_destroy_compress(&info);
    std::vector<uint8_t> result(buffer, buffer + size);
    std::free(buffer);
    return result;
}

struct Image {
    unsigned width;
    unsigned height;
    std::vector<uint8_t> rgb;
};

static Image decode(const uint8_t *bytes, size_t size, unsigned width, unsigned height)
{
    jpeg_decompress_struct info = {};
    jpeg_error_mgr errors;
    info.err = jpeg_std_error(&errors);
    jpeg_create_decompress(&info);
    jcopy_markers_setup(&info, JCOPYOPT_ALL);
    jpeg_mem_src(&info, bytes, size);
    jpeg_read_header(&info, TRUE);
    require(info.image_width == width && info.image_height == height, "JPEG dimensions");
    const auto expectedExif = exif(width, height);
    int counts[4] = {};
    for (auto marker = info.marker_list; marker != nullptr; marker = marker->next) {
        const std::vector<uint8_t> *expected = nullptr;
        int index = -1;
        if (marker->marker == JPEG_APP0 + 1) { expected = &expectedExif; index = 0; }
        if (marker->marker == JPEG_APP0 + 2) { expected = &icc; index = 1; }
        if (marker->marker == JPEG_APP0 + 3) { expected = &app3; index = 2; }
        if (marker->marker == JPEG_COM) { expected = &comment; index = 3; }
        if (expected) {
            ++counts[index];
            require(marker->data_length == expected->size() &&
                    std::memcmp(marker->data, expected->data(), expected->size()) == 0,
                    "EXIF dimensions/orientation or ICC/APP3/comment payload changed");
        }
    }
    for (int count : counts) require(count == 1, "optional marker missing or duplicated");
    info.out_color_space = JCS_RGB;
    jpeg_start_decompress(&info);
    Image image{width, height, std::vector<uint8_t>(width * height * 3)};
    while (info.output_scanline < info.output_height) {
        JSAMPROW row = image.rgb.data() + info.output_scanline * width * 3;
        jpeg_read_scanlines(&info, &row, 1);
    }
    jpeg_finish_decompress(&info);
    jpeg_destroy_decompress(&info);
    return image;
}

static void rotate(const std::vector<uint8_t>& input, JXFORM_CODE rotation,
                   uint8_t **buffer, size_t *size)
{
    created = destroyed = destinations = 0;
    tracking = true;
    RotJpegImg(input.data(), input.size(), buffer, size, rotation);
    tracking = false;
    require(created == 2 && destroyed == 2, "JPEG objects leaked on transform exit");
}

static void rejection(unsigned width, unsigned height, JXFORM_CODE rotation)
{
    const auto input = encode(width, height);
    const auto original = input;
    uint8_t *buffer = nullptr;
    size_t size = 0;
    rotate(input, rotation, &buffer, &size);
    require(destinations == 0 && buffer == nullptr && size == 0, "rejected workspace allocated an output");
    require(input == original, "rejected rotation changed fallback JPEG");
    decode(input.data(), input.size(), width, height);
}

static void accepted(unsigned width, unsigned height, JXFORM_CODE rotation)
{
    const auto input = encode(width, height);
    const auto original = input;
    const Image before = decode(input.data(), input.size(), width, height);
    uint8_t *buffer = nullptr;
    size_t size = 0;
    rotate(input, rotation, &buffer, &size);
    require(destinations == 1 && buffer != nullptr && size != 0, "accepted rotation has no output");
    const bool swap = rotation == JXFORM_ROT_90 || rotation == JXFORM_ROT_270;
    const Image after = decode(buffer, size, swap ? height : width, swap ? width : height);
    for (unsigned y = 0; y < after.height; ++y) {
        for (unsigned x = 0; x < after.width; ++x) {
            unsigned sx = x, sy = y;
            if (rotation == JXFORM_ROT_90) { sx = y; sy = height - 1 - x; }
            if (rotation == JXFORM_ROT_180) { sx = width - 1 - x; sy = height - 1 - y; }
            if (rotation == JXFORM_ROT_270) { sx = width - 1 - y; sy = x; }
            for (unsigned channel = 0; channel < 3; ++channel) {
                const int delta = int(after.rgb[(y * after.width + x) * 3 + channel]) -
                                  int(before.rgb[(sy * width + sx) * 3 + channel]);
                require(std::abs(delta) <= 3, "decoded pixels have incorrect rotation");
            }
        }
    }
    require(input == original, "accepted rotation changed input JPEG");
    std::free(buffer);
}

int main(int argc, char **argv)
{
    // The original implementation deterministically fails this resource check.
    rejection(17, 19, JXFORM_ROT_90);
    if (argc == 2 && std::strcmp(argv[1], "rejection-only") == 0) return 0;
    for (JXFORM_CODE rotation : {JXFORM_NONE, JXFORM_ROT_90, JXFORM_ROT_180, JXFORM_ROT_270})
        accepted(32, 48, rotation);
    accepted(17, 19, JXFORM_NONE);
    accepted(17, 24, JXFORM_ROT_90); // Only height alignment is required for 90.
    accepted(24, 19, JXFORM_ROT_270); // Only width alignment is required for 270.
    rejection(17, 19, JXFORM_ROT_180);
    rejection(17, 19, JXFORM_ROT_270);
    rejection(24, 19, JXFORM_ROT_90);
    rejection(17, 24, JXFORM_ROT_270);
    for (int iteration = 0; iteration < 400; ++iteration)
        rejection(17, 19, JXFORM_ROT_180);
    std::puts("PASS: 0/90/180/270 pixels, EXIF/ICC/APP3/COM, MCU boundaries, 400 clean rejections");
    return 0;
}
