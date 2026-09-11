from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).parents[2] / "templates"
environment = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_document(template_name: str, context: dict[str, Any]) -> str:
    """Render trusted server-side document templates to HTML.

    PDF conversion belongs in a background worker adapter so API requests do
    not block on Chromium/WeasyPrint.
    """
    return environment.get_template(template_name).render(**context)
