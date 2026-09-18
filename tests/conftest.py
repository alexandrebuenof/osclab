"""Configuração comum dos testes.

`pythonpath = ["src"]` no pyproject.toml já resolve o import de `osclab`, então
aqui só ficam fixtures.
"""

import pytest

from osclab.web.server import create_app


@pytest.fixture
def cliente():
    """Cliente de teste do Flask: exercita as rotas sem abrir porta nenhuma."""
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()
