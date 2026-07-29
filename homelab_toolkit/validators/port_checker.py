import socket


class PortChecker:
    def check_local_port(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return True
            except OSError:
                return False

    def find_available(self, start: int = 8000, end: int = 9000) -> int | None:
        for port in range(start, end):
            if self.check_local_port(port):
                return port
        return None

    def _normalize_ports(self, port: int | str | list) -> list:
        if isinstance(port, int):
            return [port]
        if isinstance(port, str):
            try:
                return [int(port)]
            except ValueError:
                return []
        if isinstance(port, list):
            result = []
            for p in port:
                if isinstance(p, int):
                    result.append(p)
                elif isinstance(p, str):
                    try:
                        result.append(int(p))
                    except ValueError:
                        pass
            return result
        return []

    def check_ports_in_config(self, config: dict) -> list:
        warnings = []
        services = config.get("homelab", {}).get("services", {})
        if not isinstance(services, dict):
            return warnings
        for cat, cfg in services.items():
            if not isinstance(cfg, dict):
                continue
            ports = cfg.get("ports", {})
            for name, port in ports.items():
                for p in self._normalize_ports(port):
                    if not self.check_local_port(p):
                        warnings.append(f"Port {p} ({name}) is already in use")
        return warnings
