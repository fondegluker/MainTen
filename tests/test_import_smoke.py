"""Import smoke test suite for verifying module importability and package naming safety rules."""

import importlib
import keyword
import pkgutil
import traceback
from pathlib import Path

import app as app_package


def test_all_app_modules_import_without_errors():
    """Recursively walk and import every module under app/ using importlib."""
    errors = []
    imported_count = 0

    for _, modname, _ in pkgutil.walk_packages(app_package.__path__, prefix="app."):
        try:
            mod = importlib.import_module(modname)
            assert mod is not None
            imported_count += 1
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc()
            errors.append(f"Module '{modname}' failed to import: {exc}\n{tb}")

    assert not errors, f"Failed to import {len(errors)} module(s):\n" + "\n".join(errors)
    assert imported_count > 0, "No modules were imported under app package"


def test_no_python_keyword_identifiers_in_app_filesystem():
    """Scan Python packages and modules under app/ to ensure no directory or .py file name is a Python reserved keyword."""
    app_dir = Path("app")
    keyword_violations = []

    for path in app_dir.rglob("*"):
        if path.name == "__pycache__":
            continue

        # Check Python directories (packages) and .py files
        is_python_file = path.is_file() and path.suffix == ".py"
        is_python_dir = path.is_dir()

        if is_python_file or is_python_dir:
            stem = path.stem if is_python_file else path.name
            if keyword.iskeyword(stem):
                keyword_violations.append(f"Forbidden Python reserved keyword name '{stem}' found at '{path}'")

    assert not keyword_violations, "Found reserved keyword filesystem paths:\n" + "\n".join(keyword_violations)


def test_fleet_import_package_name_uniqueness():
    """Explicitly verify app.importer is canonical and app/import directory does not exist."""
    app_dir = Path("app")
    assert (app_dir / "importer").is_dir(), "app/importer package directory must exist"
    assert not (app_dir / "import").exists(), "app/import directory must NOT exist (reserved keyword conflict)"


def test_single_source_of_truth_schema_constant_sharing():
    """Verify FLEET_IMPORT_COLUMNS schema constant is imported (not redefined) by parser and template generator."""
    from app.importer.schema import FLEET_IMPORT_COLUMNS
    from app.importer.template import FLEET_IMPORT_COLUMNS as TEMPLATE_COLUMNS
    from app.routers.import_fleet import FLEET_IMPORT_COLUMNS as PARSER_COLUMNS

    assert FLEET_IMPORT_COLUMNS is PARSER_COLUMNS, (
        "app.routers.import_fleet must import FLEET_IMPORT_COLUMNS from app.importer.schema, not redefine it"
    )
    assert FLEET_IMPORT_COLUMNS is TEMPLATE_COLUMNS, (
        "app.importer.template must import FLEET_IMPORT_COLUMNS from app.importer.schema, not redefine it"
    )
