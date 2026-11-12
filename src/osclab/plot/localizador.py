"""O painel «localizador de faltas»: as curvas dos métodos no tempo, e o relé.

Escolhido pelo Alexandre em 09/11/2026 entre as maquetes (a 11, «a 10
ajustada»): o painel mostra só as curvas de cada método ao longo do registro,
no MESMO eixo do tempo das ondas, com o número do relé tracejado. O número de
cada método vai na legenda; o resultado, no rodapé; a explicação de cada
método e a origem do número do relé, só no passar do mouse.

A conta é toda de `faultloc/ldl.py` — é o mesmo pacote da tela «localizar
falta», e por isso o mesmo número nas duas. Este módulo só ARRUMA o pacote
para o painel:

* **tudo em km E em % da linha.** A chave km/% é da tela, mas o número é
  daqui: o JavaScript não decide número nenhum. As curvas vão sempre em km;
  em %, o que muda são os RÓTULOS do eixo, posicionados no km que valem;
* **os dois cursores e a diferença entre eles**, como a tabelinha dos
  analógicos;
* **o relé**, com a origem: lido do arquivo (`faultloc/rele.py`) ou digitado.
  Digitado vence lido — é o caminho manual que o leitor universal exige ao
  lado de todo atalho.
"""

from __future__ import annotations

import math

from osclab.faultloc import rele as rele_mod
from osclab.plot import escala, navegacao

TIPO = "localizador"
NOME = "Localizador de faltas"
#: A ordem da legenda e da tabelinha: a mesma da tela «localizar falta».
ORDEM = ("seqneg", "laco", "takagi", "takagi_i2")
#: Quantos terminais cada método usa.
TERMINAIS = {"seqneg": 2, "laco": 1, "takagi": 1, "takagi_i2": 1}


def esqueleto(painel) -> dict:
    """O que a JANELA manda deste painel: só a identidade.

    Os números vêm da rota da localização, que já guarda as contas pesadas e
    já sabe dos outros registros da aba e da linha escolhida — refazer tudo
    isso a cada arrasto da janela seria pagar duas vezes pela mesma conta.
    """
    return {"id": painel.id, "tipo": TIPO, "nome": painel.nome or NOME,
            "do_padrao": painel.do_padrao}


def _ok(v) -> bool:
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def _pct(km, linha_km):
    return km / linha_km * 100.0 if _ok(km) and _ok(linha_km) and linha_km else None


def _par(km, linha_km) -> dict:
    return {"km": km if _ok(km) else None, "pct": _pct(km, linha_km)}


def _cursor(c: dict | None, linha_km) -> dict | None:
    if not c:
        return None
    return {"t": c["t"], "no_plato": c["no_plato"],
            "km": {m: (v if _ok(v) else None) for m, v in c["km"].items()},
            "pct": {m: _pct(v, linha_km) for m, v in c["km"].items()}}


def _diferenca(c1: dict | None, c2: dict | None) -> dict | None:
    if not c1 or not c2:
        return None
    sai = {"km": {}, "pct": {}}
    for unidade in ("km", "pct"):
        for m, a in c1[unidade].items():
            b = c2[unidade].get(m)
            sai[unidade][m] = b - a if _ok(a) and _ok(b) else None
    return sai


def rele_para_a_tela(lido, digitado, linha_km, resultado_km) -> dict | None:
    """O número do relé, com a origem. `lido` é um `faultloc.rele.DoRele`."""
    if _ok(digitado):
        km, origem = float(digitado), {"origem": "digitado", "campo": "", "arquivo": "",
                                        "unidade": "km", "presumido": False,
                                        "valor": float(digitado)}
    elif lido is not None:
        km = lido.km
        origem = {"origem": "lido", "campo": lido.campo, "arquivo": lido.arquivo,
                  "unidade": lido.unidade, "presumido": lido.presumido,
                  "valor": lido.valor}
    else:
        return None
    pct_do_rele = lido.percentual if (lido is not None and not _ok(digitado)) else None
    return {"km": km, "pct": _pct(km, linha_km),
            "pct_do_rele": pct_do_rele,
            "delta_km": km - resultado_km if _ok(resultado_km) else None,
            "delta_pct": (_pct(km, linha_km) - _pct(resultado_km, linha_km)
                          if _ok(resultado_km) and _ok(linha_km) else None),
            **origem}


def montar(pacote: dict, cursor1: dict | None, cursor2: dict | None,
           lido, digitado) -> dict:
    """O bloco `painel` que vai junto do pacote da localização."""
    linha_km = pacote.get("km_linha")
    res = pacote.get("resultado")
    metodos = {}
    for m in ORDEM:
        info = (pacote.get("metodos") or {}).get(m)
        if info is None:
            continue
        metodos[m] = {**_par(info.get("km"), linha_km), "terminais": TERMINAIS[m]}
    resultado = None
    if res:
        a, b = res["km"] - res["faixa"], res["km"] + res["faixa"]
        resultado = {"metodo": res["metodo"], **_par(res["km"], linha_km),
                     "patrulha_km": [a, b],
                     "patrulha_pct": [_pct(a, linha_km), _pct(b, linha_km)]}
    # O relé que tem o campo e escreveu «não medido»: sem número para a
    # linha tracejada, mas a tela diz que ele NÃO MEDIU em vez de calar —
    # é diferente de o arquivo não trazer distância nenhuma.
    sem_medida = None
    if isinstance(lido, rele_mod.NaoMediu):
        sem_medida = {"campo": lido.campo, "arquivo": lido.arquivo, "escrito": lido.escrito}
        lido = None
    rele = rele_para_a_tela(lido, digitado, linha_km, res["km"] if res else None)

    # A régua vertical. Em km, a da conta (`escala_ldl`); sem linha não há
    # curva, e a régua sai do relé, que pode existir sozinho.
    regua = pacote.get("escala_ldl")
    if regua is None and rele is not None:
        lo, hi = escala.faixa(0.0, abs(rele["km"]) * 1.6 or 1.0)
        regua = {"min": lo, "max": hi, "marcas": escala.marcacoes(lo, hi, 5)}
    marcas_pct = []
    if regua is not None and _ok(linha_km) and linha_km:
        lo = regua["min"] / linha_km * 100.0
        hi = regua["max"] / linha_km * 100.0
        marcas_pct = [{"rotulo": p, "km": p * linha_km / 100.0}
                      for p in escala.marcacoes(max(lo, 0.0), hi, 6)]
    c1, c2 = _cursor(cursor1, linha_km), _cursor(cursor2, linha_km)
    return {
        "linha_km": linha_km if _ok(linha_km) else None,
        "metodos": metodos,
        "resultado": resultado,
        "rele": rele,
        "rele_nao_mediu": sem_medida if rele is None else None,
        "regua": regua,
        "marcas_pct": marcas_pct,
        "cursor1": c1,
        "cursor2": c2,
        "diferenca": _diferenca(c1, c2),
    }


# ---------------------------------------------------------------------------
# O zoom do duplo clique: a REGIÃO DA FALTA (12/11/2026)
# ---------------------------------------------------------------------------

#: A folga em volta da falta, em ciclos, de cada lado. Dois ciclos antes
#: mostram a pré-falta contra a qual o início foi achado (a grandeza
#: incremental olha um ciclo atrás) e dois depois mostram a abertura
#: assentando — menos que isso corta o que se foi ver; mais, e numa falta
#: curta o zoom deixa de ser zoom.
FOLGA_DO_ZOOM = 4.0
#: E a folga cresce com a falta: um quarto da duração dela, se passar dos
#: quatro ciclos. «Uma folguinha do hachurado» de cada lado (12/11/2026) —
#: a janela justa da falta ao disjuntor ficou apertada demais para ele.
FOLGA_RELATIVA = 0.25
#: Sem fim conhecido (nem abertura, nem platô), quantos ciclos depois do
#: início se mostram.
SEM_FIM_EM_CICLOS = 10.0

#: Por que não há zoom, dito na tela (no `title` do desenho e na linha de
#: baixo dele, nunca por cima).
SEM_FALTA = "sem início de falta reconhecido no registro: não há região da falta para ampliar"


def janela_da_falta(eventos: dict | None, t0: float, t1: float, ciclo: float,
                    intervalo: float = 0.0, aviso: str = "") -> dict:
    """A janela que o DUPLO CLIQUE no localizador mostra: `{de, ate, motivo}`.

    Do início da falta até o FIM do trecho em que a curva mede
    (`eventos.assentado`: a abertura ou o fim da falta, o que vier antes),
    com folga dos dois lados: `FOLGA_DO_ZOOM` ciclos ou `FOLGA_RELATIVA` da
    duração, o que for maior — um pouco do hachurado aparece de cada lado. Começa no INÍCIO e não no platô de propósito: o
    platô é de onde sai a mediana e leva folga dos dois lados; quem amplia
    «para ver de perto a região da falta» quer ver a falta ENTRAR — o degrau,
    a DC, o ciclo que as curvas levam para assentar — e o disjuntor abrir.

    Sem platô também amplia (decidido em 12/11/2026): o fim é a abertura, e
    sem ela `SEM_FIM_EM_CICLOS` depois do início. Só sem início de falta não
    há zoom (`de`/`ate` = `None`, e o `motivo` diz por quê).

    Colada numa borda do registro, a janela é CORTADA na borda — não desliza
    para dentro: deslizar acrescentaria do outro lado um trecho que não é da
    falta, só para manter uma largura que ninguém pediu. O piso de amostras de
    `navegacao.limitar` continua valendo.
    """
    nada = {"de": None, "ate": None}
    if not eventos or eventos.get("inicio") is None:
        return {**nada, "motivo": aviso or SEM_FALTA}
    plato = eventos.get("plato")
    inicio = float(eventos["inicio"])
    assentado = eventos.get("assentado")
    if assentado:
        fim = float(assentado[1])
    elif plato:
        fim = float(plato[1])
    else:
        fim = inicio + SEM_FIM_EM_CICLOS * ciclo
    folga = max(FOLGA_DO_ZOOM * ciclo, FOLGA_RELATIVA * (fim - inicio))
    de, ate = max(inicio - folga, t0), min(fim + folga, t1)
    if not (math.isfinite(de) and math.isfinite(ate)) or ate <= de:
        return {**nada, "motivo": SEM_FALTA}
    de, ate = navegacao.limitar(t0, t1, de, ate, intervalo)
    return {"de": de, "ate": ate, "motivo": ""}
