# Release HAP dependencies

OpenHarmony's `compile_app.py` unconditionally runs `ohpm install`, including
for production HAPs whose only declared packages are test-only
`devDependencies`.  This component keeps normal dependency resolution for test
HAPs and applications with release dependencies, while allowing production
image builds with no runtime package dependencies to proceed offline.
