import backend
from app.main import app


def test_backend_module_exposes_app() -> None:
    assert backend.app is app
