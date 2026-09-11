from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

TEMPLATE_DIR = Path(__file__).parents[2] / "templates"
environment = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_document(template_name: str, context: dict[str, Any]) -> str:
    """Render an autoescaped, trusted server-side template."""
    return environment.get_template(template_name).render(**context)


def render_pdf(template_name: str, context: dict[str, Any]) -> bytes:
    html = render_document(template_name, context)
    return HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf()
