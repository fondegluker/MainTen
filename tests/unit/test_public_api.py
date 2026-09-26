import ast
import glob
import importlib
import os


def test_all_test_imports_exist_in_app_modules():
    """Regression guard: parse all tests/**/*.py files and assert that every imported symbol from app.* exists."""
    test_files = glob.glob("tests/**/*.py", recursive=True)
    assert len(test_files) > 0, "No test files found"

    missing_symbols = []

    for test_path in test_files:
        with open(test_path, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=test_path)
            except SyntaxError as e:
                missing_symbols.append(f"Syntax error in test file {test_path}: {e}")
                continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module_name = node.module
                if module_name and (module_name == "app" or module_name.startswith("app.")):
                    try:
                        mod = importlib.import_module(module_name)
                    except (ImportError, ModuleNotFoundError, AttributeError) as exc:
                        missing_symbols.append(
                            f"[{test_path}:{node.lineno}] Failed to import module '{module_name}': {exc}"
                        )
                        continue

                    for alias in node.names:
                        symbol_name = alias.name
                        if symbol_name == "*":
                            continue
                        if not hasattr(mod, symbol_name):
                            missing_symbols.append(
                                f"[{test_path}:{node.lineno}] Symbol '{symbol_name}' not found in module '{module_name}'"
                            )

    assert not missing_symbols, "Found missing imported symbols in test files:\n" + "\n".join(
        f"  - {err}" for err in missing_symbols
    )


def test_all_app_modules_import_cleanly():
    """Assert every python file under app/ imports cleanly without errors."""
    app_files = glob.glob("app/**/*.py", recursive=True)
    assert len(app_files) > 0, "No app files found"

    for filepath in app_files:
        if os.path.basename(filepath) == "__init__.py":
            mod_path = os.path.dirname(filepath).replace(os.sep, ".")
        else:
            mod_path = filepath[:-3].replace(os.sep, ".")

        try:
            importlib.import_module(mod_path)
        except (ImportError, ModuleNotFoundError, AttributeError) as exc:
            raise AssertionError(f"Failed to import app module '{mod_path}' ({filepath}): {exc}") from exc
