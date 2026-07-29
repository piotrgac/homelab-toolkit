from homelab_toolkit.generators.docker_generator import SERVICE_TEMPLATES


class ConfigValidator:
    def validate(self, config):
        errors = []

        if not isinstance(config, dict):
            errors.append("Config must be a dictionary")
            return errors

        homelab = config.get("homelab")
        if not homelab:
            errors.append("Missing 'homelab' key")
            return errors

        if not isinstance(homelab, dict):
            errors.append("'homelab' must be a dictionary")
            return errors

        net = homelab.get("network")
        if not net:
            errors.append("Missing 'homelab.network'")
        elif not isinstance(net, dict):
            errors.append("'homelab.network' must be a dictionary")
        elif "subnet" not in net:
            errors.append("Missing 'homelab.network.subnet' (e.g. 192.168.1.0/24)")

        services = homelab.get("services")
        if not services:
            errors.append("No services defined under 'homelab.services'")
        else:
            self._check_services(services, errors, config.get("custom_templates", {}))

        if "backup" in config:
            b = config["backup"]
            if not isinstance(b, dict):
                errors.append("'backup' must be a dictionary")

        ct = config.get("custom_templates")
        if ct:
            if not isinstance(ct, dict):
                errors.append("'custom_templates' must be a dictionary")
            else:
                for name, tmpl in ct.items():
                    if not isinstance(tmpl, dict):
                        errors.append(f"custom_templates.{name} is not a dict")
                    elif "image" not in tmpl:
                        errors.append(f"custom_templates.{name} missing 'image' key")

        return errors

    def _check_services(self, services, errors, custom):
        if not isinstance(services, dict):
            errors.append("'services' must be a dictionary")
            return

        for cat, cfg in services.items():
            if not isinstance(cfg, dict):
                errors.append(f"services.{cat} must be a dictionary")
                continue

            stack = cfg.get("stack", [])
            if not isinstance(stack, list):
                errors.append(f"services.{cat}.stack must be a list")
                continue

            for svc in stack:
                if svc not in SERVICE_TEMPLATES and svc not in custom:
                    errors.append(
                        f"services.{cat}.stack: '{svc}' - unknown service. "
                        f"Run 'homelab template list' to see available services"
                    )

            ports = cfg.get("ports", {})
            if not isinstance(ports, dict):
                errors.append(f"services.{cat}.ports must be a dict")
            else:
                for name, port in ports.items():
                    if isinstance(port, list):
                        for p in port:
                            if not isinstance(p, (int, str)):
                                errors.append(f"services.{cat}.ports.{name}: invalid port '{p}'")
                    elif not isinstance(port, (int, str)):
                        errors.append(f"services.{cat}.ports.{name}: invalid port '{port}'")
