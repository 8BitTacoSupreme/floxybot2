# Rust with Flox

Flox provides the Rust toolchain (rustc, cargo, clippy, rustfmt, rust-analyzer) from Nixpkgs, replacing rustup for reproducible builds. This guide covers toolchain management, caching, system library linking, and cross-compilation in Flox environments.

## Manifest Setup

```toml
[install]
rustc.pkg-path = "rustc"
cargo.pkg-path = "cargo"
rustfmt.pkg-path = "rustfmt"
clippy.pkg-path = "clippy"
rust-analyzer.pkg-path = "rust-analyzer"

[vars]
CARGO_HOME = "${FLOX_ENV_CACHE}/cargo"
CARGO_TARGET_DIR = "${FLOX_ENV_CACHE}/target"

[hook]
on-activate = """
  mkdir -p "$CARGO_HOME" "$CARGO_TARGET_DIR"

  # Report toolchain version
  echo "Rust $(rustc --version | cut -d' ' -f2)"
"""
```

## Flox Rust vs rustup

With Flox, you do NOT use rustup. The toolchain comes from Nixpkgs and is pinned in the manifest:

| Feature | rustup | Flox |
|---------|--------|------|
| Version pinning | `rust-toolchain.toml` | `manifest.toml` version constraint |
| Components | `rustup component add` | Add packages in `[install]` |
| Targets | `rustup target add` | System-level cross packages |
| Reproducibility | Partial (channels shift) | Full (Nix derivation hash) |

If a project has a `rust-toolchain.toml`, the Flox manifest takes precedence within `flox activate`.

## Cargo Cache Management

Redirect all Cargo caches to `$FLOX_ENV_CACHE` to keep them project-scoped and persistent:

```toml
[vars]
CARGO_HOME = "${FLOX_ENV_CACHE}/cargo"
CARGO_TARGET_DIR = "${FLOX_ENV_CACHE}/target"
```

This prevents `~/.cargo` pollution and keeps build artifacts isolated per project. The `CARGO_TARGET_DIR` redirect also avoids the common issue of IDE indexers conflicting with CLI builds.

## System Library Linking

Rust crates with C dependencies (openssl-sys, libpq, etc.) need system libraries. Install them in the manifest and Flox handles linking:

```toml
[install]
rustc.pkg-path = "rustc"
cargo.pkg-path = "cargo"
openssl.pkg-path = "openssl"
openssl-dev.pkg-path = "openssl.dev"
pkg-config.pkg-path = "pkg-config"

[hook]
on-activate = """
  # Ensure pkg-config can find Flox-provided libraries
  export PKG_CONFIG_PATH="${PKG_CONFIG_PATH:+$PKG_CONFIG_PATH:}$FLOX_ENV/lib/pkgconfig"
"""
```

### Common System Dependencies

```toml
# For crates needing OpenSSL (reqwest, native-tls, etc.)
openssl.pkg-path = "openssl"
openssl-dev.pkg-path = "openssl.dev"
pkg-config.pkg-path = "pkg-config"

# For crates needing SQLite (rusqlite, diesel with sqlite)
sqlite.pkg-path = "sqlite"

# For crates needing PostgreSQL (diesel with postgres, tokio-postgres)
postgresql.pkg-path = "postgresql"

# For crates using bindgen (generating FFI bindings)
clang.pkg-path = "clang"
libclang.pkg-path = "libclang"
```

## Cross-Compilation

For cross-compiling to different targets:

```toml
[install]
rustc.pkg-path = "rustc"
cargo.pkg-path = "cargo"
# Add cross-compilation toolchain
gcc-cross.pkg-path = "pkgsCross.aarch64-multiplatform.buildPackages.gcc"

[vars]
CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER = "aarch64-unknown-linux-gnu-gcc"
```

## Build Scripts and Flox Packages

When Rust `build.rs` scripts need to find libraries, Flox packages are automatically available through standard environment variables:

```rust
// build.rs -- libraries from Flox manifest are findable
fn main() {
    // pkg-config will find openssl from the Flox environment
    pkg_config::Config::new().probe("openssl").unwrap();
}
```

## Key Principles

- Do NOT install rustup inside a Flox environment -- use Flox-managed toolchain packages
- Set `CARGO_HOME` and `CARGO_TARGET_DIR` to `$FLOX_ENV_CACHE` for isolation
- Install system libraries (openssl, sqlite, etc.) in the manifest for crates that need them
- Use `pkg-config` in the manifest to help Rust find Flox-provided C libraries
- Pin Rust version in the manifest for team-wide reproducibility
- If a crate fails to build with linker errors, check that the C library and its `.dev` package are installed
