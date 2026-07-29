import json
import shutil
import subprocess
import tarfile
from datetime import datetime
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


def _read_config(path=None):
    path = path or CONFIG_FILE
    cfg = Path(path)
    if not cfg.exists():
        console.print(f"[red]x[/red] Config not found: {path}")
        raise click.Abort()
    try:
        return yaml.safe_load(cfg.read_text())
    except yaml.YAMLError as e:
        console.print(f"[red]x[/red] Invalid YAML in {path}: {e}")
        raise click.Abort()


def _resolve_stack(stack_name, config_path=None):
    config = _read_config(config_path)
    services = config.get("homelab", {}).get("services", {})
    if not isinstance(services, dict):
        return [stack_name]
    for cat, cfg in services.items():
        if cat != stack_name:
            continue
        if isinstance(cfg, dict) and cfg.get("stack"):
            return cfg["stack"]
    return [stack_name]


@click.group()
@click.version_option()
@click.option("--config", "-c", default="homelab.yaml", envvar="HOMELAB_CONFIG", show_default=True)
@click.pass_context
def cli(ctx, config):
    ctx.ensure_object(dict)
    ctx.obj["config"] = config


@cli.command()
@click.argument("name", default="my-homelab")
@click.pass_context
def init(ctx, name):
    """Create a new homelab project skeleton."""
    config_path = ctx.obj["config"]
    cfg = Path(config_path)
    if cfg.exists():
        click.confirm(f"{config_path} already exists. Override?", abort=True)

    raw = f"""homelab:
  name: {name}
  description: Personal homelab
  network:
    subnet: 192.168.1.0/24
    gateway: 192.168.1.1
  services:
    # monitoring:
    #   enabled: true
    #   stack:
    #     - prometheus
    #     - grafana

backup:
  enabled: true
  retention_days: 7
"""
    cfg.write_text(raw)
    console.print(f"[green]v[/green] Created {CONFIG_FILE}")
    console.print("Edit the file then run [bold]homelab validate[/bold] to check it.")


@cli.command()
@click.option("--output", "-o", default="output")
@click.option("--docker/--no-docker", default=True)
@click.option("--terraform/--no-terraform", default=True)
@click.option("--ansible/--no-ansible", default=True)
@click.option("--dry-run", is_flag=True)
@click.pass_context
def generate(ctx, output, docker, terraform, ansible, dry_run):
    """Generate orchestration files from homelab.yaml."""
    config = _read_config(ctx.obj["config"])
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
@click.pass_context
def deploy(ctx, stack, output):
    """Deploy services via docker compose."""
    compose = Path(output) / "docker-compose.yml"
    if not compose.exists():
        console.print("[red]x[/red] No compose file. Run [bold]homelab generate[/bold] first")
        raise click.Abort()

    try:
        cmd = ["docker", "compose", "-f", str(compose)]
        if stack:
            services = _resolve_stack(stack, ctx.obj["config"])
            cmd.extend(["up", "-d"] + services)
            console.print(f"[blue]->[/blue] Deploying services: [bold]{', '.join(services)}[/bold]")
        else:
            cmd.extend(["up", "-d"])
            console.print("[blue]->[/blue] Deploying all services...")

        r = subprocess.run(cmd)
        if r.returncode == 0:
            console.print("[green]v[/green] Done")
        else:
            console.print(f"[red]x[/red] Deploy failed (exit {r.returncode})")
            raise click.Abort()
    except FileNotFoundError:
        console.print("[red]x[/red] Docker not found")
        raise click.Abort()


@cli.command()
@click.option("--output", "-o", default="output")
@click.pass_context
def status(ctx, output):
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
        console.print("[red]x[/red] Docker not found")
        raise click.Abort()
    except subprocess.CalledProcessError as e:
        console.print(f"[red]x[/red] Docker error: {e.stderr or e}")
        raise click.Abort()


@cli.command()
@click.option("--stack", "-s")
@click.option("--follow", "-f", is_flag=True, help="Follow log output")
@click.option("--tail", default=50, help="Number of lines to show")
@click.option("--output", "-o", default="output")
@click.pass_context
def logs(ctx, stack, follow, tail, output):
    """Tail logs for services."""
    compose = Path(output) / "docker-compose.yml"
    if not compose.exists():
        console.print("[red]x[/red] No compose. [bold]homelab generate[/bold] first")
        raise click.Abort()

    try:
        cmd = ["docker", "compose", "-f", str(compose), "logs", f"--tail={tail}"]
        if follow:
            cmd.append("-f")
        if stack:
            services = _resolve_stack(stack, ctx.obj["config"])
            cmd.extend(services)

        r = subprocess.run(cmd)
        if r.returncode != 0:
            raise click.Abort()
    except FileNotFoundError:
        console.print("[red]x[/red] Docker not found")
        raise click.Abort()


@cli.command()
@click.option("--output", "-o", default="output")
def down(output):
    """Stop and remove containers."""
    compose = Path(output) / "docker-compose.yml"
    if not compose.exists():
        console.print("[red]x[/red] No compose file")
        return
    try:
        subprocess.run(["docker", "compose", "-f", str(compose), "down"], check=True)
        console.print("[green]v[/green] Services stopped")
    except FileNotFoundError:
        console.print("[red]x[/red] Docker not found")
        raise click.Abort()
    except subprocess.CalledProcessError:
        console.print("[red]x[/red] Failed to stop services")
        raise click.Abort()


@cli.command()
@click.option("--output", "-o", default="output")
def pull(output):
    """Pull latest service images."""
    compose = Path(output) / "docker-compose.yml"
    if not compose.exists():
        console.print("[red]x[/red] No compose file")
        return
    try:
        subprocess.run(["docker", "compose", "-f", str(compose), "pull"], check=True)
        console.print("[green]v[/green] Images pulled")
    except FileNotFoundError:
        console.print("[red]x[/red] Docker not found")
        raise click.Abort()
    except subprocess.CalledProcessError:
        console.print("[red]x[/red] Failed to pull images")
        raise click.Abort()


@cli.command()
@click.pass_context
def validate(ctx):
    """Validate homelab.yaml config."""
    config = _read_config(ctx.obj["config"])
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

    if errors or port_warnings:
        raise click.Abort()


@cli.command()
@click.argument("action", type=click.Choice(["create", "restore", "list"]))
@click.option("--output", "-o", default="output/backups")
@click.option("--file", "-f", "backup_file")
@click.pass_context
def backup(ctx, action, output, backup_file):
    """Manage config backups."""
    bdir = Path(output)

    if action == "create":
        bdir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        archive = f"homelab-backup-{ts}.tar.gz"

        files = ["homelab.yaml"]
        out_dir = Path("output")
        if out_dir.exists():
            files.append("output")

        if all(Path(f).exists() for f in files if f != "output"):
            try:
                with tarfile.open(str(bdir / archive), "w:gz") as tar:
                    for f in files:
                        tar.add(f)
            except (tarfile.TarError, OSError) as e:
                console.print(f"[red]x[/red] Backup failed: {e}")
                raise click.Abort()
            console.print(f"[green]v[/green] Backup saved: [bold]{bdir / archive}[/bold]")
        else:
            console.print("[yellow]![/yellow] Nothing to backup")

    elif action == "restore":
        if not backup_file:
            console.print("[red]x[/red] Specify --file backup.tar.gz")
            raise click.Abort()

        bp = Path(backup_file)
        if not bp.exists():
            console.print(f"[red]x[/red] File not found: {bp}")
            raise click.Abort()

        try:
            with tarfile.open(str(bp), "r:gz") as tar:
                for member in tar.getmembers():
                    name = Path(member.name)
                    if name.is_absolute() or ".." in name.parts:
                        console.print(f"[red]x[/red] Unsafe backup (path traversal): {member.name}")
                        raise click.Abort()
                    if member.issym() or member.islnk():
                        console.print(f"[red]x[/red] Unsafe backup (symlink): {member.name}")
                        raise click.Abort()
                tar.extractall()
        except tarfile.TarError as e:
            console.print(f"[red]x[/red] Backup error: {e}")
            raise click.Abort()

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
            mtime = datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            table.add_row(b.name, sz, mtime)
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
            raise click.Abort()

        t = SERVICE_TEMPLATES.get(name)
        if not t:
            console.print(f"[red]x[/red] Unknown template: {name}")
            console.print("[bold]homelab template list[/bold] to see all templates")
            raise click.Abort()

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
@click.pass_context
def clean(ctx, output):
    """Remove generated output directory."""
    p = Path(output)
    if not p.exists():
        console.print("[yellow]![/yellow] Nothing to clean")
        return

    try:
        shutil.rmtree(p)
        console.print(f"[green]v[/green] Removed {p}/")
    except PermissionError:
        console.print("[red]x[/red] Permission denied. Run [bold]sudo rm -rf {p}[/bold] manually")
        raise click.Abort()


if __name__ == "__main__":
    cli()
