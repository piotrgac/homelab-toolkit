import json
import shutil
import subprocess
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax

from homelab_toolkit.generators.docker_generator import DockerGenerator, SERVICE_TEMPLATES
from homelab_toolkit.generators.terraform_generator import TerraformGenerator
from homelab_toolkit.generators.ansible_generator import AnsibleGenerator
from homelab_toolkit.validators.config_validator import ConfigValidator
from homelab_toolkit.validators.port_checker import PortChecker

console = Console()
CONFIG_FILE = "homelab.yaml"


@click.group()
@click.version_option()
def cli():
    pass


@cli.command()
@click.argument("name", default="my-homelab")
def init(name):
    """Create a new homelab project skeleton."""
    cfg = Path(CONFIG_FILE)
    if cfg.exists():
        click.confirm(f"{CONFIG_FILE} already exists. Override?", abort=True)

    config = {
        "homelab": {
            "name": name,
            "description": "Personal homelab",
            "network": {"subnet": "192.168.1.0/24", "gateway": "192.168.1.1"},
            "services": {},
        },
        "backup": {"enabled": True, "retention_days": 7},
    }
    cfg.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))
    console.print(f"[green]v[/green] Created {CONFIG_FILE}")
    console.print("Edit the file then run [bold]homelab validate[/bold] to check it.")


@cli.command()
@click.option("--output", "-o", default="output")
@click.option("--docker/--no-docker", default=True)
@click.option("--terraform/--no-terraform", default=True)
@click.option("--ansible/--no-ansible", default=True)
@click.option("--dry-run", is_flag=True)
def generate(output, docker, terraform, ansible, dry_run):
    """Generate orchestration files from homelab.yaml."""
    cfg = Path(CONFIG_FILE)
    if not cfg.exists():
        console.print("[red]x[/red] No config file. Run [bold]homelab init[/bold] first")
        raise click.Abort()

    config = yaml.safe_load(cfg.read_text())
    errors = ConfigValidator().validate(config)
    if errors:
        for e in errors:
            console.print(f"[red]x[/red] {e}")
        raise click.Abort()

    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)

    done = []
    if docker:
        DockerGenerator(dry_run=dry_run, output_dir=out).generate(config)
        done.append("Docker")
    if terraform:
        TerraformGenerator(dry_run=dry_run, output_dir=out).generate(config)
        done.append("Terraform")
    if ansible:
        AnsibleGenerator(dry_run=dry_run, output_dir=out).generate(config)
        done.append("Ansible")

    console.print()
    console.print(f"[green]v[/green] Generated {', '.join(done)} in [bold]{out}/[/bold]")
    if not dry_run:
        console.print("Run [bold]homelab deploy[/bold] to start services.")


@cli.command()
@click.option("--stack", "-s")
@click.option("--output", "-o", default="output")
def deploy(stack, output):
    """Deploy services via docker compose."""
    compose = Path(output) / "docker-compose.yml"
    if not compose.exists():
        console.print("[red]x[/red] No compose file. Run [bold]homelab generate[/bold] first")
        raise click.Abort()

    try:
        cmd = ["docker", "compose", "-f", str(compose)]
        if stack:
            cmd.extend(["up", "-d", stack])
            console.print(f"[blue]->[/blue] Deploying stack: [bold]{stack}[/bold]")
        else:
            cmd.extend(["up", "-d"])
            console.print("[blue]->[/blue] Deploying all services...")

        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            console.print("[green]v[/green] Done")
            if r.stdout:
                console.print(r.stdout)
        else:
            console.print(f"[red]x[/red] Deploy failed:")
            console.print(r.stderr)
    except FileNotFoundError:
        console.print("[red]x[/red] Docker not found")


@cli.command()
@click.option("--output", "-o", default="output")
def status(output):
    """Show running container status."""
    try:
        r = subprocess.run(
            ["docker", "ps", "--format", "{{json .}}"],
            capture_output=True, text=True, check=True,
        )
        containers = {}
        for line in r.stdout.strip().split("\n"):
            if not line:
                continue
            d = json.loads(line)
            containers[d["Names"]] = {
                "status": d["Status"],
                "ports": d.get("Ports", ""),
                "image": d["Image"],
            }

        if not containers:
            console.print("[yellow]![/yellow] No running containers")
            return

        table = Table(title="Running containers", border_style="blue")
        table.add_column("Name", style="cyan")
        table.add_column("Image", style="magenta")
        table.add_column("Status", style="green")
        table.add_column("Ports")
        for name, info in containers.items():
            table.add_row(name, info["image"], info["status"], info["ports"])

        console.print(table)
    except FileNotFoundError:
        console.print("[red]x[/red] Docker not installed")
    except subprocess.CalledProcessError:
        console.print("[red]x[/red] Failed to get status")


@cli.command()
@click.option("--stack", "-s")
@click.option("--output", "-o", default="output")
def logs(stack, output):
    """Tail logs for services."""
    compose = Path(output) / "docker-compose.yml"
    if not compose.exists():
        console.print("[red]x[/red] No compose. [bold]homelab generate[/bold] first")
        raise click.Abort()

    try:
        cmd = ["docker", "compose", "-f", str(compose), "logs", "--tail=50"]
        if stack:
            cmd.append(stack)
            console.print(f"[blue]->[/blue] Logs: [bold]{stack}[/bold]")
        else:
            console.print("[blue]->[/blue] All services:")

        r = subprocess.run(cmd, capture_output=True, text=True)
        console.print(r.stdout or "[dim]empty[/dim]")
    except FileNotFoundError:
        console.print("[red]x[/red] Docker not found")


@cli.command()
def validate():
    """Validate homelab.yaml config."""
    cfg = Path(CONFIG_FILE)
    if not cfg.exists():
        console.print("[red]x[/red] No homelab.yaml")
        return

    config = yaml.safe_load(cfg.read_text())
    errors = ConfigValidator().validate(config)
    port_warnings = PortChecker().check_ports_in_config(config)

    if not errors and not port_warnings:
        console.print("[green]v[/green] Config is valid")
        return

    if errors:
        console.print("[bold red]Errors:[/bold red]")
        for e in errors:
            console.print(f"  [red]x[/red] {e}")

    if port_warnings:
        console.print("\n[bold yellow]Port conflicts:[/bold yellow]")
        for w in port_warnings:
            console.print(f"  [yellow]![/yellow] {w}")


@cli.command()
@click.argument("action", type=click.Choice(["create", "restore", "list"]))
@click.option("--output", "-o", default="output/backups")
@click.option("--file", "-f", "backup_file")
def backup(action, output, backup_file):
    """Manage config backups."""
    bdir = Path(output)

    if action == "create":
        bdir.mkdir(parents=True, exist_ok=True)
        ts = subprocess.run(["date", "+%Y%m%d-%H%M%S"], capture_output=True, text=True).stdout.strip()
        archive = f"homelab-backup-{ts}.tar.gz"

        files = ["homelab.yaml"]
        out_dir = Path("output")
        if out_dir.exists():
            files.append("output")

        if all(Path(f).exists() for f in files if f != "output"):
            subprocess.run(["tar", "czf", str(bdir / archive)] + files, check=True)
            console.print(f"[green]v[/green] Backup saved: [bold]{bdir / archive}[/bold]")
        else:
            console.print("[yellow]![/yellow] Nothing to backup")

    elif action == "restore":
        if not backup_file:
            console.print("[red]x[/red] Specify --file backup.tar.gz")
            return

        bp = Path(backup_file)
        if not bp.exists():
            console.print(f"[red]x[/red] File not found: {bp}")
            return

        subprocess.run(["tar", "xzf", str(bp)], check=True)
        console.print(f"[green]v[/green] Restored from: [bold]{bp}[/bold]")

    elif action == "list":
        if not bdir.exists():
            console.print("[yellow]![/yellow] No backups found")
            return

        backups = sorted(bdir.glob("*.tar.gz"), reverse=True)
        if not backups:
            console.print("[yellow]![/yellow] No backups")
            return

        table = Table(title="Backups")
        table.add_column("File")
        table.add_column("Size")
        table.add_column("Date")
        for b in backups:
            size = b.stat().st_size
            sz = f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / (1024*1024):.1f} MB"
            date = subprocess.run(["date", "-r", str(b), "+%Y-%m-%d %H:%M"], capture_output=True, text=True).stdout.strip()
            table.add_row(b.name, sz, date)
        console.print(table)


@cli.command("template")
@click.argument("action", type=click.Choice(["list", "show"]))
@click.argument("name", required=False)
def template_cmd(action, name):
    """List or show service templates."""
    if action == "list":
        table = Table(title="Available templates")
        table.add_column("Name", style="cyan")
        table.add_column("Image", style="magenta")
        table.add_column("Ports", style="green")
        table.add_column("Category")

        cats = {
            "monitoring": ["prometheus", "grafana", "alertmanager", "node-exporter"],
            "networking": ["traefik", "pi-hole", "nginx-proxy-manager"],
            "media": ["jellyfin", "radarr", "sonarr", "prowlarr", "qbittorrent"],
            "storage": ["nextcloud", "samba"],
            "security": ["authelia", "vault"],
            "database": ["postgres", "mysql", "redis"],
            "development": ["portainer", "code-server", "gitlab"],
        }

        for cat, services in cats.items():
            for svc in services:
                t = SERVICE_TEMPLATES.get(svc)
                if t:
                    ports = ", ".join(t.get("ports", []))
                    table.add_row(svc, t["image"], ports, cat)

        console.print(table)
        console.print("\n[dim][bold]homelab template show <name>[/bold] for details[/dim]")

    elif action == "show":
        if not name:
            console.print("[red]x[/red] Specify a template name")
            return

        t = SERVICE_TEMPLATES.get(name)
        if not t:
            console.print(f"[red]x[/red] Unknown template: {name}")
            console.print("[bold]homelab template list[/bold] to see all templates")
            return

        console.print(f"[bold cyan]{name}[/bold cyan]")
        console.print(Syntax(yaml.dump({name: t}, default_flow_style=False, sort_keys=False), "yaml", theme="monokai"))

        console.print("\n[bold]Usage in homelab.yaml:[/bold]")
        ex = yaml.dump(
            {"services": {"my-stack": {"enabled": True, "stack": [name]}}},
            default_flow_style=False,
        )
        console.print(Syntax(ex, "yaml", theme="monokai"))


@cli.command()
@click.option("--output", "-o", default="output")
def clean(output):
    """Remove generated output directory."""
    p = Path(output)
    if p.exists():
        shutil.rmtree(p)
        console.print(f"[green]v[/green] Removed {p}/")
    else:
        console.print("[yellow]![/yellow] Nothing to clean")


if __name__ == "__main__":
    cli()
