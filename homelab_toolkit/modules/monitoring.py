MONITORING_STACK = {
    "prometheus": {
        "image": "prom/prometheus:latest",
        "ports": ["9090:9090"],
        "volumes": ["./data/prometheus:/etc/prometheus"],
    },
    "grafana": {
        "image": "grafana/grafana:latest",
        "ports": ["3000:3000"],
        "volumes": ["./data/grafana:/var/lib/grafana"],
    },
    "alertmanager": {
        "image": "prom/alertmanager:latest",
        "ports": ["9093:9093"],
    },
}
