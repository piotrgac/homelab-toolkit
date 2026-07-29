MEDIA_STACK = {
    "jellyfin": {
        "image": "jellyfin/jellyfin:latest",
        "ports": ["8096:8096"],
        "volumes": ["./data/jellyfin:/config", "./data/media:/media"],
    },
    "radarr": {
        "image": "linuxserver/radarr:latest",
        "ports": ["7878:7878"],
        "volumes": ["./data/radarr:/config", "./data/media:/media"],
    },
    "sonarr": {
        "image": "linuxserver/sonarr:latest",
        "ports": ["8989:8989"],
        "volumes": ["./data/sonarr:/config", "./data/media:/media"],
    },
    "prowlarr": {
        "image": "linuxserver/prowlarr:latest",
        "ports": ["9696:9696"],
    },
    "qbittorrent": {
        "image": "linuxserver/qbittorrent:latest",
        "ports": ["8080:8080", "6881:6881"],
        "volumes": ["./data/qbittorrent:/config", "./data/downloads:/downloads"],
    },
}
