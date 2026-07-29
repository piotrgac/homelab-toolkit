STORAGE_STACK = {
    "nextcloud": {
        "image": "nextcloud:latest",
        "ports": ["8081:80"],
        "volumes": ["./data/nextcloud/html:/var/www/html", "./data/nextcloud/apps:/var/www/html/custom_apps"],
    },
    "samba": {
        "image": "dperson/samba:latest",
        "ports": ["139:139", "445:445"],
        "volumes": ["./data/samba:/mount"],
        "command": "-u \"admin;password\" -s \"homelab;/mount;yes;no;no;admin\"",
    },
}
