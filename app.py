"""OscLab — leitor e analisador de oscilografia.

Este arquivo é o único ponto de entrada. Ele resolve, nesta ordem:

    1. o virtualenv (cria `.venv/` ao lado deste arquivo e se re-executa dentro dele);
    2. as dependências (instala só o que falta — ver `install_requirements`);
    3. o modo pedido (`--web` sobe o servidor Flask, sem argumento faz o mesmo).

Modos:
    python app.py                    # sobe a interface web (padrão)
    python app.py --web --port 9000  # outra porta
    python app.py --versao           # imprime a versão e sai
    python app.py --ler ARQUIVO      # descreve uma oscilografia no terminal
    python app.py --offline          # instala de vendor/, nunca de um índice
    python app.py --skip-install     # não confere dependências
    python app.py --no-venv          # não usa virtualenv

A estrutura do projeto está no README.md; as regras de trabalho, no CLAUDE.md.
"""

from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
REQ_FILE = ROOT / "requirements.txt"
# Ferramentas de quem desenvolve (pytest, ruff). Ficam FORA do pacote
# distribuído: quem só usa o programa não precisa delas.
REQ_DEV_FILE = ROOT / "requirements-dev.txt"

# Wheels do pacote offline. Ausente num clone do repositório, que é o estado normal:
# `--offline` é o que uma instalação em subestação usa.
VENDOR_DIR = ROOT / "vendor"

VENV_DIR = ROOT / ".venv"
if os.name == "nt":
    VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
else:
    VENV_PYTHON = VENV_DIR / "bin" / "python"

PORTA_PADRAO = 8770

# Nome no pip -> módulo que dá para importar, quando são diferentes.
IMPORT_NAMES: dict[str, str] = {
    "flask": "flask",
    "numpy": "numpy",
}


# ---------------------------------------------------------------------------
# Virtualenv
# ---------------------------------------------------------------------------

def is_inside_target_venv() -> bool:
    """Estamos rodando DENTRO do `.venv` deste projeto?

    A comparação é entre PREFIXOS, nunca entre executáveis. No Linux o
    `.venv/bin/python` é um link simbólico para o interpretador base, então
    `VENV_PYTHON.resolve()` devolve `/usr/bin/pythonX.Y` — exatamente o que
    `sys.executable` resolve quando estamos FORA do venv. Comparar executáveis
    daria verdadeiro nos dois casos, o programa pularia a re-execução e tentaria
    instalar no Python do sistema, onde o PEP 668 recusa e o boot morre.

    `sys.prefix` aponta para o venv quando se está dentro de um e para o
    interpretador base quando não — que é a pergunta real.
    """
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return False


def create_venv() -> bool:
    """Cria o venv. Devolve False se não deu e o chamador deve seguir sem ele."""
    if VENV_PYTHON.exists():
        return True
    print(f"[INFO] Criando virtualenv em {VENV_DIR}...")
    try:
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)],
                              stderr=subprocess.STDOUT)
        subprocess.check_call([str(VENV_PYTHON), "-m", "pip",
                               "install", "--quiet", "--upgrade", "pip"])
        return True
    except subprocess.CalledProcessError:
        import shutil
        shutil.rmtree(VENV_DIR, ignore_errors=True)
        print("[AVISO] Nao consegui criar o virtualenv.")
        print("[AVISO] No Debian/Ubuntu: sudo apt install python3-venv")
        print("[AVISO] Seguindo com --break-system-packages.")
        return False


def relaunch_in_venv() -> None:
    """Re-executa este mesmo script com o Python do venv."""
    print(f"[INFO] Re-executando dentro do venv ({VENV_PYTHON})...")
    args = [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]]
    # No Windows, `os.execv` monta a linha de comando juntando os argumentos com
    # espaço e SEM aspas. Se o projeto estiver num caminho com espaço — e ele
    # está: "06 - Ferramentas" — o Python filho recebe os pedaços como
    # argumentos separados, e um "-" solto significa "leia o script da entrada
    # padrão", o que abre o REPL em vez de rodar o programa. `subprocess` recebe
    # uma lista e faz o quoting certo.
    if os.name == "nt":
        try:
            sys.exit(subprocess.call(args))
        except KeyboardInterrupt:
            sys.exit(130)
    os.execv(str(VENV_PYTHON), args)


# ---------------------------------------------------------------------------
# Dependências
# ---------------------------------------------------------------------------

def parse_requirements(req_file: Path) -> list[str]:
    """Nomes de pacote do requirements.txt, sem versão e sem comentário."""
    if not req_file.is_file():
        return []
    pkgs: list[str] = []
    for raw in req_file.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        # Referência direta do PEP 508 (`nome @ git+https://...`): o nome do
        # pacote é o que vem ANTES do '@'. Sem esta linha o "pacote" seria a URL
        # inteira, `missing_packages` nunca conseguiria importá-lo, e o pip
        # rodaria a cada boot reinstalando tudo.
        name = line.split(" @ ", 1)[0].strip() if " @ " in line else line
        for sep in ("==", ">=", "<=", "~=", ">", "<", "!="):
            if sep in name:
                name = name.split(sep, 1)[0]
                break
        pkgs.append(name.strip())
    return pkgs


def missing_packages(pkgs: list[str]) -> list[str]:
    missing = []
    for pkg in pkgs:
        module = IMPORT_NAMES.get(pkg.lower(), pkg).replace("-", "_")
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(pkg)
    return missing


def install_requirements(allow_break: bool = False, offline: bool = False) -> None:
    """Instala o que falta.

    Um boot normal só chama o pip quando um pacote falha ao IMPORTAR. É isso que
    mantém o programa utilizável numa subestação sem internet: conferir versão a
    cada boot faria o pip falhar sem rede, e o launcher morre no erro do pip.
    """
    if not REQ_FILE.is_file():
        print(f"[AVISO] requirements.txt nao encontrado em {REQ_FILE}")
        return
    missing = missing_packages(parse_requirements(REQ_FILE))
    if not missing:
        return
    print(f"[INFO] Instalando dependencias ausentes: {', '.join(missing)}")
    cmd = [sys.executable, "-m", "pip", "install", "-r", str(REQ_FILE)]
    if offline:
        # O pacote offline traz um wheel para cada dependência, então a
        # instalação não pode procurar índice nenhum: `--no-index` transforma
        # "sem rede" de um travamento silencioso de 30 s numa falha imediata e
        # legível, nomeando o wheel que falta.
        if not VENDOR_DIR.is_dir():
            sys.exit(f"[ERRO] --offline pedido, mas {VENDOR_DIR} nao existe.\n"
                     f"       Esta e' uma copia do repositorio, nao um pacote offline.")
        cmd += ["--no-index", "--find-links", str(VENDOR_DIR)]
    if allow_break:
        cmd.append("--break-system-packages")
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as exc:
        sys.exit(f"[ERRO] Falha ao instalar dependencias (codigo {exc.returncode}).")


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

def ensure_import_path() -> None:
    """Coloca `src/` no sys.path — é de lá que `osclab` é importado."""
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))


def explain_import_failure(exc: ModuleNotFoundError) -> str:
    """Transforma um ModuleNotFoundError em algo que vale a pena ler.

    As duas causas pedem respostas opostas: uma cópia incompleta é um arquivo
    faltando; uma dependência ausente é instalação que não rodou. A diferença
    está no disco, e custa um `is_file()` para saber qual é.
    """
    faltando = exc.name or "?"
    if not (SRC_DIR / "osclab" / "__init__.py").is_file():
        return (f"[ERRO] Nao achei o codigo do OscLab em {SRC_DIR}.\n"
                f"       Esta copia esta incompleta — a pasta tem que ter "
                f"`src`, `app.py` e `requirements.txt`.")
    if faltando == "osclab":
        return (f"[ERRO] Nao consegui importar `osclab` a partir de {SRC_DIR}.\n"
                f"       O arquivo existe, entao o problema e' de permissao ou "
                f"de copia parcial.")
    dica = (f"           python app.py --offline   (usa os wheels de "
            f"{VENDOR_DIR.name}/)" if VENDOR_DIR.is_dir()
            else "           python app.py             (instala as dependencias)")
    return (f"[ERRO] Falta a dependencia `{faltando}`.\n"
            f"       As dependencias ainda nao foram instaladas aqui. Rode:\n"
            f"{dica}\n"
            f"       (`--skip-install` pula justamente essa instalacao.)")


def read_version_file() -> str:
    """Lê `VERSION` direto do disco.

    De propósito NÃO importa `osclab`: imprimir a versão tem que funcionar numa
    instalação quebrada — que costuma ser justamente quando alguém pergunta.
    """
    f = ROOT / "VERSION"
    return f.read_text(encoding="utf-8").strip() if f.is_file() else "0.0.0+desconhecida"


def run_web(port: int) -> None:
    ensure_import_path()
    try:
        from osclab.web.server import serve
    except ModuleNotFoundError as exc:
        sys.exit(explain_import_failure(exc))
    print(f"[INFO] OscLab {read_version_file()}")
    print(f"[INFO] Abra http://localhost:{port}/ no navegador. Ctrl+C encerra.")
    print("-" * 62)
    serve(port=port)


def run_read(caminho: list[str]) -> None:
    """`--ler`: abre uma oscilografia e descreve no terminal.

    A interface grafica so' chega no marco 0.3; ate' la' este e' o jeito de
    apontar o leitor para um arquivo e ver o que ele entendeu.
    """
    ensure_import_path()
    try:
        from osclab.cli.inspecionar import main as inspecionar
    except ModuleNotFoundError as exc:
        sys.exit(explain_import_failure(exc))
    sys.exit(inspecionar(caminho))


def run_tests() -> None:
    """Roda a suíte de testes, instalando as ferramentas de desenvolvimento se
    ainda faltarem.

    `--preparar` instala só o que o programa precisa para RODAR — e é isso que
    mantém o pacote distribuído enxuto. pytest e ruff não entram lá. Então a
    primeira vez que alguém pede os testes é aqui que elas são instaladas, em
    vez de o menu falhar com um `No module named pytest` que não explica nada.
    """
    try:
        importlib.import_module("pytest")
    except ImportError:
        if not REQ_DEV_FILE.is_file():
            sys.exit(f"[ERRO] {REQ_DEV_FILE} nao existe — nao sei o que instalar.")
        print("[INFO] pytest ainda nao esta instalado aqui.")
        print("[INFO] Instalando as ferramentas de desenvolvimento "
              "(requirements-dev.txt)...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install",
                                   "-r", str(REQ_DEV_FILE)])
        except subprocess.CalledProcessError as exc:
            sys.exit(f"[ERRO] Falha ao instalar as ferramentas de "
                     f"desenvolvimento (codigo {exc.returncode}).\n"
                     f"       Isso exige internet — o pacote offline nao as traz.")
    print("-" * 62)
    sys.exit(subprocess.call([sys.executable, "-m", "pytest"], cwd=str(ROOT)))


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.py", add_help=True,
                                     description="OscLab — leitor de oscilografia")
    parser.add_argument("--web", action="store_true",
                        help="sobe a interface web (padrao)")
    parser.add_argument("--port", type=int, default=PORTA_PADRAO,
                        help=f"porta do servidor (padrao {PORTA_PADRAO})")
    parser.add_argument("--versao", action="store_true", help="imprime a versao e sai")
    parser.add_argument("--preparar", action="store_true",
                        help="cria o venv e instala as dependencias, sem subir o servidor")
    parser.add_argument("--testes", action="store_true",
                        help="roda a suite de testes (instala pytest se faltar)")
    parser.add_argument("--ler", nargs="+", metavar="ARQUIVO", default=None,
                        help="descreve uma oscilografia no terminal e sai")
    parser.add_argument("--offline", action="store_true",
                        help="instala de vendor/, nunca de um indice")
    parser.add_argument("--skip-install", action="store_true",
                        help="nao confere as dependencias")
    parser.add_argument("--no-venv", action="store_true", help="nao usa virtualenv")
    args = parser.parse_args()

    if args.versao:
        print(read_version_file())
        return

    usar_venv = not args.no_venv
    quebrar = False
    if usar_venv and not is_inside_target_venv():
        if create_venv():
            relaunch_in_venv()
            return  # inalcançável no POSIX (execv), alcançável no Windows
        quebrar = True
    elif not usar_venv:
        quebrar = True

    if not args.skip_install:
        install_requirements(allow_break=quebrar, offline=args.offline)

    if args.ler:
        run_read(args.ler)   # não retorna

    if args.testes:
        run_tests()   # não retorna

    if args.preparar:
        # Chegar aqui já é a preparação: o venv existe e as dependências estão
        # instaladas. Só não subimos o servidor.
        print(f"[OK] Pasta preparada. Virtualenv em {VENV_DIR}")
        print("[OK] Para rodar: app.py --web")
        return

    run_web(port=args.port)


if __name__ == "__main__":
    main()
