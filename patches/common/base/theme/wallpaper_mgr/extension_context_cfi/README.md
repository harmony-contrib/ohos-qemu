# extension_context_cfi

Wraps `new std::weak_ptr<AbilityRuntime::Context>(context)` on the JS `WallpaperExtensionContext` object so `windowStage.loadContent` unwraps a valid `weak_ptr<Context>` instead of reinterpreting a raw `WallpaperExtensionContext` and crashing `com.ohos.wallpaper` under Clang CFI.
