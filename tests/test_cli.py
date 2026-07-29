import yaml
import pytest
from pathlib import Path
from click.testing import CliRunner

from homelab_toolkit.cli import cli, _read_config, _resolve_stack


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def valid_config():
    return {
        "homelab": {
            "name": "test",
            "network": {"subnet": "10.0.0.0/24", "gateway": "10.0.0.1"},
            "services": {"mon": {"enabled": True, "stack": ["prometheus"]}},
        }
    }


def test_init_creates_file(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        r = runner.invoke(cli, ["init", "my-lab"])
        assert r.exit_code == 0
        assert Path(td, "homelab.yaml").exists()


def test_init_override_aborts(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        Path(td, "homelab.yaml").write_text("x: 1")
        r = runner.invoke(cli, ["init"], input="n\n")
        assert r.exit_code != 0


def test_validate_ok(runner, tmp_path, valid_config):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        Path(td, "homelab.yaml").write_text(yaml.dump(valid_config))
        r = runner.invoke(cli, ["validate"])
        assert r.exit_code == 0
        assert "Config is valid" in r.output


def test_validate_missing_key(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        Path(td, "homelab.yaml").write_text("x: 1")
        r = runner.invoke(cli, ["validate"])
        assert r.exit_code != 0


def test_validate_no_file(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        r = runner.invoke(cli, ["validate"])
        assert r.exit_code != 0


def test_validate_bad_yaml(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        Path(td, "homelab.yaml").write_text("{{invalid: [yaml]")
        r = runner.invoke(cli, ["validate"])
        assert r.exit_code != 0
        assert "Invalid YAML" in r.output


def test_generate_dry_run(runner, tmp_path, valid_config):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        Path(td, "homelab.yaml").write_text(yaml.dump(valid_config))
        r = runner.invoke(cli, ["generate", "--dry-run", "-o", str(td)])
        assert r.exit_code == 0
        assert "Docker" in r.output
        assert "Terraform" in r.output
        assert "Ansible" in r.output


def test_generate_with_custom_config(runner, tmp_path, valid_config):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        cfg = Path(td, "my-config.yaml")
        cfg.write_text(yaml.dump(valid_config))
        r = runner.invoke(cli, ["-c", str(cfg), "generate", "--dry-run", "-o", str(td)])
        assert r.exit_code == 0
        assert "Docker" in r.output


def test_template_list(runner):
    r = runner.invoke(cli, ["template", "list"])
    assert r.exit_code == 0
    assert "prometheus" in r.output
    assert "22" in r.output or "templates" in r.output


def test_template_show(runner):
    r = runner.invoke(cli, ["template", "show", "postgres"])
    assert r.exit_code == 0
    assert "postgres:16-alpine" in r.output


def test_template_show_unknown(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        r = runner.invoke(cli, ["template", "show", "nope"])
        assert r.exit_code != 0
        assert "Unknown" in r.output


def test_backup_no_file(runner):
    r = runner.invoke(cli, ["backup", "restore"])
    assert r.exit_code != 0
    assert "--file" in r.output


def test_backup_create_and_restore(runner, tmp_path, valid_config):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        td = Path(td)
        (td / "homelab.yaml").write_text(yaml.dump(valid_config))
        r = runner.invoke(cli, ["backup", "create", "-o", str(td / "backups")])
        assert r.exit_code == 0
        backups = list((td / "backups").glob("*.tar.gz"))
        assert len(backups) == 1


def test_clean_no_output(runner):
    r = runner.invoke(cli, ["clean"])
    assert r.exit_code == 0


def test_read_config():
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("homelab:\n  name: test\n")
        path = f.name
    cfg = _read_config(path)
    assert cfg["homelab"]["name"] == "test"
    Path(path).unlink()


def test_read_config_not_found():
    from click.exceptions import Abort
    with pytest.raises(Abort):
        _read_config("/nonexistent/file.yaml")


def test_resolve_stack(runner, tmp_path, valid_config):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        cfg = Path(td, "homelab.yaml")
        cfg.write_text(yaml.dump(valid_config))
        services = _resolve_stack("mon", str(cfg))
        assert services == ["prometheus"]


def test_resolve_stack_fallback(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        cfg = Path(td, "homelab.yaml")
        cfg.write_text("homelab:\n  services: {}\n")
        services = _resolve_stack("direct-svc", str(cfg))
        assert services == ["direct-svc"]


def test_down_no_compose(runner):
    r = runner.invoke(cli, ["down"])
    assert r.exit_code == 0


def test_pull_no_compose(runner):
    r = runner.invoke(cli, ["pull"])
    assert r.exit_code == 0
