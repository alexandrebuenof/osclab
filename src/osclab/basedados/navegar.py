"""Um navegador de pastas para a tela escolher onde a base vai morar.

## Por que isto existe no servidor

O navegador não entrega o caminho absoluto de uma pasta — nem com
`<input type="file" webkitdirectory>`, que devolve só nomes relativos. É uma
proteção dele, e é certa: uma página qualquer não pode saber como o disco de
quem a abriu está organizado.

Mas o OscLab roda NA máquina do usuário, servindo só `127.0.0.1`, e a pasta
que ele quer escolher é a dele. Então quem lista é o servidor — e a tela só
mostra o que ele já poderia ver abrindo o Explorer.

## Duas formas de escolher

A primeira é o **diálogo do próprio sistema** — a mesma janela de «salvar
em…» que todo programa do Windows abre. É o que a pessoa já sabe usar: tem
barra de endereço, favoritos, «nova pasta». Ele roda num processo à parte e
devolve o caminho; é a forma preferida.

A segunda é a lista aqui de baixo, desenhada na página. Ela existe porque o
diálogo do sistema depende do `tkinter`, que pode não estar instalado — numa
instalação enxuta do Python, ou num servidor sem ambiente gráfico. Quando o
primeiro não abre, a tela cai neste sem dizer nada de errado: o trabalho é o
mesmo, só a janela é outra.

## O que ele mostra, e o que não

Só **pastas**: arquivo nenhum aparece, porque a pergunta é «onde», não «qual».
Pasta oculta (começando em ponto) fica de fora, e pasta sem permissão de
leitura aparece vazia em vez de derrubar a listagem — num disco de rede isso
é rotina, não exceção.
"""

from __future__ import annotations

import os
import string
from pathlib import Path


def _drives() -> list[Path]:
    """As raízes do computador.

    No Windows, as letras que existem — e descobrir isso é sondar de A a Z,
    porque não há lista pronta antes do Python 3.12. Fora dele, a raiz é uma.
    """
    if os.name != "nt":
        return [Path("/")]
    achadas = []
    for letra in string.ascii_uppercase:
        caminho = Path(f"{letra}:\\")
        try:
            if caminho.exists():
                achadas.append(caminho)
        except OSError:
            continue
    return achadas


def atalhos() -> list[dict]:
    """Os lugares de onde quase toda escolha começa."""
    casa = Path.home()
    candidatos = [("sua pasta", casa),
                  ("Documentos", casa / "Documents"),
                  ("Documentos", casa / "Documentos"),
                  ("Área de trabalho", casa / "Desktop")]
    saida, vistos = [], set()
    for rotulo, caminho in candidatos:
        if caminho.is_dir() and str(caminho) not in vistos:
            vistos.add(str(caminho))
            saida.append({"nome": rotulo, "caminho": str(caminho)})
    for drive in _drives():
        saida.append({"nome": str(drive), "caminho": str(drive)})
    return saida


def listar(onde: str | None = None) -> dict:
    """As subpastas de `onde`. Sem `onde`, começa na pasta do usuário."""
    alvo = Path(onde).expanduser() if onde else Path.home()
    try:
        alvo = alvo.resolve()
    except OSError:
        alvo = Path.home()
    if not alvo.is_dir():
        return {"atual": str(alvo), "existe": False, "pai": None,
                "pastas": [], "atalhos": atalhos()}

    pastas = []
    try:
        for item in sorted(alvo.iterdir(), key=lambda p: p.name.lower()):
            if item.name.startswith("."):
                continue
            try:
                if not item.is_dir():
                    continue
            except OSError:
                continue
            pastas.append({"nome": item.name, "caminho": str(item)})
    except (PermissionError, OSError):
        # Pasta sem permissão volta VAZIA, não quebrada: em disco de rede
        # isso acontece o tempo todo, e derrubar a listagem faria a tela
        # parecer com defeito.
        pastas = []

    pai = alvo.parent
    return {
        "atual": str(alvo),
        "existe": True,
        "pai": None if pai == alvo else str(pai),
        "pastas": pastas,
        "atalhos": atalhos(),
    }


# ---------------------------------------------------------------------------
# O diálogo do sistema
# ---------------------------------------------------------------------------

#: O programinha que abre a janela. Roda num processo SEPARADO de propósito:
#: o tkinter não é feito para conviver com as threads do servidor web, e uma
#: janela presa derrubaria o programa inteiro. Separado, o pior caso é o
#: usuário fechar a janela — e o servidor nem fica sabendo.
_ABRIDOR = r"""
import sys
import tkinter as tk
from tkinter import filedialog

inicial = sys.argv[1] if len(sys.argv) > 1 else ""
titulo = sys.argv[2] if len(sys.argv) > 2 else "Escolher a pasta"

raiz = tk.Tk()
raiz.withdraw()
# Sem isto a janela nasce ATRAS do navegador, e quem clicou acha que o botao
# nao funcionou.
raiz.attributes("-topmost", True)
escolhida = filedialog.askdirectory(parent=raiz, title=titulo,
                                    initialdir=inicial or None)
raiz.destroy()
# Em bytes, e nao com print: um caminho com acento vira lixo quando o Windows
# decide a pagina de codigo do console por conta propria.
sys.stdout.buffer.write((escolhida or "").encode("utf-8"))
"""

#: Quanto tempo se espera pela janela. Generoso: a pessoa pode ir procurar a
#: pasta com calma, e este é um pedido que só existe porque ela pediu.
ESPERA = 600


def nativo(inicial: str | None = None, titulo: str = "") -> dict:
    """Abre o diálogo de pasta do sistema e devolve o que foi escolhido.

    `disponivel=False` quer dizer que a janela não abriu nesta máquina — e a
    tela então cai no navegador desenhado na página, sem avisar erro nenhum.
    """
    import subprocess
    import sys

    comando = [sys.executable, "-c", _ABRIDOR, str(inicial or ""),
               titulo or "Escolher a pasta"]
    try:
        feito = subprocess.run(
            comando, capture_output=True, timeout=ESPERA,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"disponivel": False, "caminho": "", "cancelado": False}
    if feito.returncode != 0:
        # Quase sempre é tkinter que não está instalado.
        return {"disponivel": False, "caminho": "", "cancelado": False}

    escolhida = feito.stdout.decode("utf-8", errors="replace").strip()
    return {"disponivel": True, "caminho": escolhida, "cancelado": not escolhida}
