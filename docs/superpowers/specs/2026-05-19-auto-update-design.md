# Auto-Update Design for Taxo CLI

## Overview

Add an auto-update system to Taxo that checks GitHub Releases for new versions and allows users to upgrade via `taxo update`. Two modes: passive check (hint on every run) and active update (download and replace).

## Version Detection

- Query GitHub Releases API: `https://api.github.com/repos/Lemon-cc-hang/taxo/releases/latest`
- Parse `tag_name` (strip `v` prefix), compare with current version using semantic versioning
- Cache check results in `~/.taxo/update_cache.json` with 24-hour TTL
- Cache structure:
  ```json
  {
    "last_check": "2026-05-19T12:00:00",
    "latest_version": "0.3.0",
    "download_url": "https://github.com/.../taxo-macos-arm64",
    "asset_name": "taxo-macos-arm64"
  }
  ```

## Install Method Detection

- `sys.frozen` (set by PyInstaller) → binary update path
- Not frozen → pip update path (`sys.executable -m pip install --upgrade taxo`)

## Passive Check (every run)

- In `cli()` main group callback, check if cache is stale (>24h)
- If stale, call GitHub API (non-blocking, <1s)
- If new version available, append yellow hint line after command output:
  ```
  ⬆ New version available: 0.2.0 → 0.3.0. Run `taxo update` to upgrade.
  ```
- If API unreachable, silently skip — never block normal operation

## Active Update (`taxo update` command)

### Binary update flow:
1. Detect platform: `platform.system()` + `platform.machine()` → match release asset
2. Platform map:
   ```python
   PLATFORM_MAP = {
     ("Darwin", "arm64"): "taxo-macos-arm64",
     ("Linux", "x86_64"): "taxo-linux-x86_64",
     ("Windows", "AMD64"): "taxo-windows-x86_64.exe",
   }
   ```
3. Download to `~/.taxo/tmp/taxo-new` with Rich progress bar
4. Replace:
   - POSIX: `os.rename(tmp, current_binary)` — atomic
   - Windows: rename old to `.old`, rename new in, delete `.old`
5. Set executable permission (POSIX): `os.chmod(new, 0o755)`
6. Clean temp files

### Pip update flow:
1. Detect non-frozen installation
2. Run `sys.executable -m pip install --upgrade taxo`
3. Report result

### Output examples:

Update available:
```
$ taxo update
Checking for updates...
Current version: 0.2.0
Latest version:  0.3.0

Update available! Downloading taxo-macos-arm64...
████████████████████████████████████████ 12.3 MB/12.3 MB

Replacing binary... Done!
Updated to 0.3.0 successfully.
```

Already up to date:
```
$ taxo update
Already up to date (v0.3.0).
```

## Error Handling

- GitHub API unreachable → silent skip for passive, error message for `taxo update`
- Download failure → clean temp files, report error
- Replace failure (permissions) → suggest `sudo` or manual download
- Version parse failure → skip, never crash
- Unsupported platform → message: "Auto-update not available for this platform. Please download manually from https://github.com/Lemon-cc-hang/taxo/releases"

## Data Model

```python
class UpdateInfo(BaseModel):
    current_version: str
    latest_version: str
    download_url: str | None = None
    is_frozen: bool
    asset_name: str | None = None
```

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/taxo/updater.py` | New — check, download, replace logic |
| `src/taxo/cli.py` | Modify — add `taxo update` command, passive check hint |
| `src/taxo/__init__.py` | Modify — bump version to 0.2.0 |
| `pyproject.toml` | Modify — bump version to 0.2.0 |
| `tests/test_updater.py` | New — version comparison, platform detection, binary replace (mocked) |

## Constraints

- Zero external dependencies for update logic (httpx already available)
- Passive check must never delay or block normal CLI operation
- `taxo update` for pip installs just runs pip upgrade, no custom logic
- Binary replace must be atomic on POSIX, safe on Windows