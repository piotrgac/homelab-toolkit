import yaml
from pathlib import Path
from rich.console import Console

console = Console()

SERVICE_TEMPLATES = {
    "prometheus": {
        "image": "prom/prometheus:latest", "ports": ["9090:9090"],
        "volumes": ["./data/prometheus:/etc/prometheus"], "restart": "unless-stopped",
    },
    "grafana": {
        "image": "grafana/grafana:latest", "ports": ["3000:3000"],
        "volumes": ["./data/grafana:/var/lib/grafana"], "restart": "unless-stopped",
    },
    "alertmanager": {
        "image": "prom/alertmanager:latest", "ports": ["9093:9093"],
        "restart": "unless-stopped",
    },
    "node-exporter": {
        "image": "prom/node-exporter:latest", "ports": ["9100:9100"],
        "restart": "unless-stopped",
    },
    "traefik": {
        "image": "traefik:v3.0", "ports": ["80:80", "443:443"],
        "volumes": ["/var/run/docker.sock:/var/run/docker.sock", "./data/traefik:/etc/traefik"],
        "restart": "unless-stopped",
    },
    "pi-hole": {
        "image": "pihole/pihole:latest", "ports": ["53:53/tcp", "53:53/udp", "8053:80/tcp"],
        "cap_add": ["NET_ADMIN"],
        "environment": {"TZ": "Europe/Warsaw", "WEBPASSWORD": "admin"},
        "restart": "unless-stopped",
    },
    "nginx-proxy-manager": {
        "image": "jc21/nginx-proxy-manager:latest",
        "ports": ["80:80", "443:443", "8181:81"],
        "volumes": ["./data/nginx-proxy:/data"], "restart": "unless-stopped",
    },
    "jellyfin": {
        "image": "jellyfin/jellyfin:latest", "ports": ["8096:8096"],
        "volumes": ["./data/jellyfin:/config", "./data/media:/media"],
        "restart": "unless-stopped",
    },
    "radarr": {
        "image": "linuxserver/radarr:latest", "ports": ["7878:7878"],
        "volumes": ["./data/radarr:/config", "./data/media:/media"],
        "restart": "unless-stopped",
    },
    "sonarr": {
        "image": "linuxserver/sonarr:latest", "ports": ["8989:8989"],
        "volumes": ["./data/sonarr:/config", "./data/media:/media"],
        "restart": "unless-stopped",
    },
    "prowlarr": {
        "image": "linuxserver/prowlarr:latest", "ports": ["9696:9696"],
        "restart": "unless-stopped",
    },
    "qbittorrent": {
        "image": "linuxserver/qbittorrent:latest",
        "ports": ["8080:8080", "6881:6881"],
        "volumes": ["./data/qbittorrent:/config", "./data/downloads:/downloads"],
        "restart": "unless-stopped",
    },
    "nextcloud": {
        "image": "nextcloud:latest", "ports": ["8081:80"],
        "volumes": ["./data/nextcloud:/var/www/html"],
        "restart": "unless-stopped",
    },
    "samba": {
        "image": "dperson/samba:latest", "ports": ["139:139", "445:445"],
        "volumes": ["./data/samba:/mount"], "restart": "unless-stopped",
    },
    "authelia": {
        "image": "authelia/authelia:latest", "ports": ["9091:9091"],
        "volumes": ["./data/authelia:/config"], "restart": "unless-stopped",
    },
    "vault": {
        "image": "hashicorp/vault:latest", "ports": ["8200:8200"],
        "cap_add": ["IPC_LOCK"], "restart": "unless-stopped",
    },
    "postgres": {
        "image": "postgres:16-alpine", "ports": ["5432:5432"],
        "volumes": ["./data/postgres:/var/lib/postgresql/data"],
        "environment": {"POSTGRES_PASSWORD": "changeme", "POSTGRES_DB": "homelab"},
        "restart": "unless-stopped",
    },
    "mysql": {
        "image": "mysql:8.0", "ports": ["3306:3306"],
        "volumes": ["./data/mysql:/var/lib/mysql"],
        "environment": {"MYSQL_ROOT_PASSWORD": "changeme"},
        "restart": "unless-stopped",
    },
    "redis": {
        "image": "redis:7-alpine", "ports": ["6379:6379"],
        "restart": "unless-stopped",
    },
    "portainer": {
        "image": "portainer/portainer-ce:latest",
        "ports": ["9000:9000", "8000:8000"],
        "volumes": ["/var/run/docker.sock:/var/run/docker.sock", "./data/portainer:/data"],
        "restart": "unless-stopped",
    },
    "code-server": {
        "image": "codercom/code-server:latest", "ports": ["8443:8443"],
        "volumes": ["./data/code-server:/home/coder/project"],
        "environment": {"PASSWORD": "changeme"},
        "restart": "unless-stopped",
    },
    "gitlab": {
        "image": "gitlab/gitlab-ce:latest",
        "ports": ["8929:80", "2224:22"],
        "volumes": [
            "./data/gitlab/config:/etc/gitlab",
            "./data/gitlab/logs:/var/log/gitlab",
            "./data/gitlab/data:/var/opt/gitlab",
        ],
        "restart": "unless-stopped",
    },
}


class DockerGenerator:
    def __init__(self, dry_run=False, output_dir=Path("output")):
        self.dry_run = dry_run
        self.output_dir = output_dir

    def generate(self, config):
        services = config.get("homelab", {}).get("services", {})
        custom_templates = config.get("custom_templates", {})
        docker_services = {}

        for category, category_config in services.items():
            if not category_config.get("enabled", True):
                continue

            stack = category_config.get("stack", [])
            ports_override = category_config.get("ports", {})
            env_override = category_config.get("environment", {})

            for service_name in stack:
                template = SERVICE_TEMPLATES.get(service_name) or custom_templates.get(service_name)
                if not template:
                    console.print(f"[yellow]![/yellow] Unknown service: {service_name}")
                    continue

                s = template.copy()

                if isinstance(ports_override.get(service_name), int):
                    port = ports_override[service_name]
                    s["ports"] = [f"{port}:{port}"]

                if isinstance(ports_override.get(service_name), list):
                    s["ports"] = ports_override[service_name]

                if env_override.get(service_name):
                    if isinstance(s.get("environment"), dict):
                        s["environment"].update(env_override[service_name])
                    else:
                        s["environment"] = env_override[service_name]

                s["networks"] = ["homelab"]
                docker_services[service_name] = s

        compose = {
            "version": "3.8",
            "services": docker_services,
            "networks": {
                "homelab": {
                    "driver": "bridge",
                    "ipam": {"config": [{"subnet": "172.20.0.0/16"}]},
                }
            },
        }

        out = self.output_dir / "docker-compose.yml"
        if self.dry_run:
            console.print(yaml.dump(compose, default_flow_style=False, sort_keys=False))
            return

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(yaml.dump(compose, default_flow_style=False, sort_keys=False))
        console.print(f"  [green]v[/green] {out.relative_to(self.output_dir)}")
