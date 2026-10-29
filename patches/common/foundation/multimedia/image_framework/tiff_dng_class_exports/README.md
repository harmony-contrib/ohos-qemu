# Dynamic DNG / TIFF metadata records

Pinned image_framework: `711db218c8d1c4d6546b28d8cf466059644dfa77`.

Exports the API 26 record classes and makes the existing parsed DNG/TIFF factories
return their instances. Constructor references belong to the NAPI environment and
are released by its cleanup hook. Empty instances have no shared/default parser
state. Existing parsers, fields, errors, permissions and public C++ ABI are unchanged.

Registration is reached through the existing Avis initializer, after the separate
Avis export component. This component does not modify the module-entry file, so
both components remain independently exact-state checked and repeatable.

`compile_tiff_dng_classes.py` compiles the actual TU against all three product
commands. `test_tiff_dng_class_exports.py` executes the patched lifecycle code.
The image-metadata HAP additionally requires public construction, parsed instance
prototypes, real values, invalid-index numeric errors and recovery. Compilation
does not replace booting and testing a newly packaged image.
