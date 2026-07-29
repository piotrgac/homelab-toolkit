NETWORKING_STACK = {
    "traefik": {
        "image": "traefik:v3.0",
        "ports": ["80:80", "443:443"],
        "volumes": ["/var/run/docker.sock:/var/run/docker.sock"],
        "command": ["--providers.docker", "--entrypoints.web.address=:80"],
    },
    "pi-hole": {
        "image": "pihole/pihole:latest",
        "ports": ["53:53/tcp", "53:53/udp", "8053:80/tcp"],
        "cap_add": ["NET_ADMIN"],
        "environment": {"TZ": "Europe/Warsaw"},
    },
}
