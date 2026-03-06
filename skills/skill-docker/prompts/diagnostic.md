# Docker Diagnostic Patterns

## Daemon Not Running

**Symptoms:** `Cannot connect to the Docker daemon`, `Is the docker daemon running?`, `connection refused`.

**Diagnostic steps:**
1. Check Docker socket: `ls -la /var/run/docker.sock`
2. Check Docker service: `docker info`
3. For Podman: `podman info`
4. Check `DOCKER_HOST` env var: `echo $DOCKER_HOST`

**Flox-specific causes:**
- Flox installs the Docker CLI but does not start the daemon (daemon runs at system level)
- `DOCKER_HOST` set to Podman socket but Podman service not started
- On macOS: Docker Desktop not running
- On Linux: Docker service not enabled/started with systemd

**Resolution pattern:**
```bash
# macOS: Start Docker Desktop
open -a Docker

# Linux: Start Docker daemon
sudo systemctl start docker

# If using Podman as backend
podman system service --time=0 &
export DOCKER_HOST="unix://${XDG_RUNTIME_DIR}/podman/podman.sock"
```

## Permission Denied

**Symptoms:** `Got permission denied while trying to connect to the Docker daemon socket`, `dial unix /var/run/docker.sock: permission denied`.

**Diagnostic steps:**
1. Check socket permissions: `ls -la /var/run/docker.sock`
2. Check user groups: `groups`
3. Check if user is in docker group: `getent group docker`

**Resolution pattern:**
```bash
# Add user to docker group (Linux)
sudo usermod -aG docker $USER
# Then log out and back in (or newgrp docker)

# Alternative: Use Podman (rootless, no daemon)
```

## Image Build Failures

**Symptoms:** Various errors during `docker build`.

### "COPY failed: file not found"
- Check `.dockerignore` is not excluding needed files
- Check build context (the `.` in `docker build .`)
- Paths in COPY are relative to the build context

### "RUN apt-get install failed"
- Network issues inside the build
- Package name wrong or repository outdated

**Flox-specific causes (flox containerize):**
- Missing runtime dependency in manifest `[install]`
- Hook script references a binary not in the manifest
- Service command has a hardcoded path instead of using Flox-provided paths

**Resolution pattern:**
```bash
# Debug flox containerize output
flox containerize | docker load
docker run --rm -it <image> /bin/sh

# Check what's inside the container
docker run --rm <image> ls /usr/bin/
docker run --rm <image> which python3
```

## Volume Mount Issues

**Symptoms:** `Mounts denied`, empty directories inside container, permission errors on mounted files.

**Diagnostic steps:**
1. Check path exists on host: `ls -la /path/to/mount`
2. Check Docker Desktop file sharing settings (macOS/Windows)
3. Check SELinux labels (Linux): may need `:z` or `:Z` suffix
4. Check container user vs host file ownership

**Flox-specific causes:**
- Mounting `$FLOX_ENV_PROJECT` but the variable is not expanded in the compose file
- Mounting `$FLOX_ENV_CACHE` which may not exist yet

**Resolution pattern:**
```yaml
# docker-compose.yml -- use explicit paths, not Flox vars
services:
  app:
    volumes:
      - ./src:/app/src     # Relative to compose file location
      - ./data:/app/data

# For SELinux (Fedora/RHEL)
    volumes:
      - ./src:/app/src:z   # Shared label
```

## containerize Output Debugging

**Symptoms:** `flox containerize` produces an image but the container fails at runtime.

**Diagnostic steps:**
1. Load and inspect: `flox containerize | docker load && dive <image>`
2. Check layers for expected binaries
3. Run shell in the container: `docker run --rm -it <image> /bin/sh`
4. Check environment variables: `docker run --rm <image> env`

**Common issues:**
- Missing dynamically linked libraries (binary works on host but not in container)
- Environment variables from `[vars]` not available at container runtime
- Services defined in manifest but no init system to start them

**Resolution pattern:**
```bash
# Check for missing libraries
docker run --rm <image> ldd /path/to/binary

# Check if hooks ran
docker run --rm <image> cat /etc/profile.d/flox.sh

# Inspect image layers
dive <image>
```

## General Debugging Checklist

1. `docker info` -- confirms daemon is running and accessible
2. `docker version` -- confirms client and server versions match
3. `docker ps -a` -- shows running and stopped containers
4. `docker images` -- shows available images
5. `docker system df` -- shows disk usage (full disk causes build failures)
6. `docker logs <container>` -- shows container output
