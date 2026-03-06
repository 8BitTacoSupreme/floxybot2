# Rust Diagnostic Patterns

## Linker Errors

**Symptoms:** `error: linker 'cc' not found`, `undefined reference to ...`, `cannot find -lssl`, `ld: library not found`.

**Diagnostic steps:**
1. Check if the error names a specific library (`-lssl`, `-lpq`, `-lsqlite3`)
2. Check if `pkg-config` is installed: `which pkg-config`
3. Check library search paths: `echo $LIBRARY_PATH` and `echo $PKG_CONFIG_PATH`
4. Check if the `.dev` (header) package is installed alongside the library

**Flox-specific causes:**
- Library installed in Flox but its `.dev` package (headers) is not
- `pkg-config` not in the manifest, so build scripts cannot find libraries
- `PKG_CONFIG_PATH` does not include `$FLOX_ENV/lib/pkgconfig`
- Nix-provided libraries have non-standard paths that Cargo's `build.rs` cannot find automatically

**Resolution pattern:**
```toml
# Add both the library AND its dev headers
[install]
openssl.pkg-path = "openssl"
openssl-dev.pkg-path = "openssl.dev"
pkg-config.pkg-path = "pkg-config"
```

```bash
# Verify pkg-config can find the library
pkg-config --libs openssl
pkg-config --cflags openssl

# If pkg-config path is wrong, add to hook
export PKG_CONFIG_PATH="$FLOX_ENV/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
```

## Missing System Libraries

**Symptoms:** `failed to run custom build command`, `could not find native static library`, `pkg-config exited with status 1`.

**Common crate-to-package mappings:**

| Crate | Flox packages needed |
|-------|---------------------|
| openssl-sys | `openssl`, `openssl.dev`, `pkg-config` |
| rusqlite | `sqlite` |
| libpq / diesel (postgres) | `postgresql`, `postgresql.lib` |
| zlib-sys | `zlib`, `zlib.dev` |
| curl-sys | `curl`, `curl.dev` |
| libgit2-sys | `libgit2` |
| rdkafka | `rdkafka`, `pkg-config` |

**Resolution pattern:**
```bash
# Find what library a crate needs
cargo build 2>&1 | grep "cannot find"
# Look for: cannot find -l<libname>
# Then: flox search <libname>
```

## Cargo Cache Corruption

**Symptoms:** `failed to parse lock file`, `checksum mismatch`, `failed to get ... from registry`.

**Diagnostic steps:**
1. Check `CARGO_HOME`: `echo $CARGO_HOME`
2. Check registry cache: `ls "$CARGO_HOME/registry/cache/"`
3. Check disk space: `df -h "$CARGO_HOME"`

**Flox-specific causes:**
- `CARGO_HOME` in `$FLOX_ENV_CACHE` was partially written during a crash
- Multiple concurrent builds writing to the same `CARGO_HOME`

**Resolution pattern:**
```bash
# Clear the cargo registry cache
rm -rf "$CARGO_HOME/registry/cache"
rm -rf "$CARGO_HOME/registry/src"

# Clear the git checkout cache
rm -rf "$CARGO_HOME/git"

# Rebuild
cargo build
```

## Target Not Installed

**Symptoms:** `error[E0463]: can't find crate for 'std'`, `no matching package found for target`.

**Cause:** In Flox, cross-compilation targets are not managed by rustup. The Nix-provided toolchain includes the host target only.

**Flox-specific causes:**
- Trying to use `rustup target add` in a Flox environment (rustup is not used)
- Cross-compilation target not available in Nixpkgs
- Missing cross-compilation toolchain packages

**Resolution pattern:**
```toml
# For cross-compilation, add the cross toolchain
[install]
rustc.pkg-path = "rustc"
cargo.pkg-path = "cargo"

# Example: cross-compile to aarch64 Linux
# Check flox search for available cross toolchains
```

```bash
# If you truly need rustup (escape hatch), install it separately
# But this is NOT recommended -- it conflicts with Flox-provided Rust
# Instead, use cargo-cross or cross-compilation Nix packages
```

## FFI Linking Failures

**Symptoms:** `error: linking with 'cc' failed`, `relocation R_X86_64_32 against...`, `undefined symbol`.

**Diagnostic steps:**
1. Check if `clang` or `gcc` is in the manifest
2. Check if `bindgen` dependencies are satisfied: `llvm`, `libclang`
3. Check `LIBCLANG_PATH`: needed by bindgen to find clang headers

**Flox-specific causes:**
- `bindgen` needs `libclang` and `LIBCLANG_PATH` set
- Mixed gcc/clang linking (some Nix packages built with gcc, project using clang)

**Resolution pattern:**
```toml
# For crates using bindgen (FFI generation)
[install]
clang.pkg-path = "clang"
libclang.pkg-path = "libclang"

[vars]
LIBCLANG_PATH = "${FLOX_ENV}/lib"
```

```bash
# Verify clang is findable
echo $LIBCLANG_PATH
ls "$LIBCLANG_PATH"/libclang*
```

## General Debugging Checklist

1. `rustc --version` -- confirms Rust is available and which version
2. `echo $CARGO_HOME` -- confirms cargo cache location
3. `echo $CARGO_TARGET_DIR` -- confirms build output location
4. `pkg-config --list-all` -- shows all findable libraries
5. `echo $PKG_CONFIG_PATH` -- confirms library search paths
6. `cargo build -vv` -- verbose output showing linker commands
