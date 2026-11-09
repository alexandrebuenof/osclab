"""A distância da falta que o PRÓPRIO relé calculou e gravou.

É o tracejado do painel «localizador de faltas»: o número do relé ao lado das
curvas dos métodos do OscLab. Nenhum COMTRADE do banco o traz como canal —
levantado em 09/11/2026 em todos os `.cfg` do parque. É sempre UM número, num
arquivo de texto que acompanha a oscilografia:

    SEL .CEV (421, 451, 311C, 311L)   cabeçalho, campo "LOCATION"
    SEL-411L .CEV                     cabeçalho, "Z_BASED_LOCATION" ("305.08(SE)")
    SEL COMTRADE                      .HDR: "Location:  -12.76" / "Z-Based Location: 2.54(ME)"
    SEL-TWFL                          .HDR: L1_Fault_Location,"112.576(km)"
    SEL-321 (relatório em texto)      "Location:  +17.31"
    Schneider MiCOM P139/P437/P439    .hdr/.txt, Fault log: "FT_DA Fault location | 10.3 km"

Fora daqui, e por isso NÃO lidos: a GE grava num relatório à parte
(`FaultReport*.txt`, `FRP_*.txt`), o SIPROTEC deixa no DIGSI, e Ingeteam,
SEL-487E/787/751 não calculam. Para todos esses — e para qualquer relé que o
programa nunca viu — o número se DIGITA na tela: o leitor é atalho, nunca
condição (ver o CLAUDE.md, «O leitor é universal»).

**O `FLOC` do SEL-421 não serve.** É uma das grandezas ERAQ do `.CEV` e parece
a «variável do localizador», mas é constante no registro inteiro e traz a
distância da falta ANTERIOR (às vezes `3.4e38`, «nada calculado»). A falta do
próprio registro é a do `LOCATION`.

**A unidade quase nunca vem escrita.** A SEL usa a do ajuste `LL`, que é só um
número; o 411L e o TWFL às vezes colam `(mi)`/`(km)` no valor, e o ajuste
`LLUNIT` diz qual. Sem nada escrito, o número entra como km e a tela diz que a
unidade foi PRESUMIDA — milha lida como km erraria a distância em 60 %.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path

MILHA_KM = 1.609344

#: Os campos do cabeçalho do `.CEV`, na ordem de preferência. O 411L não tem
#: `LOCATION`; quem tem os dois fica com o baseado em impedância, que é o que
#: os métodos do OscLab também são.
CAMPOS_DO_CEV = ("Z_BASED_LOCATION", "LOCATION")

_NUMERO = r"([-+]?\d+(?:[.,]\d+)?)"
_VALOR = re.compile(rf"^\s*{_NUMERO}\s*(?:\(\s*(mi|km)\s*\))?", re.IGNORECASE)
_HDR_Z = re.compile(rf"Z-Based Location:\s*{_NUMERO}\s*(?:\(\s*(mi|km)\s*\))?", re.IGNORECASE)
_HDR = re.compile(rf"(?<![-\w])Location:\s*{_NUMERO}", re.IGNORECASE)
_TWFL = re.compile(rf'Fault_Location"?\s*,\s*"?{_NUMERO}\s*\(\s*(km|mi)\s*\)', re.IGNORECASE)
_MICOM_KM = re.compile(rf"Fault location\s*\|\s*{_NUMERO}\s*km", re.IGNORECASE)
_MICOM_PCT = re.compile(rf"Fault locat\.?\s*percent\s*\|\s*{_NUMERO}\s*%", re.IGNORECASE)
_LLUNIT = re.compile(r'LLUNIT"?\s*(?::?=|,)\s*"?\s*(KM|MI)\b', re.IGNORECASE)

_EXTENSOES = (".cev", ".hdr", ".txt")


@dataclass(frozen=True)
class DoRele:
    """O número do relé, como ele o escreveu, e de onde saiu."""

    #: O número escrito no arquivo, na unidade do relé.
    valor: float
    #: `"km"`, `"mi"` ou `None` quando o arquivo não diz.
    unidade: str | None
    #: O campo de onde saiu (`LOCATION`, `Z_BASED_LOCATION`, `FT_DA Fault location`).
    campo: str
    #: O arquivo de onde saiu.
    arquivo: str
    #: O % da linha, quando o relé também o grava (MiCOM).
    percentual: float | None = None

    @property
    def km(self) -> float:
        """Em km. Milha é convertida; sem unidade, o número é tomado como km."""
        return self.valor * MILHA_KM if self.unidade == "mi" else self.valor

    @property
    def presumido(self) -> bool:
        return self.unidade is None


def _numero(texto: str) -> float | None:
    try:
        return float(texto.replace(",", "."))
    except (TypeError, ValueError):
        return None


def _texto(caminho: Path) -> str:
    try:
        return caminho.read_bytes().decode("cp1252", errors="replace")
    except OSError:
        return ""


def do_cev(texto: str, arquivo: str = "") -> DoRele | None:
    """O campo do cabeçalho do `.CEV` (CSV com aspas): nomes numa linha, valores na seguinte."""
    linhas = texto.splitlines()[:12]
    for i, linha in enumerate(linhas[:-1]):
        if not any(f'"{c}"' in linha for c in CAMPOS_DO_CEV):
            continue
        try:
            nomes = next(csv.reader(io.StringIO(linha)))
            valores = next(csv.reader(io.StringIO(linhas[i + 1])))
        except (csv.Error, StopIteration):
            return None
        nomes = [n.strip().upper() for n in nomes]
        unidade_lida = _LLUNIT.search(texto)
        for campo in CAMPOS_DO_CEV:
            if campo not in nomes or nomes.index(campo) >= len(valores):
                continue
            m = _VALOR.match(valores[nomes.index(campo)].strip().strip('"'))
            valor = _numero(m.group(1)) if m else None
            if valor is None:
                continue
            escrita = m.group(2) or (unidade_lida.group(1) if unidade_lida else "")
            return DoRele(valor, escrita.lower() or None, campo, arquivo)
        return None
    # Um «.CEV» que é relatório em TEXTO (o do SEL-321) cai na leitura do .HDR.
    return do_texto(texto, arquivo)


def do_texto(texto: str, arquivo: str = "") -> DoRele | None:
    """`.HDR` e `.txt` que acompanham a oscilografia: SEL, TWFL e MiCOM."""
    unidade_lida = _LLUNIT.search(texto)
    lida = unidade_lida.group(1).lower() if unidade_lida else None
    m = _HDR_Z.search(texto)
    if m and _numero(m.group(1)) is not None:
        return DoRele(_numero(m.group(1)), (m.group(2) or lida or "").lower() or None,
                      "Z-Based Location", arquivo)
    m = _TWFL.search(texto)
    if m and _numero(m.group(1)) is not None:
        return DoRele(_numero(m.group(1)), m.group(2).lower(), "Fault_Location", arquivo)
    m = _MICOM_KM.search(texto)
    if m and _numero(m.group(1)) is not None:
        p = _MICOM_PCT.search(texto)
        return DoRele(_numero(m.group(1)), "km", "FT_DA Fault location", arquivo,
                      _numero(p.group(1)) if p else None)
    m = _HDR.search(texto)
    if m and _numero(m.group(1)) is not None:
        return DoRele(_numero(m.group(1)), lida, "Location", arquivo)
    return None


def do_registro(pasta: Path, arquivos) -> DoRele | None:
    """O número do relé neste registro, ou `None` quando nenhum arquivo o traz.

    `.cev` primeiro (é a própria oscilografia), depois `.hdr` e `.txt`.
    """
    for extensao in _EXTENSOES:
        for nome in sorted(arquivos or ()):
            if not str(nome).lower().endswith(extensao):
                continue
            texto = _texto(Path(pasta) / nome)
            if not texto:
                continue
            achado = do_cev(texto, nome) if extensao == ".cev" else do_texto(texto, nome)
            if achado is not None:
                return achado
    return None
