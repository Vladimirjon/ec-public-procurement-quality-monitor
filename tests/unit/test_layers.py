"""AC6: the four architectural layers are importable packages.

`domain` may import only the standard library and itself (AGENTS.md boundaries).
"""

import ast
import importlib
import sys
from pathlib import Path

import pytest

ROOT_PACKAGE = "ec_procurement_quality"
DOMAIN_PACKAGE = f"{ROOT_PACKAGE}.domain"
LAYERS = ("domain", "application", "infrastructure", "interfaces")


@pytest.mark.parametrize("layer", LAYERS)
def test_layer_package_is_importable(layer: str) -> None:
    module = importlib.import_module(f"{ROOT_PACKAGE}.{layer}")

    assert module.__name__ == f"{ROOT_PACKAGE}.{layer}"
    # A regular package has an __init__.py and therefore a __file__. A bare
    # directory (for example an empty local folder) only imports as a namespace
    # package, which has no __file__, and must not count.
    assert module.__file__ is not None, f"{layer} needs an __init__.py"
    assert module.__path__, f"{layer} must be a package, not a plain module"


def _imported_modules(source: str) -> list[tuple[str, int]]:
    """Return (module name, relative level) for every import in `source`."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend((alias.name, 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", node.level))
    return found


def test_layer_domain_imports_only_stdlib_and_itself() -> None:
    domain = importlib.import_module(DOMAIN_PACKAGE)
    assert domain.__file__ is not None, "domain needs an __init__.py"
    domain_root = Path(next(iter(domain.__path__)))

    offenders: list[str] = []
    for path in sorted(domain_root.rglob("*.py")):
        depth = len(path.relative_to(domain_root).parts) - 1
        source = path.read_text(encoding="utf-8")
        for name, level in _imported_modules(source):
            if level > 0:
                # A relative import stays inside `domain` unless it climbs
                # above the domain root.
                if level - 1 > depth:
                    offenders.append(
                        f"{path.name}: relative import climbs out of domain"
                    )
                continue
            top = name.split(".")[0]
            inside_domain = name == DOMAIN_PACKAGE or name.startswith(
                f"{DOMAIN_PACKAGE}."
            )
            if top not in sys.stdlib_module_names and not inside_domain:
                offenders.append(f"{path.name}: {name}")

    assert offenders == []


APPLICATION_PACKAGE = f"{ROOT_PACKAGE}.application"
RAW_EVIDENCE_PORT_MODULE = "raw_evidence_store.py"


def _inside(name: str, package: str) -> bool:
    return name == package or name.startswith(f"{package}.")


def test_layer_application_imports_only_stdlib_domain_and_itself() -> None:
    """Feature raw-evidence-store (F1), AC11: `application` may import the
    standard library, `domain` and itself, never `infrastructure` or
    `interfaces`.
    """
    application = importlib.import_module(APPLICATION_PACKAGE)
    assert application.__file__ is not None, "application needs an __init__.py"
    application_root = Path(next(iter(application.__path__)))

    # The check must not pass on an empty package: the storage port is the
    # module this boundary exists to guard.
    port_module = application_root / RAW_EVIDENCE_PORT_MODULE
    assert port_module.is_file(), f"application needs {RAW_EVIDENCE_PORT_MODULE}"

    offenders: list[str] = []
    for path in sorted(application_root.rglob("*.py")):
        depth = len(path.relative_to(application_root).parts) - 1
        source = path.read_text(encoding="utf-8")
        for name, level in _imported_modules(source):
            if level > 0:
                # How many packages above `application` the relative import
                # reaches: 0 or less stays inside `application`; 1 reaches the
                # root package, where only `domain` is allowed.
                climb = level - 1 - depth
                if climb <= 0:
                    continue
                if climb == 1 and _inside(name, "domain"):
                    continue
                offenders.append(f"{path.name}: {'.' * level}{name}")
                continue
            top = name.split(".")[0]
            allowed = _inside(name, APPLICATION_PACKAGE) or _inside(
                name, DOMAIN_PACKAGE
            )
            if top not in sys.stdlib_module_names and not allowed:
                offenders.append(f"{path.name}: {name}")

    assert offenders == []


INFRASTRUCTURE_PACKAGE = f"{ROOT_PACKAGE}.infrastructure"
SERCOP_ADAPTER_MODULE = "sercop_source.py"
HTTP_CLIENT_LIBRARY = "httpx"


def _names_http_client_library(source: str) -> bool:
    """True when `source` imports `httpx` in any form.

    Covers `import httpx`, `import httpx.x`, `from httpx import x`,
    `from httpx.x import y` (also relative), `from package import httpx` and a
    string-literal dynamic import (`__import__("httpx")`,
    `importlib.import_module("httpx")`).
    """
    for name, _level in _imported_modules(source):
        if name.split(".")[0] == HTTP_CLIENT_LIBRARY:
            return True
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and any(
            alias.name.split(".")[0] == HTTP_CLIENT_LIBRARY for alias in node.names
        ):
            return True
        if isinstance(node, ast.Call) and node.args:
            function = node.func
            called = (
                function.id
                if isinstance(function, ast.Name)
                else function.attr
                if isinstance(function, ast.Attribute)
                else ""
            )
            first = node.args[0]
            if (
                called in {"__import__", "import_module"}
                and isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and first.value.split(".")[0] == HTTP_CLIENT_LIBRARY
            ):
                return True
    return False


def test_layer_only_infrastructure_imports_httpx() -> None:
    """Feature sercop-source-adapter (F2), AC12 and ADR 0006: the HTTP client
    library is imported only in `infrastructure`; `domain`, `application`,
    `interfaces` and the root package never import it, in any form.
    """
    root_package = importlib.import_module(ROOT_PACKAGE)
    assert root_package.__file__ is not None, "the root package needs an __init__.py"
    root = Path(root_package.__file__).parent

    # The check must not pass vacuously: the adapter is the one module that is
    # supposed to import the library.
    adapter = root / "infrastructure" / SERCOP_ADAPTER_MODULE
    assert adapter.is_file(), (
        f"infrastructure needs {SERCOP_ADAPTER_MODULE} ({adapter} is missing)"
    )
    assert _names_http_client_library(adapter.read_text(encoding="utf-8")), (
        f"infrastructure/{SERCOP_ADAPTER_MODULE} must import {HTTP_CLIENT_LIBRARY}"
    )

    guarded = sorted(root.glob("*.py"))
    for layer in ("domain", "application", "interfaces"):
        guarded.extend(sorted((root / layer).rglob("*.py")))
    assert guarded, "no module was checked"

    offenders = [
        str(path.relative_to(root))
        for path in guarded
        if _names_http_client_library(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []
