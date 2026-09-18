"""Todos os caminhos do OscLab saem daqui. Nenhum outro módulo monta um.

Duas razões, e as duas vão cobrar o preço depois se forem ignoradas:

1. **Instalação versionada.** O programa roda de `versions/<versao>/`, mas os
   dados do usuário (configuração, acervo de arquivos, cache) moram FORA dessa
   pasta, para que uma atualização nunca os toque. O launcher informa as duas
   raízes por variável de ambiente; este módulo é quem as lê.
2. **Empacotamento futuro.** Se um dia o programa virar um `.exe`, os arquivos
   mudam de lugar. Com tudo saindo daqui, isso é um arquivo para ajustar em vez
   de cinquenta.

Variáveis de ambiente:
    OSCLAB_ROOT       raiz da versão em execução (padrão: a raiz do projeto)
    OSCLAB_DATA_DIR   dados do usuário           (padrão: a mesma raiz)
"""

from __future__ import annotations

import os
from pathlib import Path

# Este arquivo é src/osclab/paths.py — a raiz do projeto está três níveis acima.
_ESTE_ARQUIVO = Path(__file__).resolve()
_RAIZ_PADRAO = _ESTE_ARQUIVO.parent.parent.parent


def _da_env(nome: str, padrao: Path) -> Path:
    valor = os.environ.get(nome, "").strip()
    return Path(valor).resolve() if valor else padrao


#: Raiz da versão em execução: onde moram `app.py`, `src/`, `data/`.
PROJECT_ROOT: Path = _da_env("OSCLAB_ROOT", _RAIZ_PADRAO)

#: Dados do usuário. Uma atualização nunca lê, move ou migra o que está aqui.
DATA_DIR: Path = _da_env("OSCLAB_DATA_DIR", PROJECT_ROOT)

#: Código-fonte do pacote.
SRC_DIR: Path = PROJECT_ROOT / "src"
PACKAGE_DIR: Path = SRC_DIR / "osclab"

#: Configuração. `config.ini` fica fora do git; `config.ini.example` é versionado.
CONFIG_DIR: Path = DATA_DIR / "config"
CONFIG_FILE: Path = CONFIG_DIR / "config.ini"
CONFIG_EXAMPLE: Path = PROJECT_ROOT / "config" / "config.ini.example"

#: Dados de referência que acompanham o programa (perfis de IED, tabelas).
REFERENCE_DIR: Path = PROJECT_ROOT / "data"

#: Oscilografias de exemplo, usadas pelos testes.
SAMPLES_DIR: Path = PROJECT_ROOT / "samples"

#: Gerado em tempo de execução. Nada aqui é versionado nem precisa sobreviver.
CACHE_DIR: Path = DATA_DIR / "cache"

#: Acervo de arquivos do usuário, endereçado por conteúdo (sha256).
LIBRARY_DIR: Path = DATA_DIR / "library"

#: Recursos servidos pela web (CSS, JS, fontes). Viajam com o pacote.
WEB_DIR: Path = PACKAGE_DIR / "web"
STATIC_DIR: Path = WEB_DIR / "static"
TEMPLATES_DIR: Path = WEB_DIR / "templates"

#: Arquivo com o número da versão.
VERSION_FILE: Path = PROJECT_ROOT / "VERSION"


def ensure_runtime_dirs() -> None:
    """Cria as pastas de tempo de execução. Idempotente."""
    for pasta in (CONFIG_DIR, CACHE_DIR, LIBRARY_DIR):
        pasta.mkdir(parents=True, exist_ok=True)


def is_within(caminho: Path, base: Path) -> bool:
    """`caminho` está dentro de `base`?

    Usado antes de servir ou abrir qualquer arquivo cujo nome tenha vindo do
    navegador — é o que impede um `../../` de escapar da pasta pretendida.
    """
    try:
        Path(caminho).resolve().relative_to(Path(base).resolve())
        return True
    except (ValueError, OSError):
        return False
