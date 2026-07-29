import yaml
import pytest

from homelab_toolkit.generators.docker_generator import DockerGenerator, SERVICE_TEMPLATES
from homelab_toolkit.generators.terraform_generator import TerraformGenerator
from homelab_toolkit.generators.ansible_generator import AnsibleGenerator
from homelab_toolkit.validators.config_validator import ConfigValidator
from homelab_toolkit.utils.network import validate_subnet
from homelab_toolkit.utils.templates import render_string


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


class TestUtils:
    def test_subnet_ok(self):
        assert validate_subnet("10.0.0.0/8") is True

    def test_subnet_bad(self):
        assert validate_subnet("xxx") is False

    def test_render(self):
        assert render_string("hi {{ name }}", {"name": "there"}) == "hi there"


class TestTemplates:
    def test_all_have_image(self):
        for n, t in SERVICE_TEMPLATES.items():
            assert "image" in t, f"{n} no image"

    def test_all_restart(self):
        for n, t in SERVICE_TEMPLATES.items():
            assert "restart" in t, f"{n} no restart"

    def test_count(self):
        assert len(SERVICE_TEMPLATES) >= 20
