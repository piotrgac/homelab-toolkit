from pathlib import Path
from rich.console import Console

console = Console()


class AnsibleGenerator:
    def __init__(self, dry_run=False, output_dir=Path("output")):
        self.dry_run = dry_run
        self.output_dir = output_dir

    def generate(self, config):
        homelab = config.get("homelab", {})
        services = homelab.get("services", {})
        backup = config.get("backup", {})

        ansible_dir = self.output_dir / "ansible"
        if not self.dry_run:
            (ansible_dir / "playbooks").mkdir(parents=True, exist_ok=True)
            (ansible_dir / "roles").mkdir(parents=True, exist_ok=True)

        self._write_inventory(ansible_dir, homelab)
        self._write_site_playbook(ansible_dir, services)
        self._write_docker_playbook(ansible_dir)
        self._write_backup_playbook(ansible_dir, backup)
        self._write_monitoring_playbook(ansible_dir, services)
        self._write_update_playbook(ansible_dir)

        console.print(f"[green]v[/green] Ansible playbooks in {ansible_dir}/")

    def _write_file(self, path, content):
        if self.dry_run:
            console.print(f"[dim]--- {path.relative_to(self.output_dir)} ---[/dim]")
            console.print(content)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.lstrip("\n"))
        console.print(f"  [green]v[/green] {path.relative_to(self.output_dir)}")

    def _write_inventory(self, ansible_dir, homelab):
        content = f"""[homelab]
localhost ansible_connection=local

[homelab:vars]
homelab_name={homelab.get("name", "my-homelab")}
ansible_python_interpreter=/usr/bin/python3
"""
        self._write_file(ansible_dir / "inventory.ini", content)

    def _write_site_playbook(self, ansible_dir, services):
        items = []
        for cat, cfg in services.items():
            if not cfg.get("enabled", True):
                continue
            for svc in cfg.get("stack", []):
                items.append(f"        - {svc}")

        if not items:
            items.append("        - none")

        content = f"""---
- name: Provision homelab services
  hosts: homelab
  become: yes
  vars:
    env: production
  tasks:
    - name: Create docker network
      community.docker.docker_network:
        name: homelab-net
        driver: bridge

    - name: Ensure data directories exist
      file:
        path: "/data/homelab/{{{{ item }}}}"
        state: directory
        mode: "0755"
      loop:
{chr(10).join(items)}

    - name: Pull service images
      community.docker.docker_image:
        name: "{{{{ item }}}}"
        source: pull
      loop:
{chr(10).join(items)}
"""
        self._write_file(ansible_dir / "playbooks" / "site.yml", content)

    def _write_docker_playbook(self, ansible_dir):
        content = """---
- name: Docker management
  hosts: homelab
  become: yes
  tasks:
    - name: Ensure docker is installed
      package:
        name: docker
        state: present

    - name: Ensure docker is running
      service:
        name: docker
        state: started
        enabled: yes

    - name: Install docker compose plugin
      community.general.pipx:
        packages: [docker-compose]

    - name: Prune unused resources
      community.docker.docker_prune:
        containers: yes
        images: yes
        networks: yes
        volumes: yes
        builder_cache: yes
"""
        self._write_file(ansible_dir / "playbooks" / "docker.yml", content)

    def _write_backup_playbook(self, ansible_dir, backup):
        if not backup.get("enabled"):
            return

        content = f"""---
- name: Homelab backup
  hosts: homelab
  become: yes
  vars:
    dest: "{backup.get('destination', '/mnt/backup/homelab')}"
    keep: {backup.get('retention_days', 7)}
  tasks:
    - name: Create backup directory
      file:
        path: "{{{{ dest }}}}"
        state: directory
        mode: "0755"

    - name: Backup docker volumes
      shell: |
        docker run --rm \\
          -v homelab-net:/volume \\
          -v {{{{ dest }}}}:/backup \\
          alpine tar czf "/backup/volumes-$(date +%Y%m%d-%H%M%S).tar.gz" -C /volume .
      ignore_errors: yes

    - name: Cleanup old backups
      find:
        paths: "{{{{ dest }}}}"
        age: "{{{{ keep }}}}d"
        patterns: "*.tar.gz"
      register: old

    - name: Remove old backups
      file:
        path: "{{{{ item.path }}}}"
        state: absent
      loop: "{{{{ old.files }}}}"
"""
        self._write_file(ansible_dir / "playbooks" / "backup.yml", content)

    def _write_monitoring_playbook(self, ansible_dir, services):
        mon = services.get("monitoring", {})
        if not mon.get("enabled"):
            return

        content = """---
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

    - name: Deploy grafana datasource
      copy:
        dest: /data/homelab/grafana/datasources/datasource.yml
        content: |
          apiVersion: 1
          datasources:
            - name: Prometheus
              type: prometheus
              url: http://prometheus:9090
              access: proxy
"""
        self._write_file(ansible_dir / "playbooks" / "monitoring.yml", content)

    def _write_update_playbook(self, ansible_dir):
        content = """---
- name: System update
  hosts: homelab
  become: yes
  tasks:
    - name: Update RHEL/Fedora packages
      dnf:
        name: "*"
        state: latest
      when: ansible_facts.os_family == "RedHat"

    - name: Update Debian/Ubuntu packages
      apt:
        name: "*"
        state: latest
      when: ansible_facts.os_family == "Debian"

    - name: Reboot if needed
      reboot:
        reboot_timeout: 300
      when: ansible_facts.os_family == "RedHat"
"""
        self._write_file(ansible_dir / "playbooks" / "update.yml", content)
