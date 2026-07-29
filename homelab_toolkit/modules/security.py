SECURITY_STACK = {
    "authelia": {
        "image": "authelia/authelia:latest",
        "ports": ["9091:9091"],
        "volumes": ["./data/authelia:/config"],
    },
    "vault": {
        "image": "hashicorp/vault:latest",
        "ports": ["8200:8200"],
        "cap_add": ["IPC_LOCK"],
    },
}
