# Docker and Containers with Flox

Flox integrates with container workflows through `flox containerize` for building OCI images from environments, and through standard Docker/Podman tooling managed in the manifest.

## Manifest Setup

```toml
[install]
docker.pkg-path = "docker"
podman.pkg-path = "podman"
docker-compose.pkg-path = "docker-compose"
dive.pkg-path = "dive"
skopeo.pkg-path = "skopeo"

[hook]
on-activate = """
  # Verify container runtime is available
  if docker info &>/dev/null 2>&1; then
    echo "Docker daemon available"
  elif podman info &>/dev/null 2>&1; then
    echo "Podman available"
  else
    echo "WARNING: No container runtime detected"
  fi
"""
```

## flox containerize

`flox containerize` converts a Flox environment into an OCI container image without writing a Dockerfile. The image contains all packages from the manifest plus hooks and services.

```bash
# Build an OCI image from the current environment
flox containerize -o myapp.tar.gz

# Load into Docker
docker load < myapp.tar.gz

# Or pipe directly
flox containerize | docker load
```

### When to Use containerize vs Dockerfile

Use `flox containerize` when:
- Your application is fully described by the Flox manifest
- You want reproducible, Nix-backed container images
- You need minimal image size (no package manager bloat)

Use a Dockerfile when:
- You need multi-stage builds with non-Flox base images
- Your deployment target requires a specific base image
- You need fine-grained layer control for caching

### Debugging containerize Output

Inspect the generated image:

```bash
flox containerize | docker load
dive myapp:latest  # Inspect layers
docker run --rm -it myapp:latest /bin/sh  # Interactive shell
```

## Dockerfile to Manifest Migration

Replace Dockerfile `RUN apt-get install` with Flox packages:

```dockerfile
# Before (Dockerfile)
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y python3 postgresql-client curl
```

```toml
# After (manifest.toml)
[install]
python3.pkg-path = "python3"
postgresql.pkg-path = "postgresql"
curl.pkg-path = "curl"
```

## Docker Compose Integration

Use Flox to manage the compose tooling while compose orchestrates multi-container stacks:

```toml
[services]
compose-up.command = "docker-compose -f $FLOX_ENV_PROJECT/docker-compose.yml up"
```

Bind-mount the project for live reload in development:

```yaml
# docker-compose.yml
services:
  app:
    build: .
    volumes:
      - .:/app
    ports:
      - "8080:8080"
```

## Podman Rootless Setup

For environments without Docker daemon access:

```toml
[install]
podman.pkg-path = "podman"

[vars]
DOCKER_HOST = "unix://${XDG_RUNTIME_DIR}/podman/podman.sock"

[hook]
on-activate = """
  # Ensure podman socket is running for Docker-compatible tools
  if command -v podman &>/dev/null; then
    podman system service --time=0 &>/dev/null &
  fi
"""
```

## Image Inspection with Skopeo

Inspect remote images without pulling them:

```bash
skopeo inspect docker://ghcr.io/flox/flox:latest
skopeo copy docker://source:tag docker://dest:tag
```

## Key Principles

- Prefer `flox containerize` over Dockerfiles when the manifest fully describes the image
- Use `dive` to inspect image layers and identify bloat
- Store Docker config in `$FLOX_ENV_CACHE` if project-specific auth is needed
- Use Podman as a rootless drop-in when Docker daemon is unavailable
- Bind mounts in compose should reference `$FLOX_ENV_PROJECT` for portability
- Always check for a running container runtime in hooks before dependent operations
