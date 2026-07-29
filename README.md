# homelab-toolkit

Generate docker-compose, terraform and ansible from a single YAML config file.

```
pip install .
homelab init
vim homelab.yaml
homelab generate -o deploy/
homelab deploy
```

## Table of contents

- [Motivation](#motivation)
- [Installation](#installation)
- [Quick start](#quick-start)
- [CLI reference](#cli-reference)
- [Config reference](#config-reference)
- [Architecture](#architecture)
- [Templates](#templates)
- [Custom templates](#custom-templates)
- [Generators](#generators)
- [Development](#development)
- [Tests](#tests)
- [Project structure](#project-structure)
- [Requirements](#requirements)
- [License](#license)

## Motivation

Running a homelab means maintaining compose files, terraform modules and ansible playbooks in parallel. Add a service to docker-compose and you need to update the backup playbook, add monitoring targets, adjust the VM provisioning. This tool keeps all three in sync from one config.

The config file is the single source of truth. Three generators consume it and produce ready-to-use orchestration files.

## Installation

```bash
git clone https://github.com/TWOJ_USER/homelab-toolkit.git
cd homelab-toolkit
pip install .
```

Verify it works:

```bash
homelab --version
homelab --help
```

For development (editable install):

```bash
pip install -e .
```

## Quick start

```bash
# 1. Create a config file
homelab init

# 2. Edit the config
vim homelab.yaml

# 3. Validate before generating
homelab validate

# 4. Generate orchestration files
homelab generate -o deploy/

# 5. Deploy services
homelab deploy

# 6. Check what's running
homelab status
```

## CLI reference

| Command | Description |
|---------|-------------|
| `homelab -c my-config.yaml init` | Create a skeleton with a custom config path |
| `homelab init [name]` | Create a skeleton `homelab.yaml`. Default name: my-homelab |
| `homelab generate` | Run all generators. Output goes to `output/` by default |
| `homelab generate --dry-run` | Print generated files to stdout, don't write anything |
| `homelab generate --no-terraform` | Skip terraform generation |
| `homelab generate --no-ansible` | Skip ansible generation |
| `homelab generate -o custom_dir/` | Write output to a custom directory |
| `homelab deploy` | Run `docker compose up -d` in the output directory |
| `homelab deploy --stack monitoring` | Deploy only services in the monitoring stack |
| `homelab status` | Show running containers with ports |
| `homelab logs --stack jellyfin` | Tail last 50 log lines |
| `homelab validate` | Check config structure and port availability |
| `homelab template list` | List all 22 built-in templates with ports |
| `homelab template show postgres` | Show template yaml and usage example |
| `homelab backup create` | Archive config and generated files to `output/backups/` |
| `homelab backup list` | List available backups with size and date |
| `homelab backup restore -f backup.tar.gz` | Restore config and generated files |
| `homelab down` | Stop and remove containers |
| `homelab pull` | Pull latest service images |
| `homelab clean` | Remove the output directory |

## Config reference

### Top-level structure

```yaml
homelab:
  name: string                  # project name, used in docker network names
  description: string           # optional, free text
  network:
    subnet: "192.168.1.0/24"    # docker network subnet
    gateway: "192.168.1.1"      # docker network gateway
    dns:                        # optional, list of DNS servers
      - "1.1.1.1"
      - "8.8.8.8"

services:
  <category>:                   # arbitrary category name, for grouping
    enabled: true               # set false to disable all services in this category
    stack:                      # list of service names (must match template names)
      - prometheus
      - grafana
    ports:                      # optional port overrides
      grafana: 3000             # override single port
      traefik: [80, 443]        # override with a list

backup:                         # optional, controls ansible backup playbook
  enabled: true
  schedule: "0 2 * * *"
  retention_days: 7
  destination: "/mnt/backup/homelab"

custom_templates:               # optional, define services outside the built-in list
  my-api:
    image: "my-api:latest"
    ports: ["4000:4000"]
    environment:
      DB_HOST: postgres
```

### Service field precedence

Ports and environment variables can be overridden at the service level. The override mechanism works per service name:

```yaml
services:
  networking:
    stack: [traefik]
    ports:
      traefik: [80, 8080]       # overrides the default 80:80, 443:443
  monitoring:
    stack: [grafana]
    ports:
      grafana: 3500             # overrides the default 3000:3000
    environment:                 # merges into the template's environment dict
      grafana:
        GF_SERVER_HTTP_PORT: 3500
```

## Architecture

```
homelab.yaml
      │
      ▼
 cli.py (click)
      │
      ├──► ConfigValidator     ──► errors or proceed
      │
      ├──► DockerGenerator     ──► docker-compose.yml
      │       │
      │       ├── SERVICE_TEMPLATES (22 built-in)
      │       └── custom_templates from config
      │
      ├──► TerraformGenerator  ──► terraform/main.tf
      │       │                    terraform/variables.tf
      │       └── libvirt provider, docker provider    terraform/outputs.tf
      │
      └──► AnsibleGenerator    ──► ansible/inventory.ini
              │                    ansible/playbooks/site.yml
              ├── provision                            docker.yml
              ├── docker setup                         backup.yml
              ├── backup                               monitoring.yml
              ├── monitoring setup                     update.yml
              └── system update
```

Each generator reads the same config object independently. They share no state and can be run separately via `--no-docker`, `--no-terraform`, `--no-ansible` flags.

### Example output: docker-compose.yml

For a config with prometheus and grafana enabled, the generator produces:

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./data/prometheus:/etc/prometheus
    restart: unless-stopped
    networks:
      - homelab
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - ./data/grafana:/var/lib/grafana
    restart: unless-stopped
    networks:
      - homelab
networks:
  homelab:
    driver: bridge
    ipam:
      config:
        - subnet: 10.0.0.0/24
```

### Example output: ansible playbook

The monitoring playbook configures prometheus and grafana on the target host:

```yaml
---
- name: Monitoring setup
  hosts: homelab
  become: yes
  tasks:
    - name: Create prometheus config directory
      file:
        path: /data/homelab/prometheus
        state: directory

    - name: Deploy prometheus config
      copy:
        dest: /data/homelab/prometheus/prometheus.yml
        content: |
          global:
            scrape_interval: 15s
          scrape_configs:
            - job_name: 'prometheus'
              static_configs:
                - targets: ['localhost:9090']
            - job_name: 'node'
              static_configs:
                - targets: ['localhost:9100']
```

## Templates

22 built-in templates across 7 categories:

| Category | Services | Ports |
|----------|----------|-------|
| Monitoring | prometheus, grafana, alertmanager, node-exporter | 9090, 3000, 9093, 9100 |
| Networking | traefik, pi-hole, nginx-proxy-manager | 80/443, 53/8053, 8181 |
| Media | jellyfin, radarr, sonarr, prowlarr, qbittorrent | 8096, 7878, 8989, 9696, 8080 |
| Storage | nextcloud, samba | 8081, 139/445 |
| Security | authelia, vault | 9091, 8200 |
| Database | postgres, mysql, redis | 5432, 3306, 6379 |
| Development | portainer, code-server, gitlab | 9000, 8443, 8929 |

```bash
homelab template list          # full table with ports
homelab template show gitlab   # detailed template yaml
```

## Custom templates

Define services outside the built-in list. The schema is the same as the internal templates:

```yaml
custom_templates:
  my-api:
    image: "my-api:latest"
    ports: ["4000:4000"]
    environment:
      DB_HOST: postgres

  my-frontend:
    image: "my-frontend:latest"
    ports: ["3000:3000"]
    environment:
      API_URL: http://my-api:4000

services:
  apps:
    enabled: true
    stack:
      - my-api
      - my-frontend
```

Custom templates support the same fields as built-in ones: `image`, `ports`, `volumes`, `environment`, `cap_add`, `restart`. Ports and environment variables can be overridden at the category level.

## Generators

### Docker generator

Reads the services section, resolves each service name against `SERVICE_TEMPLATES` (or `custom_templates`), applies port overrides and environment merges, then writes a docker-compose.yml with a shared bridge network. Each service gets `networks: ["homelab"]` automatically.

### Terraform generator

Generates a terraform module with:
- Docker provider (kreuzwerker/docker) for docker network and volume
- Libvirt provider (dmacvicar/libvirt) for KVM provisioning
- cloud-init disk with Rocky Linux 9, docker install, admin user with SSH key
- Variables for subnet, gateway, memory, vcpu
- Outputs for network ID, VM IP and VM name

### Ansible generator

Generates 5 playbooks. Each playbook is a standalone file in `ansible/playbooks/`:

| Playbook | Purpose | Runs when |
|----------|---------|-----------|
| `site.yml` | Create docker network, data dirs, pull images | Always |
| `docker.yml` | Install and configure docker | Always |
| `monitoring.yml` | Deploy prometheus and grafana configs | monitoring.enabled |
| `backup.yml` | Schedule docker volume backups | backup.enabled |
| `update.yml` | System package update, reboot if needed | Always |

## Development

### Setup

```bash
git clone https://github.com/piotrgac/homelab-toolkit.git
cd homelab-toolkit
pip install -e .
```

### Code style

The codebase follows standard Python conventions. No external linter is required. Tests live in `tests/` and use pytest fixtures with sample configs.

### Adding a new template

Open `homelab_toolkit/generators/docker_generator.py` and add an entry to `SERVICE_TEMPLATES`:

```python
"my-service": {
    "image": "org/my-service:latest",
    "ports": ["8080:8080"],
    "volumes": ["./data/my-service:/data"],
    "restart": "unless-stopped",
},
```

That's it. The service becomes available in `homelab template list` and can be used in any config.

### Running tests

```bash
pytest tests/ -v
```

Tests cover:
- Config validation (valid configs, missing fields, unknown services, custom templates)
- Docker generator (output structure, dry-run, disabled services, all templates)
- Terraform generator (file creation, dry-run, content checks)
- Ansible generator (playbook count, conditional skips, dry-run)
- Utilities (subnet validation)
- Template integrity (all have image and restart policy)

## Tests

```bash
pip install pytest
pytest tests/ -v
```

32 tests, all passing. Test files use `tmp_path` fixtures to avoid writing to the source tree.

## Project structure

```
├── homelab_toolkit/
│   ├── __init__.py             # version
│   ├── cli.py                  # CLI entry point, 9 commands
│   ├── generators/
│   │   ├── docker_generator.py # docker-compose + 22 templates
│   │   ├── terraform_generator.py
│   │   └── ansible_generator.py
│   ├── validators/
│   │   ├── config_validator.py # structural validation
│   │   └── port_checker.py     # local port availability
│   └── utils/
│       └── network.py          # subnet helpers
├── tests/
│   └── test_generators.py      # 32 test cases
├── examples/
│   └── homelab.yaml            # annotated example config
├── .env.example                # env var reference
└── pyproject.toml
```

## Requirements

- **Python 3.11+** - tested on 3.14
- **Docker** - required for `deploy` and `status` commands
- **Terraform** - optional, only if you use the terraform generator
- **Ansible** - optional, only if you use the ansible generator

## License

MIT
