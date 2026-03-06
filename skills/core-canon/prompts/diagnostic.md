# Core Flox Diagnostic Prompts

## Environment Won't Activate
- Check `flox activate` exit code and stderr
- Verify manifest.toml syntax: `flox edit` should open without errors
- Check for circular dependencies in `[install]`
- Verify system compatibility: `flox config --list` for current system

## Package Not Found
- Search the catalog: `flox search <pkg>`
- Check pkg-path vs package name (e.g., `nodejs_22` not `node`)
- Verify `options.systems` includes the current platform
- Try `flox show <pkg>` to see available versions

## Hook Failures
- Hooks must use `return` not `exit` (exit kills the shell)
- Check hook idempotency — hooks run on every activation
- Use `flox activate -- bash -x` to trace hook execution
- Verify environment variables with `flox activate -- env | grep FLOX`

## Service Issues
- Check service logs: `flox services logs <name>`
- Verify `command` field runs standalone: `flox activate -- <command>`
- For daemon services, ensure `is-daemon = true` is set
- Check port conflicts with `lsof -i :<port>`
