"""Atalhos para montar painéis nos testes.

O servidor não tem mais "o grupo das correntes": tem a lista de painéis que a
tela mandou (ver `plot/paineis.py`). Sem estes atalhos, cada teste começaria
com seis linhas de montagem antes de chegar ao que ele de fato afirma — e o
que um teste afirma tem que caber no olho.

Dois deles existem por um motivo mais forte que comodidade:

* `valores` — a leitura do cursor passou a casar por **id do sinal**, não por
  posição. O dicionário guarda a ordem de inserção, que é a ordem do painel,
  então a lista continua sendo a ordem em que o teste pediu.
* `painel` — o pacote traz os painéis na ordem do arranjo, e o teste que fala
  de corrente quer o de ampères, não "o primeiro".
"""

from __future__ import annotations

from dataclasses import replace

from osclab.plot import paineis


def analogico(sinais, *, medida: str = "instantaneo", nome: str = "",
              identidade: str = "p1") -> paineis.Painel:
    """Um painel de ondas com os sinais pedidos, pelos ids do catálogo."""
    return paineis.Painel(id=identidade, tipo=paineis.ANALOGICO, nome=nome,
                          sinais=tuple(sinais), medida=medida)


def digital(indices, *, nome: str = "Digitais",
            identidade: str = "pd") -> paineis.Painel:
    """Um painel de tiras digitais, pelos índices dos canais de estado."""
    return paineis.Painel(id=identidade, tipo=paineis.DIGITAL, nome=nome,
                          sinais=tuple(str(k) for k in indices))


def ids_dos_canais(registro, unidade: str | None = None) -> list[str]:
    """Os ids de catálogo dos canais do IED, crus, na ordem do arquivo."""
    return [f"c{c.index}:instantaneo" for c in registro.analog_channels
            if unidade is None or c.unit.strip() == unidade]


def com_os_canais(registro, *, unidade: str | None = None,
                  medida: str = "instantaneo") -> list[paineis.Painel]:
    """Um arranjo de um painel só, com os canais do registro dentro."""
    return [analogico(ids_dos_canais(registro, unidade), medida=medida)]


def painel(pacote: dict, unidade: str = "A") -> dict:
    """O painel do pacote cuja unidade no arquivo é `unidade`."""
    return next(p for p in pacote["paineis"]
                if p.get("unidade_do_arquivo") == unidade)


def valores(pacote: dict) -> list[dict]:
    """As leituras de um cursor — ou do `entre` — na ordem em que foram pedidas."""
    return list(pacote["sinais"].values())


def padrao(registro, medidas: dict[str, str] | None = None,
           lado: str = "arquivo") -> list[paineis.Painel]:
    """O arranjo com que a oscilografia abre, com a medida de cada painel.

    Antes dos painéis, a medida chegava ao servidor como um dicionário por
    unidade do arquivo — `{"A": "rms"}` era "as correntes em eficaz". Hoje a
    medida é de cada painel, mas os testes que falam de "corrente em RMS e
    tensão em instantâneo" continuam querendo dizer a mesma coisa, então a
    tradução mora aqui: monta-se o arranjo padrão e troca-se a medida do
    painel cuja unidade foi pedida.
    """
    unidade_do_canal = {c.index: c.unit.strip() for c in registro.analog_channels}
    saida = []
    for item in paineis.padrao(registro, lado):
        if item.tipo != paineis.ANALOGICO or not item.sinais:
            saida.append(item)
            continue
        primeiro = int(item.sinais[0].split(":")[0][1:])
        medida = (medidas or {}).get(unidade_do_canal.get(primeiro, ""),
                                     "instantaneo")
        saida.append(replace(item, medida=medida))
    return saida
