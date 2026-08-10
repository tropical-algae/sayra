import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "sayra"


def test_package_root_contains_only_declared_layers() -> None:
    directories = {
        path.name
        for path in PACKAGE_ROOT.iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }

    assert directories == {"app", "common", "core"}


def test_core_and_common_do_not_depend_on_fastapi_application_layer() -> None:
    for layer in ("core", "common"):
        for source in (PACKAGE_ROOT / layer).rglob("*.py"):
            assert "sayra.app" not in source.read_text(), source


def test_prompt_body_files_are_external_to_python() -> None:
    prompt_root = PACKAGE_ROOT / "core" / "prompts" / "templates"

    assert len(list(prompt_root.glob("*.md"))) >= 1
    assert not list((PACKAGE_ROOT / "core" / "prompts").glob("*.md"))


def test_application_services_do_not_contain_sql_queries() -> None:
    for source in (PACKAGE_ROOT / "app" / "services").glob("*.py"):
        text = source.read_text()
        assert "sqlalchemy import select" not in text, source
        assert ".execute(" not in text, source


def test_crud_functions_use_explicit_database_operation_names() -> None:
    allowed_prefixes = ("select_", "insert_", "update_", "delete_")
    for source in (PACKAGE_ROOT / "core" / "db" / "crud").glob("*.py"):
        tree = ast.parse(source.read_text())
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                assert node.name.startswith(allowed_prefixes), (
                    source,
                    node.name,
                )


def test_crud_functions_manage_optional_database_sessions() -> None:
    for source in (PACKAGE_ROOT / "core" / "db" / "crud").glob("*.py"):
        tree = ast.parse(source.read_text())
        for node in tree.body:
            if not isinstance(node, ast.AsyncFunctionDef) or node.name.startswith("_"):
                continue
            assert any(
                isinstance(decorator, ast.Name) and decorator.id == "with_db_session"
                for decorator in node.decorator_list
            ), (source, node.name)


def test_repeated_primitives_are_centralized_in_common() -> None:
    for layer in ("app", "core"):
        for source in (PACKAGE_ROOT / layer).rglob("*.py"):
            if source.name == "models.py":
                continue
            text = source.read_text()
            assert "uuid.uuid4" not in text, source
            assert "datetime.now(timezone.utc)" not in text, source
