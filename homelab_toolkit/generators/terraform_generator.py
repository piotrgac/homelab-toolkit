from pathlib import Path
from rich.console import Console

console = Console()


class TerraformGenerator:
    def __init__(self, dry_run=False, output_dir=Path("output")):
        self.dry_run = dry_run
        self.output_dir = output_dir

    def generate(self, config):
        homelab = config.get("homelab", {})
        net = homelab.get("network", {})

        tf = self.output_dir / "terraform"
        if not self.dry_run:
            tf.mkdir(parents=True, exist_ok=True)

        self._write_main(tf, net, homelab)
        self._write_vars(tf, homelab)
        self._write_outputs(tf)
        self._write_terraformrc(tf)

        console.print(f"[green]v[/green] Terraform config in {tf}/")

    def _write_file(self, path, content):
        if self.dry_run:
            console.print(f"[dim]--- {path.relative_to(self.output_dir)} ---[/dim]")
            console.print(content)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.lstrip("\n"))
        console.print(f"  [green]v[/green] {path.relative_to(self.output_dir)}")

    def _write_main(self, tf, net, homelab):
        subnet = net.get("subnet", "192.168.1.0/24")
        gateway = net.get("gateway", "192.168.1.1")
        name = homelab.get("name", "my-homelab")

        content = f"""terraform {{
  required_providers {{
    docker = {{
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }}
    libvirt = {{
      source  = "dmacvicar/libvirt"
      version = "~> 0.7"
    }}
  }}
}}

locals {{
  name = "{name}"
  subnet = "{subnet}"
  gw = "{gateway}"
}}

resource "docker_network" "net" {{
  name = "${{{{local.name}}}}-net"
  ipam_config {{
    subnet  = local.subnet
    gateway = local.gw
  }}
}}

resource "docker_volume" "data" {{
  name = "${{{{local.name}}}}-data"
}}

resource "libvirt_network" "net" {{
  name   = "${{{{local.name}}}}-net"
  mode   = "nat"
  domain = "${{{{local.name}}}}.local"
  addresses = [local.subnet]
}}

resource "libvirt_volume" "os" {{
  name   = "${{{{local.name}}}}-os"
  source = "https://dl.rockylinux.org/vault/rocky/9/images/Rocky-9-GenericCloud-Base.latest.x86_64.qcow2"
  format = "qcow2"
}}

resource "libvirt_domain" "vm" {{
  name   = "${{{{local.name}}}}-vm"
  memory = "2048"
  vcpu   = 2
  network_interface {{
    network_id = libvirt_network.net.id
  }}
  disk {{
    volume_id = libvirt_volume.os.id
  }}
  cloudinit = libvirt_cloudinit_disk.ci.id
}}

resource "libvirt_cloudinit_disk" "ci" {{
  name = "${{{{local.name}}}}-cloudinit.iso"
  user_data = <<-EOF
#cloud-config
hostname: ${{{{local.name}}}}
users:
  - name: admin
    sudo: ALL=(ALL) NOPASSWD:ALL
    ssh_authorized_keys:
      - ${{{{file("~/.ssh/id_rsa.pub")}}}}
packages:
  - docker
  - docker-compose-plugin
runcmd:
  - systemctl enable --now docker
EOF
}}

data "template_file" "compose" {{
  template = file("${{{{path.module}}}}/../docker-compose.yml")
}}
"""
        self._write_file(tf / "main.tf", content)

    def _write_vars(self, tf, homelab):
        net = homelab.get("network", {})
        content = f"""variable "name" {{
  description = "Project name"
  type        = string
  default     = "{homelab.get("name", "my-homelab")}"
}}

variable "subnet" {{
  type    = string
  default = "{net.get("subnet", "192.168.1.0/24")}"
}}

variable "gateway" {{
  type    = string
  default = "{net.get("gateway", "192.168.1.1")}"
}}

variable "vm_memory" {{
  type    = number
  default = 2048
}}

variable "vm_vcpu" {{
  type    = number
  default = 2
}}
"""
        self._write_file(tf / "variables.tf", content)

    def _write_outputs(self, tf):
        content = """output "net_id" {
  value = docker_network.net.id
}

output "vm_ip" {
  value = libvirt_domain.vm.network_interface[0].addresses
}

output "vm_name" {
  value = libvirt_domain.vm.name
}
"""
        self._write_file(tf / "outputs.tf", content)

    def _write_terraformrc(self, tf):
        self._write_file(tf / ".terraformrc", """provider_installation {
  direct {}
}
""")
