from pathlib import Path
from jinja2 import Template


def render_file(path, context):
    return Template(Path(path).read_text()).render(**context)


def render_string(tpl, context):
    return Template(tpl).render(**context)
