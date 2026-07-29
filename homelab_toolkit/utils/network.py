import ipaddress


def validate_subnet(subnet):
    try:
        ipaddress.IPv4Network(subnet, strict=False)
        return True
    except (ValueError, TypeError):
        return False


def hosts(subnet):
    try:
        return [str(h) for h in ipaddress.IPv4Network(subnet, strict=False).hosts()]
    except (ValueError, TypeError):
        return None


def in_subnet(ip, subnet):
    try:
        return ipaddress.IPv4Address(ip) in ipaddress.IPv4Network(subnet, strict=False)
    except (ValueError, TypeError):
        return False
