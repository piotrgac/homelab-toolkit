import os
import yaml
import pytest
from pathlib import Path

from homelab_toolkit.generators.docker_generator import DockerGenerator, SERVICE_TEMPLATES
from homelab_toolkit.generators.terraform_generator import TerraformGenerator
from homelab_toolkit.generators.ansible_generator import AnsibleGenerator
from homelab_toolkit.validators.config_validator import ConfigValidator
from homelab_toolkit.validators.port_checker import PortChecker
from homelab_toolkit.utils.network import validate_subnet


@pytest.fixture
def full_config():
    return yaml.safe_load("""
homelab:
  name: "test-homelab"
  network:
    subnet: "10.0.0.0/24"
    gateway: "10.0.0.1"
  services:
    monitoring:
      enabled: true
      stack: [prometheus, grafana]
    media:
      enabled: true
      stack: [jellyfin, radarr]
    apps:
      enabled: true
      stack: [my-app]
backup:
  enabled: true
  retention_days: 7
  destination: "/mnt/backup"
custom_templates:
  my-app:
    image: "my-app:latest"
    ports: ["3000:3000"]
""")


@pytest.fixture
def minimal():
    return yaml.safe_load("""
homelab:
  name: "minimal"
  network:
    subnet: "10.0.0.0/24"
    gateway: "10.0.0.1"
  services:
    mon:
      enabled: true
      stack: [prometheus]
""")


class TestConfigValidator:
    def test_valid(self, full_config):
        assert ConfigValidator().validate(full_config) == []

    def test_minimal(self, minimal):
        assert ConfigValidator().validate(minimal) == []

    def test_no_homelab(self):
        e = ConfigValidator().validate({})
        assert any("homelab" in x for x in e)

    def test_bad_service(self):
        cfg = yaml.safe_load("""
homelab:
  name: x
  network:
    subnet: "10.0.0.0/24"
    gateway: "10.0.0.1"
  services:
    x:
      enabled: true
      stack: [nie-ma]
""")
        e = ConfigValidator().validate(cfg)
        assert any("nie-ma" in x for x in e)

    def test_custom_template_ok(self):
        cfg = yaml.safe_load("""
homelab:
  name: x
  network:
    subnet: "10.0.0.0/24"
    gateway: "10.0.0.1"
  services:
    x:
      enabled: true
      stack: [my-app]
custom_templates:
  my-app:
    image: "my-app:latest"
""")
        assert ConfigValidator().validate(cfg) == []

    def test_custom_no_image(self):
        cfg = yaml.safe_load("""
homelab:
  name: x
  network:
    subnet: "10.0.0.0/24"
    gateway: "10.0.0.1"
  services:
    x:
      enabled: true
      stack: [x]
custom_templates:
  x:
    ports: ["3000:3000"]
""")
        e = ConfigValidator().validate(cfg)
        assert any("image" in x for x in e)

    def test_services_list_instead_of_dict(self):
        cfg = yaml.safe_load("""
homelab:
  name: x
  network:
    subnet: "10.0.0.0/24"
    gateway: "10.0.0.1"
  services: [prometheus]
""")
        e = ConfigValidator().validate(cfg)
        assert any("dictionary" in x for x in e)

    def test_services_none(self):
        cfg = yaml.safe_load("""
homelab:
  name: x
  network:
    subnet: "10.0.0.0/24"
    gateway: "10.0.0.1"
  services:
backup:
  enabled: true
""")
        e = ConfigValidator().validate(cfg)
        assert any("services" in x for x in e)


class TestDockerGenerator:
    def test_generates(self, full_config, tmp_path):
        DockerGenerator(output_dir=tmp_path).generate(full_config)
        c = yaml.safe_load((tmp_path / "docker-compose.yml").read_text())
        assert "prometheus" in c["services"]
        assert "my-app" in c["services"]
        assert "traefik" not in c["services"]

    def test_network(self, minimal, tmp_path):
        DockerGenerator(output_dir=tmp_path).generate(minimal)
        c = yaml.safe_load((tmp_path / "docker-compose.yml").read_text())
        assert c["networks"]["homelab"]["driver"] == "bridge"

    def test_no_version_field(self, minimal, tmp_path):
        DockerGenerator(output_dir=tmp_path).generate(minimal)
        c = yaml.safe_load((tmp_path / "docker-compose.yml").read_text())
        assert "version" not in c

    def test_dry_run(self, full_config, tmp_path):
        DockerGenerator(dry_run=True, output_dir=tmp_path).generate(full_config)
        assert not (tmp_path / "docker-compose.yml").exists()

    def test_disabled(self, full_config, tmp_path):
        DockerGenerator(output_dir=tmp_path).generate(full_config)
        c = yaml.safe_load((tmp_path / "docker-compose.yml").read_text())
        assert "traefik" not in c["services"]

    def test_all_templates(self, tmp_path):
        DockerGenerator(output_dir=tmp_path).generate({
            "homelab": {
                "services": {
                    "all": {
                        "enabled": True,
                        "stack": list(SERVICE_TEMPLATES.keys()),
                    }
                }
            }
        })
        c = yaml.safe_load((tmp_path / "docker-compose.yml").read_text())
        for svc in SERVICE_TEMPLATES:
            assert svc in c["services"]

    def test_env_file_generated(self, tmp_path):
        cfg = yaml.safe_load("""
homelab:
  name: x
  network:
    subnet: "10.0.0.0/24"
    gateway: "10.0.0.1"
  services:
    net:
      enabled: true
      stack: [pi-hole]
""")
        DockerGenerator(output_dir=tmp_path).generate(cfg)
        env = tmp_path / ".env"
        assert env.exists()
        content = env.read_text()
        assert "WEBPASSWORD" in content

    def test_services_list_crash(self, tmp_path):
        cfg = {"homelab": {"services": [1, 2, 3]}}
        DockerGenerator(output_dir=tmp_path).generate(cfg)
        c = yaml.safe_load((tmp_path / "docker-compose.yml").read_text())
        assert c["services"] == {}


class TestTerraformGenerator:
    def test_generates(self, full_config, tmp_path):
        TerraformGenerator(output_dir=tmp_path).generate(full_config)
        d = tmp_path / "terraform"
        assert (d / "main.tf").exists()
        assert (d / "variables.tf").exists()
        assert (d / "outputs.tf").exists()

        t = (d / "main.tf").read_text()
        assert "kreuzwerker/docker" in t
        assert "dmacvicar/libvirt" in t
        assert "libvirt_domain" in t

    def test_uses_templatefile_not_deprecated(self, full_config, tmp_path):
        TerraformGenerator(output_dir=tmp_path).generate(full_config)
        t = (tmp_path / "terraform" / "main.tf").read_text()
        assert "templatefile(" in t
        assert "template_file" not in t

    def test_correct_interpolation_syntax(self, full_config, tmp_path):
        TerraformGenerator(output_dir=tmp_path).generate(full_config)
        t = (tmp_path / "terraform" / "main.tf").read_text()
        assert "${local.name}" in t
        assert "${{local.name}}" not in t

    def test_dry(self, full_config, tmp_path):
        TerraformGenerator(dry_run=True, output_dir=tmp_path).generate(full_config)
        assert not (tmp_path / "terraform").exists()


class TestAnsibleGenerator:
    def test_playbooks(self, full_config, tmp_path):
        AnsibleGenerator(output_dir=tmp_path).generate(full_config)
        d = tmp_path / "ansible"
        assert (d / "inventory.ini").exists()
        assert (d / "playbooks" / "site.yml").exists()
        assert (d / "playbooks" / "docker.yml").exists()
        assert (d / "playbooks" / "update.yml").exists()
        assert (d / "playbooks" / "backup.yml").exists()
        assert (d / "playbooks" / "monitoring.yml").exists()

    def test_no_backup(self, minimal, tmp_path):
        AnsibleGenerator(output_dir=tmp_path).generate(minimal)
        assert not (tmp_path / "ansible" / "playbooks" / "backup.yml").exists()

    def test_dry(self, full_config, tmp_path):
        AnsibleGenerator(dry_run=True, output_dir=tmp_path).generate(full_config)
        assert not (tmp_path / "ansible").exists()

    def test_services_not_dict_no_crash(self, tmp_path):
        cfg = {"homelab": {"services": "bad"}}
        AnsibleGenerator(output_dir=tmp_path).generate(cfg)
        assert (tmp_path / "ansible" / "playbooks" / "site.yml").exists()

    def test_backup_uses_volumes_not_networks(self, full_config, tmp_path):
        AnsibleGenerator(output_dir=tmp_path).generate(full_config)
        content = (tmp_path / "ansible" / "playbooks" / "backup.yml").read_text()
        assert "docker volume ls" in content

    def test_site_yml_uses_image_names(self, full_config, tmp_path):
        AnsibleGenerator(output_dir=tmp_path).generate(full_config)
        content = (tmp_path / "ansible" / "playbooks" / "site.yml").read_text()
        assert "prom/prometheus" in content
        assert "grafana/grafana" in content
        assert "jellyfin/jellyfin" in content
        assert "linuxserver/radarr" in content


class TestUtils:
    def test_subnet_ok(self):
        assert validate_subnet("10.0.0.0/8") is True

    def test_subnet_bad(self):
        assert validate_subnet("xxx") is False


class TestTemplates:
    def test_all_have_image(self):
        for n, t in SERVICE_TEMPLATES.items():
            assert "image" in t, f"{n} no image"

    def test_all_restart(self):
        for n, t in SERVICE_TEMPLATES.items():
            assert "restart" in t, f"{n} no restart"

    def test_count(self):
        assert len(SERVICE_TEMPLATES) == 22


class TestPortChecker:
    def test_ports_not_dict_no_crash(self):
        w = PortChecker().check_ports_in_config({
            "homelab": {"services": {"x": None}}
        })
        assert w == []

    def test_services_not_dict_no_crash(self):
        w = PortChecker().check_ports_in_config({
            "homelab": {"services": [1, 2]}
        })
        assert w == []

    def test_find_available_returns_int(self):
        p = PortChecker().find_available()
        assert p is None or 8000 <= p <= 9000
