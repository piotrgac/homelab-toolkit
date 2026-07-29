# Changelog

## [0.2.0] - 2026-07-29

### Fixed
- **Terraform generator**: Fixed HCL syntax — double braces `${{local.name}}` → correct `${local.name}` interpolation
- **Ansible generator**: `site.yml` now pulls correct Docker images (full image names like `prom/prometheus:v2.53.0`) instead of service keys
- **Ansible generator**: Fixed `pipx` syntax (incorrect `packages` parameter)
- **Docker generator**: Now respects `homelab.network.subnet` from config instead of hardcoding `172.20.0.0/16`
- **Docker generator**: `.env` parsing uses regex instead of fragile `split(":-")`
- **CLI `deploy --stack`**: Now resolves category names to service names before passing to `docker compose`
- **CLI `logs --stack`**: Same fix as deploy
- **CLI `backup restore`**: Replaced insecure `tar xzf` subprocess with Python `tarfile` with path traversal validation
- **CLI `clean`**: Removed automatic `sudo rm -rf` fallback (safety red flag)
- **CLI exit codes**: `deploy`, `status`, `logs`, `validate` now return non-zero on failure
- **CLI YAML loading**: Added `try/except yaml.YAMLError` for user-friendly error messages
- **CLI `backup create`**: Uses `datetime.now()` instead of GNU-only `date` command
- **Config validation**: Added subnet format validation via `validate_subnet()`
- **Port checker**: Now handles `list` and `str` port types in addition to `int`
- **Port checker**: Added guard for `None` service configs
- **Docker generator**: Added guard for `services` being a list
- **Ansible generator**: Added guard for `services` not being a dict in `_write_monitoring_playbook`
- **README**: Fixed template count (23→22), test count (22→32), removed references to deleted files (`config_parser.py`, `templates.py`), removed `version: "3.8"` from examples
- **`.env.example`**: Removed unused vars, fixed `PIHOLE_PASSWORD` naming

### Changed
- **Docker image tags**: All 22 templates now pin specific versions instead of `:latest`
- **Pi-hole timezone**: `Europe/Warsaw` → `UTC`
- **Vault template**: Added persistent volume `./data/vault:/vault/file`
- **Alertmanager template**: Added config volume `./data/alertmanager:/etc/alertmanager`
- **Requirements**: Removed unused `jinja2` and `pydantic` dependencies
- **Deleted `modules/`**: Removed 5 dead code files (`monitoring.py`, `networking.py`, etc.)
- **Deleted `config/config_parser.py`**: Dead code
- **Deleted `utils/templates.py`**: Dead code

### Added
- **Global `--config` / `-c` flag**: All commands accept `--config` to specify a custom config path (also via `HOMELAB_CONFIG` env var)
- **`homelab down`**: Stop and remove containers
- **`homelab pull`**: Pull latest service images
- **GitHub Actions CI**: Automated test suite on push/PR

### Security
- **Backup restore**: Path traversal protection (rejects `..`, absolute paths, symlinks)
- **No automatic privilege escalation**: `clean` no longer executes `sudo rm -rf`

[0.2.0]: https://github.com/piotrgac/homelab-toolkit/releases/tag/v0.2.0
