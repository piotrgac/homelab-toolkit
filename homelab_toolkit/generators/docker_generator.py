import re
import yaml
from pathlib import Path
from rich.console import Console

console = Console()

SERVICE_TEMPLATES = {
    "prometheus": {
        "image": "prom/prometheus:v2.53.0", "ports": ["9090:9090"],
        "volumes": ["./data/prometheus:/etc/prometheus"], "restart": "unless-stopped",
    },
    "grafana": {
        "image": "grafana/grafana:11.1.0", "ports": ["3000:3000"],
        "volumes": ["./data/grafana:/var/lib/grafana"], "restart": "unless-stopped",
    },
    "alertmanager": {
        "image": "prom/alertmanager:v0.27.0", "ports": ["9093:9093"],
        "volumes": ["./data/alertmanager:/etc/alertmanager"], "restart": "unless-stopped",
    },
    "node-exporter": {
        "image": "prom/node-exporter:v1.8.1", "ports": ["9100:9100"],
        "restart": "unless-stopped",
    },
    "traefik": {
        "image": "traefik:v3.0", "ports": ["80:80", "443:443"],
        "volumes": ["/var/run/docker.sock:/var/run/docker.sock", "./data/traefik:/etc/traefik"],
        "restart": "unless-stopped",
    },
    "pi-hole": {
        "image": "pihole/pihole:2024.07.0", "ports": ["53:53/tcp", "53:53/udp", "8053:80/tcp"],
        "cap_add": ["NET_ADMIN"],
        "environment": {"TZ": "UTC", "WEBPASSWORD": "${PIHOLE_PASSWORD:-admin}"},
        "restart": "unless-stopped",
    },
    "nginx-proxy-manager": {
        "image": "jc21/nginx-proxy-manager:2.11.3",
        "ports": ["80:80", "443:443", "8181:81"],
        "volumes": ["./data/nginx-proxy:/data"], "restart": "unless-stopped",
    },
    "jellyfin": {
        "image": "jellyfin/jellyfin:10.9.6", "ports": ["8096:8096"],
        "volumes": ["./data/jellyfin:/config", "./data/media:/media"],
        "restart": "unless-stopped",
    },
    "radarr": {
        "image": "linuxserver/radarr:5.7.0", "ports": ["7878:7878"],
        "volumes": ["./data/radarr:/config", "./data/media:/media"],
        "restart": "unless-stopped",
    },
    "sonarr": {
        "image": "linuxserver/sonarr:4.0.4", "ports": ["8989:8989"],
        "volumes": ["./data/sonarr:/config", "./data/media:/media"],
        "restart": "unless-stopped",
    },
    "prowlarr": {
        "image": "linuxserver/prowlarr:1.21.0", "ports": ["9696:9696"],
        "restart": "unless-stopped",
    },
    "qbittorrent": {
        "image": "linuxserver/qbittorrent:4.6.5",
        "ports": ["8080:8080", "6881:6881"],
        "volumes": ["./data/qbittorrent:/config", "./data/downloads:/downloads"],
        "restart": "unless-stopped",
    },
    "nextcloud": {
        "image": "nextcloud:29.0.2", "ports": ["8081:80"],
        "volumes": ["./data/nextcloud:/var/www/html"],
        "restart": "unless-stopped",
    },
    "samba": {
        "image": "dperson/samba:2024-07-08", "ports": ["139:139", "445:445"],
        "volumes": ["./data/samba:/mount"], "restart": "unless-stopped",
    },
    "authelia": {
        "image": "authelia/authelia:4.38.7", "ports": ["9091:9091"],
        "volumes": ["./data/authelia:/config"], "restart": "unless-stopped",
    },
    "vault": {
        "image": "hashicorp/vault:1.17.2", "ports": ["8200:8200"],
        "volumes": ["./data/vault:/vault/file"],
        "cap_add": ["IPC_LOCK"], "restart": "unless-stopped",
    },
    "postgres": {
        "image": "postgres:16-alpine", "ports": ["5432:5432"],
        "volumes": ["./data/postgres:/var/lib/postgresql/data"],
        "environment": {"POSTGRES_PASSWORD": "${POSTGRES_PASSWORD:-changeme}", "POSTGRES_DB": "homelab"},
        "restart": "unless-stopped",
    },
    "mysql": {
        "image": "mysql:8.0", "ports": ["3306:3306"],
        "volumes": ["./data/mysql:/var/lib/mysql"],
        "environment": {"MYSQL_ROOT_PASSWORD": "${MYSQL_PASSWORD:-changeme}"},
        "restart": "unless-stopped",
    },
    "redis": {
        "image": "redis:7-alpine", "ports": ["6379:6379"],
        "restart": "unless-stopped",
    },
    "portainer": {
        "image": "portainer/portainer-ce:2.20.3",
        "ports": ["9000:9000", "8000:8000"],
        "volumes": ["/var/run/docker.sock:/var/run/docker.sock", "./data/portainer:/data"],
        "restart": "unless-stopped",
    },
    "code-server": {
        "image": "codercom/code-server:4.91.1", "ports": ["8443:8443"],
        "volumes": ["./data/code-server:/home/coder/project"],
        "environment": {"PASSWORD": "${CODESERVER_PASSWORD:-changeme}"},
        "restart": "unless-stopped",
    },
    "gitlab": {
        "image": "gitlab/gitlab-ce:17.2.2-ce.0",
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
    def __init__(self, dry_run: bool = False, output_dir: Path = Path("output")) -> None:
        self.dry_run = dry_run
        self.output_dir = output_dir

    def generate(self, config: dict) -> None:
        services = config.get("homelab", {}).get("services", {})
        if not isinstance(services, dict):
            services = {}
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

        subnet = config.get("homelab", {}).get("network", {}).get("subnet", "172.20.0.0/16")
        compose = {
            "services": docker_services,
            "networks": {
                "homelab": {
                    "driver": "bridge",
                    "ipam": {"config": [{"subnet": subnet}]},
                }
            },
        }

        out = self.output_dir / "docker-compose.yml"
        env_file = self.output_dir / ".env"
        if self.dry_run:
            console.print(yaml.dump(compose, default_flow_style=False, sort_keys=False))
            return

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(yaml.dump(compose, default_flow_style=False, sort_keys=False))

        env_vars = {}
        for svc in docker_services.values():
            for k, v in svc.get("environment", {}).items():
                if isinstance(v, str) and v.startswith("${"):
                    m = re.match(r'^\$\{([^:]+):-([^}]*)\}$', v)
                    if m:
                        env_vars[k] = m.group(2)
        if env_vars:
            lines = [f"# Generated by homelab-toolkit - override these" ]
            for k, v in sorted(env_vars.items()):
                lines.append(f"{k}={v}")
            env_file.write_text("\n".join(lines) + "\n")

        console.print(f"  [green]v[/green] {out.relative_to(self.output_dir)}")
        if env_vars:
            console.print(f"  [green]v[/green] {env_file.relative_to(self.output_dir)}")
