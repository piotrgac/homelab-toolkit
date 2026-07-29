from pathlib import Path
import yaml


class ConfigParser:
    def __init__(self, path):
        self.path = Path(path)

    def parse(self):
        if not self.path.exists():
            raise FileNotFoundError(f"Config file not found: {self.path}")
        return yaml.safe_load(self.path.read_text())

    def get_services(self, config):
        return config.get("homelab", {}).get("services", {})

    def get_network(self, config):
        return config.get("homelab", {}).get("network", {})

    def get_backup(self, config):
        return config.get("backup", {})
