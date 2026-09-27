"""Template compile smoke test to catch Jinja syntax errors on all templates."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def test_all_templates_compile():
    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=True,
    )
    errors = []
    for path in Path("app/templates").rglob("*.html"):
        rel = path.relative_to("app/templates").as_posix()
        try:
            env.get_template(rel)
        except Exception as exc:
            errors.append(f"{rel}: {exc}")
    assert not errors, "\n".join(errors)
