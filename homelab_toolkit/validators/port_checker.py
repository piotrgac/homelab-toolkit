import socket


class PortChecker:
    def check_local_port(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return True
            except OSError:
                return False

    def find_available(self, start=8000, end=9000):
        for port in range(start, end):
            if self.check_local_port(port):
                return port
        return None

    def check_ports_in_config(self, config):
        warnings = []
        services = config.get("homelab", {}).get("services", {})
        if not isinstance(services, dict):
            return warnings
        for cat, cfg in services.items():
            ports = cfg.get("ports", {})
            for name, port in ports.items():
                if isinstance(port, int) and not self.check_local_port(port):
                    warnings.append(f"Port {port} ({name}) is already in use")
        return warnings
