#[test]
fn runs_inside_openharmony_qemu() {
    println!("ohos-test-runner smoke executed");
    println!("arch={}", std::env::consts::ARCH);
    println!("os={}", std::env::consts::OS);
    assert!(matches!(std::env::consts::ARCH, "arm" | "aarch64" | "x86_64"));
}
