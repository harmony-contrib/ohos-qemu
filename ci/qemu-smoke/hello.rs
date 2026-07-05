use std::env;

fn main() {
    println!("hello from rust qemu smoke");
    println!("arch={}", env::consts::ARCH);
    println!("os={}", env::consts::OS);
    println!("args={:?}", env::args().collect::<Vec<_>>());
}
