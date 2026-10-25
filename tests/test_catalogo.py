"""O catálogo de sinais: o que se pode acrescentar a um gráfico, e quanto vale.

O teste que mais importa aqui é o do **conferir a curva contra o cursor**. A
curva de uma componente simétrica sai de `envoltoria.calcular_fasores` (soma
móvel, o registro inteiro de uma vez) e o valor do cursor sai de
`fasor.no_instante` (uma janela só). São duas implementações da mesma
identidade — e duas implementações da mesma conta é exatamente como elas
divergem, em silêncio, meses depois.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from osclab.formats import fases, registry
from osclab.formats.base import AnalogChannel, Filtering, Record
from osclab.plot import catalogo, janela, leitura
from tests import arranjo
from tests.fabrica import escrever_comtrade

PICO = 100.0


def com_correntes(registro, acrescentados=(), medida="instantaneo"):
    """Um painel com as correntes do registro e mais os sinais pedidos.

    É o que a tela monta quando se aperta «+ sinal» num gráfico que abriu por
    padrão: os canais do IED continuam lá e o sinal novo entra no fim — o que
    é justamente o caso em que o segundo eixo e os avisos aparecem.
    """
    return [arranjo.analogico(
        arranjo.ids_dos_canais(registro, "A") + list(acrescentados),
        medida=medida, nome="Correntes")]


def sinal(painel, identidade):
    """O sinal de um painel pelo id com que foi pedido."""
    return next(s for s in painel["sinais"] if s["id"] == identidade)


def trifasico(defasagens=(0.0, -120.0, -240.0), amplitudes=(PICO, PICO, PICO),
              n=600, taxa=1200.0, freq=60.0) -> Record:
    """Três correntes e três tensões, com o ângulo e a amplitude que se pedir.

    As tensões ficam sempre equilibradas: elas existem para haver um SEGUNDO
    conjunto no registro, que é o que exercita o índice `q` e o segundo eixo.
    """
    t = np.arange(n) / taxa
    r = Record(source=Path("sintetico"), format_name="teste")
    r.line_frequency = freq
    nomes = [("Current IA", "A", 0), ("Current IB", "A", 1), ("Current IC", "A", 2),
             ("Voltage A-G", "V", 0), ("Voltage B-G", "V", 1), ("Voltage C-G", "V", 2)]
    r.analog_channels = tuple(
        AnalogChannel(index=i, name=nome, unit=unidade, phase="")
        for i, (nome, unidade, _) in enumerate(nomes)
    )
    linhas = []
    for _, unidade, k in nomes:
        if unidade == "A":
            amp, ang = amplitudes[k], defasagens[k]
        else:
            amp, ang = PICO, (0.0, -120.0, -240.0)[k]
        linhas.append(amp * np.sin(2 * np.pi * freq * t + math.radians(ang)))
    r.analog = np.vstack(linhas)
    r.time = t
    r.status = np.zeros((0, n), dtype=np.int8)
    return r


# ---------------------------------------------------------------------------
# O que o catálogo oferece
# ---------------------------------------------------------------------------

def test_o_canal_do_IED_carrega_a_fundamental_que_vinculamos():
    """O vínculo é a única coisa em que TODAS as contas se apoiam, e ele é
    deduzido de um nome que cada fabricante escreve como quer. Vínculo errado
    corrompe 3I0, V1 e a localização de falta **sem dar erro nenhum**.

    Ele NÃO é nome de sinal — nenhum sinal se chama `IA`. Vai no pacote porque
    é a conferência, que a tela mostra no hover do lápis de corrigir."""
    por_id = {s.id: s for s in catalogo.de_registro(trifasico())}
    canal = por_id["c0:instantaneo"]
    assert canal.nome == "Current IA"        # o nome do fabricante, e só ele
    assert canal.familia == "canal"
    assert canal.fundamental == "IA"         # a fase que deduzimos


def _com_canal_extra(nome: str, unidade: str, valores) -> Record:
    """O trifásico de sempre mais um canal que o programa não sabe batizar."""
    r = trifasico()
    canais = list(r.analog_channels)
    canais.append(AnalogChannel(index=6, name=nome, unit=unidade, phase=""))
    r.analog_channels = tuple(canais)
    r.analog = np.vstack([r.analog, valores.reshape(1, -1)])
    return r


def test_canal_FORA_DE_TRINCA_nao_ganha_conta_nossa():
    """A regra que define a lista do OscLab — e ela é estreita de propósito.

    Um relé grava muito mais que as três fases: a tensão de sincronismo, a de
    memória, a frequência que ele mediu, e as sequências que ele mesmo já
    calculou (`V1M`, `3V2M`, `LIGM`). Sobre esses, `RMS` e `60Hz` são contas
    que rodam, devolvem número, e não significam nada — filtrar em 60 Hz um
    número que JÁ é o módulo do fasor de 60 Hz é a mesma conta feita duas
    vezes, e o resultado tem cara de medida.

    O critério não é uma lista de nomes suspeitos: é ter entrado em trinca.
    Quem entrou é fase de alguma coisa, e sobre fase as contas do OscLab
    significam o que prometem.

    **O que se perde**: um canal alternado de verdade que ficou fora de trinca
    — um `IG` que o programa não conseguiu pendurar em lado nenhum — também
    fica sem eficaz e sem filtro. O canal continua inteiro na aba do IED,
    desenhável como sempre; o que ele não tem é conta nossa.
    """
    n = trifasico().analog.shape[1]
    onda = PICO * np.sin(2 * np.pi * 60.0 * np.arange(n) / 1200.0)
    r = _com_canal_extra("ENTRADA AUXILIAR", "V", onda)

    por_id = {s.id: s for s in catalogo.de_registro(r)}
    # Continua na aba do IED, e dizendo que não reconhecemos: ficar em branco é
    # a resposta certa — um palpite com cara de vínculo é pior que vínculo
    # nenhum.
    assert por_id["c6:instantaneo"].fundamental == ""
    # E não ganha nenhuma conta do OscLab.
    assert not {"v6:rms", "v6:filtrado", "v6:fundamental"} & set(por_id)


def test_canal_CONTINUO_nao_ganha_as_contas_de_alternada():
    """`VDC1 RMS` e `VDC1 60Hz` eram oferecidos e não significavam nada: a
    componente de 60 Hz de 125 V contínuos é zero."""
    n = trifasico().analog.shape[1]
    r = _com_canal_extra("VDC1", "V", np.full(n, 125.0))

    ids = {s.id for s in catalogo.de_registro(r)}
    assert "c6:instantaneo" in ids
    assert not {"v6:rms", "v6:filtrado", "v6:fundamental"} & ids


def test_a_lista_do_OscLab_nao_repete_o_canal():
    """`IA` não está lá: são as mesmas amostras do canal, e o vínculo já
    aparece do lado do IED. O que o OscLab oferece é o que o relé NÃO gravou."""
    por_id = {s.id: s for s in catalogo.de_registro(trifasico())}
    nossos = {s.nome for s in por_id.values() if s.familia == "calculado"}
    assert "Current IA" not in nossos
    assert {"Current IA · RMS", "Current IA · 60Hz", "Current IA · 60Hz RMS"} <= nossos


def test_a_grandeza_esta_no_id_e_o_NOME_acompanha_o_botao_de_filtro():
    """Cada variante é um sinal próprio, com id e nome próprios — e o nome que
    a tela escreve é o do sinal DESENHADO. Com o filtro aceso, `IA RMS` desenha
    a fundamental, e a legenda diz `60Hz RMS`: o significado não muda calado.
    Ver `catalogo.efetivo`."""
    por_id = {s.id: s for s in catalogo.de_registro(trifasico())}
    assert por_id["v0:rms"].nome == "Current IA · RMS"
    assert por_id["v0:filtrado"].nome == "Current IA · 60Hz"
    assert por_id["v0:fundamental"].nome == "Current IA · 60Hz RMS"

    r = trifasico()
    aceso = janela.montar(r, filtro=True, colunas=100_000,
                          layout=com_correntes(r, ["v0:rms"]))
    assert sinal(aceso["paineis"][0], "v0:rms")["sinal"] == \
        "Current IA · 60Hz RMS"
    apagado = janela.montar(r, filtro=False, colunas=100_000,
                            layout=com_correntes(r, ["v0:rms"]))
    assert sinal(apagado["paineis"][0], "v0:rms")["sinal"] == "Current IA · RMS"


def test_registro_ja_filtrado_oferece_UMA_conta_so():
    """Num `.CEV`, e em qualquer registro que o relé gravou filtrado, as
    amostras JÁ são a componente de 60 Hz. Sobra uma conta a oferecer: o eficaz
    da janela de um ciclo.

    As duas variantes `60Hz` saíram daqui. A primeira, `IA 60Hz`, não
    calculava nada — era o próprio canal com outro nome, e numa tela que já diz
    «gravação filtrada pelo relé» no cabeçalho ela se lê como filtrar duas
    vezes. A segunda, `IA 60Hz RMS`, existia pelo argumento de que `IA RMS` —
    eficaz COM harmônicos — não existe ali; o argumento vale ao contrário, já
    que o que está no arquivo não tem harmônico nenhum.
    """
    r = trifasico()
    r.filtering = Filtering.FILTRADO
    por_id = {s.id: s for s in catalogo.de_registro(r)}
    assert por_id["v0:rms"].nome == "Current IA · RMS"
    assert not {"v0:filtrado", "v0:fundamental"} & set(por_id)


def test_num_registro_filtrado_o_botao_do_filtro_nao_muda_nada():
    """Se o filtro fosse aplicado de novo, a curva começaria um ciclo depois e
    ficaria atrasada em relação à onda do próprio gráfico — e o cursor leria o
    valor de um ciclo atrás. O botão aparece aceso e preso, porque é o estado
    do sinal; o servidor não filtra."""
    r = trifasico()
    r.filtering = Filtering.FILTRADO
    pacote = janela.montar(r, filtro=True, colunas=100_000,
                           layout=com_correntes(r, medida="rms"))
    painel = pacote["paineis"][0]
    assert pacote["filtro"] is False
    # Com a medida em eficaz, o canal do IED responde pelo `v:rms` — e o nome
    # não ganha sufixo de uma conta que não houve.
    assert painel["sinais"][0]["sinal"] == "Current IA · RMS"
    assert painel["sinais"][0]["id_efetivo"] == "v0:rms"


def test_o_que_os_botoes_do_painel_pegam_e_o_que_eles_nao_pegam():
    """A divisão que decide o significado de metade da tela.

    O FILTRO é do registro inteiro e pega em tudo que tem par no grupo
    filtrado — inclusive no sinal escolhido à mão. Já foi diferente: `IA RMS`
    ficava bruto com o filtro aceso, e o gráfico punha um eficaz COM
    harmônicos ao lado de ondas filtradas, sem nada na tela denunciando.
    Pedido do usuário (out/2026): "quando eu aplico o filtro, as variáveis que
    já estão no gráfico também atualizam".

    O que protege o significado é o nome: a legenda escreve `60Hz RMS`.
    """
    r = trifasico()
    r.filtering = Filtering.BRUTO        # senão `IA RMS` nem seria oferecido
    pacote = janela.montar(r, filtro=True, colunas=100_000,
                           layout=[arranjo.analogico(["c0:instantaneo",
                                                      "v0:rms"])])
    painel = pacote["paineis"][0]

    do_ied = sinal(painel, "c0:instantaneo")
    assert do_ied["sinal"] == "Current IA · 60Hz"          # o botão pegou
    assert do_ied["serie"][0] is None            # e a janela do filtro aparece

    escolhido = sinal(painel, "v0:rms")
    assert escolhido["sinal"] == "Current IA · 60Hz RMS"   # pegou também
    assert escolhido["id_efetivo"] == "v0:fundamental"


def test_o_filtro_so_empurra_o_que_tem_par_no_grupo_filtrado():
    disponiveis = catalogo.por_id(trifasico())
    empurra = {"c0:instantaneo": "v0:filtrado", "v0:rms": "v0:fundamental",
               # sem par: a DC do filtrado é zero por definição; a
               # componente já é fasor de 60 Hz
               "v0:dc": "v0:dc", "q0:n:dc": "q0:n:dc", "q0:0:rms": "q0:0:rms",
               # o resíduo é onda, e tem par como um canal
               "q0:n:instantaneo": "q0:n:filtrado",
               "q0:n:rms": "q0:n:fundamental",
               # já filtrados
               "v0:filtrado": "v0:filtrado",
               "v0:fundamental": "v0:fundamental"}
    for pedido, desenhado in empurra.items():
        assert catalogo.efetivo(pedido, "instantaneo", True,
                                disponiveis).id == desenhado, pedido


def test_apagar_o_filtro_nao_empurra_ninguem_de_volta():
    """É com o filtro apagado que se compara o filtro com o cru: `IAW` e
    `IAW · 60Hz` lado a lado. Se apagar o filtro arrastasse o filtrado para o
    bruto, as duas curvas virariam uma."""
    disponiveis = catalogo.por_id(trifasico())
    for pedido in ("v0:filtrado", "v0:fundamental", "v0:rms", "v0:dc"):
        assert catalogo.efetivo(pedido, "instantaneo", False,
                                disponiveis).id == pedido


def test_a_medida_do_painel_continua_pegando_so_no_canal():
    disponiveis = catalogo.por_id(trifasico())
    assert catalogo.efetivo("c0:instantaneo", "rms", False,
                            disponiveis).id == "v0:rms"
    assert catalogo.efetivo("v0:dc", "rms", False, disponiveis).id == "v0:dc"


def test_o_catalogo_diz_o_que_cada_sinal_vira_com_o_filtro():
    """A lista marca a caixinha na coluna em que o sinal ESTÁ, e escreve o
    nome que a legenda escreve. A conta vem do servidor: repeti-la no
    JavaScript seria a mesma regra em dois lugares."""
    r = trifasico()
    r.filtering = Filtering.BRUTO
    aceso = {x["id"]: x["efetivo"] for x in
             janela.montar(r, filtro=True, colunas=1000)["catalogo"]}
    assert aceso["c0:instantaneo"] == {"instantaneo": "v0:filtrado",
                                       "rms": "v0:fundamental"}
    assert aceso["v0:rms"]["instantaneo"] == "v0:fundamental"
    assert aceso["v0:dc"]["instantaneo"] == "v0:dc"
    apagado = {x["id"]: x["efetivo"] for x in
               janela.montar(r, filtro=False, colunas=1000)["catalogo"]}
    assert apagado["v0:filtrado"]["instantaneo"] == "v0:filtrado"
    assert apagado["c0:instantaneo"]["instantaneo"] == "c0:instantaneo"


def test_dois_pedidos_no_mesmo_traco_sao_desenhados_uma_vez_so():
    """Com o filtro aceso, `IAW` e `IAW · 60Hz` são a mesma curva. Desenhar as
    duas dava dois traços sobrepostos, com duas cores e duas entradas na
    legenda — foi o que apareceu na tela do usuário."""
    r = trifasico()
    r.filtering = Filtering.BRUTO
    layout = [arranjo.analogico(["c0:instantaneo", "v0:filtrado"])]
    aceso = janela.montar(r, filtro=True, colunas=1000, layout=layout)
    assert [s["id_efetivo"] for s in aceso["paineis"][0]["sinais"]] == \
        ["v0:filtrado"]
    apagado = janela.montar(r, filtro=False, colunas=1000, layout=layout)
    assert len(apagado["paineis"][0]["sinais"]) == 2


def test_cada_conjunto_trifasico_rende_as_tres_componentes():
    componentes = {s.id: s.nome for s in catalogo.de_registro(trifasico())
                   if s.id.startswith("q") and ":n:" not in s.id}
    assert componentes == {"q0:0:rms": "3I0 G1", "q0:1:rms": "I1 G1",
                           "q0:2:rms": "I2 G1", "q1:0:rms": "3V0 G2",
                           "q1:1:rms": "V1 G2", "q1:2:rms": "V2 G2"}


def test_cada_conjunto_trifasico_rende_tambem_o_residuo():
    """`IN` e `VN` saem da MESMA trinca das componentes, e por isso levam o
    mesmo nome de grupo. A diferença está na conta: soma no tempo, não
    Fortescue."""
    residuos = {s.id: s.nome for s in catalogo.de_registro(trifasico())
                if ":n:" in s.id}
    assert residuos == {"q0:n:instantaneo": "IN G1", "q0:n:rms": "IN G1 · RMS",
                        "q0:n:dc": "IN G1 · DC",
                        "q0:n:filtrado": "IN G1 · 60Hz",
                        "q0:n:fundamental": "IN G1 · 60Hz RMS",
                        "q1:n:instantaneo": "VN G2", "q1:n:rms": "VN G2 · RMS",
                        "q1:n:dc": "VN G2 · DC",
                        "q1:n:filtrado": "VN G2 · 60Hz",
                        "q1:n:fundamental": "VN G2 · 60Hz RMS"}


def test_registro_ja_filtrado_oferece_o_eficaz_do_residuo_PELA_DFT():
    """Num `.CEV` o eficaz do resíduo existe (pedido do usuário, out/2026: a
    linha `IN G1` com as mesmas colunas dos canais), mas sai pela DFT e não
    pela conta `rms` dos canais.

    O motivo foi medido no `.CEV` do alimentador: o eficaz verdadeiro sobre
    amostras que já são a saída do filtro do relé se descola do `3I0` em até
    84 % nas bordas da falta — resposta transitória de dois estimadores
    diferentes sobre o mesmo degrau, e uma cadeia de medição que nenhum relé
    tem. Pela DFT ele é o `3I0` amostra por amostra, bordas incluídas.
    """
    r = trifasico(amplitudes=(3 * PICO, PICO, PICO))
    r.filtering = Filtering.FILTRADO
    r.analog = r.analog.copy()
    r.analog[:, :250] = 0.0                  # uma borda: a falta começa aqui
    por_id = {s.id: s for s in catalogo.de_registro(r)}
    assert por_id["q0:n:rms"].conta == "fundamental"
    assert por_id["q0:n:rms"].coluna == "filtrado.rms"
    assert por_id["q0:n:instantaneo"].coluna == "filtrado.onda"
    # sem as variantes `60Hz`: as amostras já SÃO a de 60 Hz
    assert not {"q0:n:filtrado", "q0:n:fundamental"} & set(por_id)

    pacote = janela.montar(r, colunas=100_000,
                           layout=[arranjo.analogico(["q0:n:rms", "q0:0:rms"])])
    residuo = sinal(pacote["paineis"][0], "q0:n:rms")["serie"]
    zero = sinal(pacote["paineis"][0], "q0:0:rms")["serie"]
    pares = [(a, b) for a, b in zip(residuo, zero) if a is not None]
    assert len(pares) > 300
    for a, b in pares:
        assert abs(a - b) <= 1e-6 * max(1.0, abs(b))


def test_IN_60Hz_RMS_e_o_3I0_amostra_por_amostra():
    """A DFT é linear: o fasor de `ia+ib+ic` é a soma dos três fasores, que é
    `3I0`. Então `IN · 60Hz RMS` e `3I0` têm que dar o MESMO número em toda
    amostra — mesmo com DC e harmônico, que separam o `IN · RMS` deles. Se
    divergirem, é erro de conta, não grandeza diferente.

    Os dois existem no catálogo de propósito (pedido do usuário, out/2026):
    a linha `IN G1` ganha as mesmas colunas de um canal, e o `3I0` fica com o
    nome do ofício. Ver o cabeçalho de `plot/catalogo.py`."""
    r = trifasico(amplitudes=(3 * PICO, PICO, PICO))
    r.analog = r.analog.copy()
    r.analog[0] += 40.0                                       # DC
    r.analog[1] += 0.3 * PICO * np.sin(2 * np.pi * 180 * r.time)  # 3º harmônico
    layout = [arranjo.analogico(["q0:n:fundamental", "q0:0:rms"])]
    painel = janela.montar(r, colunas=100_000, layout=layout)["paineis"][0]
    a = sinal(painel, "q0:n:fundamental")["serie"]
    b = sinal(painel, "q0:0:rms")["serie"]
    pares = [(x, y) for x, y in zip(a, b) if x is not None]
    assert len(pares) > 400
    for x, y in pares:
        assert abs(x - y) <= 1e-6 * max(1.0, abs(y))

    i = 450
    lido = leitura.em(r, [(float(r.time[i]), 0, 0.0), (None, 0, 0.0)],
                      layout=[arranjo.analogico(["q0:n:fundamental",
                                                 "q0:n:filtrado", "q0:0:rms"])])
    v = lido["cursores"][0]["sinais"]
    assert v["q0:n:fundamental"]["valor"] == pytest_aprox(v["q0:0:rms"]["valor"],
                                                         rel=1e-6)
    # a onda filtrada lê o valor filtrado, não a amostra crua
    assert v["q0:n:filtrado"]["valor"] == v["q0:n:filtrado"]["filtrado"]


def test_o_residuo_leva_o_lapis_da_trinca():
    """Ele sai de três canais que o programa ESCOLHEU olhando nomes — o mesmo
    palpite das componentes, e portanto o mesmo editor. Sem isso, corrigir a
    trinca arrumaria o 3I0 e deixaria o IN errado na mesma tela."""
    por_id = {s.id: s for s in catalogo.de_registro(trifasico())}
    assert por_id["q0:n:instantaneo"].conjunto == por_id["q0:0:rms"].conjunto
    assert por_id["q0:n:instantaneo"].conjunto["canais"] == {"A": 0, "B": 1,
                                                             "C": 2}


def test_sem_conjunto_completo_nao_ha_componente_nenhuma():
    """Sem A, B e C não há transformação de Fortescue — há chute. O catálogo
    simplesmente não oferece, em vez de oferecer e devolver NaN."""
    r = trifasico()
    # Só duas correntes: some a fase C, e com ela o conjunto de correntes.
    r.analog_channels = tuple(
        AnalogChannel(index=i, name=c.name, unit=c.unit, phase="")
        for i, c in enumerate([r.analog_channels[0], r.analog_channels[1],
                               *r.analog_channels[3:]])
    )
    r.analog = np.vstack([r.analog[:2], r.analog[3:]])

    componentes = [s.nome for s in catalogo.de_registro(r) if s.id.startswith("q")]
    # Sem a trinca de correntes, a de tensões passa a ser o primeiro grupo.
    assert not any(x.startswith("3I0") for x in componentes)
    assert "3V0 G1" in componentes    # as tensões continuam completas


# ---------------------------------------------------------------------------
# Quanto vale cada componente
# ---------------------------------------------------------------------------

def test_equilibrado_em_abc_poe_tudo_na_positiva():
    """Sistema equilibrado: I1 é o próprio valor de fase, I2 e 3I0 são zero.
    Se este teste inverter, a fábrica está gerando ACB — foi o que aconteceu, e
    custou um registro inteiro lido de cabeça para baixo."""
    r = trifasico()
    lido = leitura.em(r, [(float(r.time[300]), 0, 0.0), (None, 0, 0.0)],
                      layout=[arranjo.analogico(
                          ["q0:0:rms", "q0:1:rms", "q0:2:rms"])])
    valores = {k: v["valor"] for k, v in lido["cursores"][0]["sinais"].items()}
    assert valores["q0:1:rms"] == pytest_aprox(PICO / math.sqrt(2.0))
    assert abs(valores["q0:2:rms"]) < 0.01
    assert abs(valores["q0:0:rms"]) < 0.01


def test_falta_fase_terra_levanta_o_3i0():
    """Fase A em falta: o resíduo aparece, e é ele que a proteção de terra vê.
    Com as três fases iguais o 3I0 é zero por construção; qualquer valor que
    aparecesse ali seria erro de conta."""
    r = trifasico(amplitudes=(10 * PICO, PICO, PICO))
    lido = leitura.em(r, [(float(r.time[300]), 0, 0.0), (None, 0, 0.0)],
                      layout=[arranjo.analogico(["q0:0:rms"])])
    tres_i0 = lido["cursores"][0]["sinais"]["q0:0:rms"]["valor"]
    # 3I0 = Ia+Ib+Ic; com Ib e Ic equilibrados eles se cancelam e sobra o
    # excesso da fase A: (10-1)·PICO, em eficaz.
    assert tres_i0 == pytest_aprox(9 * PICO / math.sqrt(2.0), rel=1e-3)


def test_a_curva_e_o_cursor_dao_o_MESMO_numero():
    """A curva vem da soma móvel sobre o registro inteiro; o cursor, de uma
    janela só. Duas implementações da mesma identidade — e é assim que elas
    divergem, em silêncio, meses depois."""
    r = trifasico(amplitudes=(3 * PICO, PICO, PICO))
    i = 400
    pacote = janela.montar(r, colunas=100_000,
                           layout=com_correntes(r, ["q0:0:rms"]))
    desenhado = sinal(pacote["paineis"][0], "q0:0:rms")["serie"][i]

    lido = leitura.em(r, [(float(r.time[i]), 0, 0.0), (None, 0, 0.0)],
                      layout=com_correntes(r, ["q0:0:rms"]))
    # A tolerância é a do ARREDONDAMENTO do desenho, não da conta: a série sai
    # arredondada na resolução do eixo (ver `serie.arredondar`), porque mandar
    # dezesseis dígitos para desenhar um pixel é peso de rede por nada.
    assert abs(desenhado
               - lido["cursores"][0]["sinais"]["q0:0:rms"]["valor"]) < 0.02


def test_o_primeiro_ciclo_nao_tem_componente():
    """Não há janela antes dele. Zero seria um número, e número na tela é
    afirmação — diria "medi, e deu zero" onde não há o que medir."""
    r = trifasico()
    pacote = janela.montar(r, colunas=100_000,
                           layout=com_correntes(r, ["q0:1:rms"]))
    assert sinal(pacote["paineis"][0], "q0:1:rms")["serie"][0] is None


# ---------------------------------------------------------------------------
# Os dois eixos
# ---------------------------------------------------------------------------

def test_sinal_de_outra_unidade_vai_para_o_eixo_da_direita():
    """100 A e 100 V na mesma altura seria leitura errada que não dá erro
    nenhum. Unidade diferente, eixo diferente — e a tela escreve os dois."""
    r = trifasico()
    pacote = janela.montar(r, colunas=200,
                           layout=com_correntes(r, ["c3:instantaneo"]))
    painel = pacote["paineis"][0]
    assert sinal(painel, "c3:instantaneo")["eixo"] == "dir"
    assert painel["eixo_dir"]["unidade"] == "V"
    assert painel["eixo_dir"]["marcacoes"]


def test_mesma_unidade_divide_o_eixo_da_esquerda():
    r = trifasico()
    pacote = janela.montar(r, colunas=200, layout=com_correntes(r, ["q0:1:rms"]))
    painel = pacote["paineis"][0]
    assert sinal(painel, "q0:1:rms")["eixo"] == "esq"
    assert painel["eixo_dir"] is None


def test_uma_terceira_unidade_e_recusada_com_aviso():
    """A tela tem dois lados. O terceiro sinal seria desenhado numa escala que
    não está escrita em lugar nenhum — e o usuário leria a altura dele."""
    r = trifasico()
    canais = list(r.analog_channels)
    canais.append(AnalogChannel(index=6, name="Freq", unit="Hz", phase=""))
    r.analog_channels = tuple(canais)
    r.analog = np.vstack([r.analog, np.full((1, r.analog.shape[1]), 60.0)])

    pacote = janela.montar(r, colunas=200, layout=com_correntes(
        r, ["c3:instantaneo", "c6:instantaneo"]))
    painel = pacote["paineis"][0]
    # As três correntes e a tensão entraram; o hertz ficou de fora, com aviso.
    assert [s["id"] for s in painel["sinais"]][-1] == "c3:instantaneo"
    assert painel["avisos"] and "Hz" in painel["avisos"][0]


def test_id_que_nao_existe_e_ignorado_em_silencio():
    pacote = janela.montar(trifasico(), colunas=200, layout=[
        arranjo.analogico(["v99:rms", "q7:1:rms", "lixo"])])
    assert pacote["paineis"][0]["sinais"] == []


# ---------------------------------------------------------------------------
# A tabelinha
# ---------------------------------------------------------------------------

def test_o_sinal_acrescentado_carrega_a_propria_medida(tmp_path):
    """O botão do gráfico manda nos canais que abriram por padrão; o que foi
    acrescentado à mão fica como foi pedido. É o que permite `IA` e `IA RMS` na
    mesma tela."""
    r = registry.read(escrever_comtrade(tmp_path, na=3, n=512, taxa=1200.0))
    # A senoide da fábrica é pura, e pelo critério do detector isso é um sinal
    # já filtrado — onde `IA RMS` nem é oferecido. Este teste é sobre um
    # registro bruto, então ele diz isso.
    r.filtering = Filtering.BRUTO
    lido = leitura.em(r, [(float(r.time[300]), 0, 0.0), (None, 0, 0.0)],
                      layout=com_correntes(r, ["v0:rms"]))
    leituras = lido["cursores"][0]["sinais"]
    linha = leituras["v0:rms"]
    # O gráfico está em instantâneo; o sinal acrescentado continua em RMS.
    assert linha["valor"] == linha["rms"]
    assert leituras["c0:instantaneo"]["grandeza"] == "instantaneo"


def test_a_diferenca_entre_cursores_vale_para_os_acrescentados():
    r = trifasico(amplitudes=(3 * PICO, PICO, PICO))
    lido = leitura.em(r, [(float(r.time[200]), 0, 0.0), (float(r.time[400]), 0, 0.0)],
                      layout=com_correntes(r, ["q0:0:rms"]))
    assert "q0:0:rms" in lido["entre"]["sinais"]


def pytest_aprox(v, rel=1e-6):
    """Comparação com tolerância, sem depender do `approx` do pytest aqui."""
    class Perto:
        def __eq__(self, outro):
            return outro is not None and math.isclose(float(outro), float(v),
                                                      rel_tol=rel, abs_tol=1e-9)

        def __repr__(self):
            return f"≈{v}"
    return Perto()


# ---------------------------------------------------------------------------
# O vínculo corrigido pelo usuário
# ---------------------------------------------------------------------------

def test_a_escolha_do_usuario_vence_a_deducao():
    """Quem corrigiu olhou o arquivo e o unifilar; a nossa expressão regular
    olhou um nome que cada fabricante escreve como quer."""
    from dataclasses import replace as _replace

    r = trifasico()
    canal = _replace(r.analog_channels[0], phase_escolhida="C")
    assert fases.da_canal(canal) == ("C", fases.OrigemDaFase.ESCOLHIDA)
    assert fases.padrao(canal) == "IC"


def test_escolher_NENHUMA_e_diferente_de_nao_ter_mexido():
    """`-` é o usuário dizendo "este canal não é fase nenhuma", e por isso não
    pode cair de volta na dedução pelo nome. Vazio é "não mexeram"."""
    from dataclasses import replace as _replace

    r = trifasico()
    apagado = _replace(r.analog_channels[0], phase_escolhida="-")
    assert fases.da_canal(apagado) == ("", fases.OrigemDaFase.ESCOLHIDA)
    intocado = _replace(r.analog_channels[0], phase_escolhida="")
    assert fases.da_canal(intocado)[1] == fases.OrigemDaFase.DEDUZIDA


def test_o_vinculo_corrigido_chega_ao_catalogo_com_a_origem():
    """A tela precisa dizer "você corrigiu" em vez de "deduzi" — e a diferença
    entre as duas é o que separa um fato de um palpite num laudo."""
    from dataclasses import replace as _replace

    r = trifasico()
    r.analog_channels = tuple(
        _replace(c, phase_escolhida="C") if c.index == 0 else c
        for c in r.analog_channels
    )
    por_id = {s.id: s for s in catalogo.de_registro(r)}
    assert por_id["c0:instantaneo"].fundamental == "IC"
    assert por_id["c0:instantaneo"].fundamental_origem == "escolhida"
    assert por_id["c0:instantaneo"].canal == 0


def test_a_correcao_muda_TUDO_que_vem_depois():
    """O vínculo decide o conjunto trifásico, e o conjunto decide as
    componentes. Corrigir a fase e as componentes continuarem iguais seria a
    correção não ter servido para nada."""
    from dataclasses import replace as _replace

    r = trifasico()
    # As três correntes viram fase A: não sobra conjunto trifásico nenhum.
    r.analog_channels = tuple(
        _replace(c, phase_escolhida="A") if c.index in (0, 1, 2) else c
        for c in r.analog_channels
    )
    componentes = [s.nome for s in catalogo.de_registro(r) if s.id.startswith("q")]
    assert not any(x.startswith("3I0") for x in componentes)
    assert "3V0 G1" in componentes


def test_a_letra_do_neutro_sozinha_e_reconhecida():
    """`Voltage N-G` não casa com a regra do residual (que espera o `V` colado,
    como em `VNG`) e ficava sem fase — um canal de tensão residual fora de toda
    conta. E `Voltage A-G` continua sendo fase A."""
    assert fases.deduzir("Voltage N-G") == "N"
    assert fases.deduzir("Voltage A-G") == "A"


# ---------------------------------------------------------------------------
# O botão de medida de cada painel
# ---------------------------------------------------------------------------

def test_o_botao_de_medida_trava_onde_nao_ha_canal_do_IED():
    """Botão que acende e não faz nada é pior que botão travado.

    Num painel só de componentes simétricas o instantâneo/RMS não tem em que
    pegar: elas são fasor e já saem em eficaz. Clicar nele trocava o rótulo da
    tabelinha de `valor` para `RMS` e deixava os valores iguais — a tela
    afirmando uma mudança que não houve.
    """
    r = trifasico()
    so_componentes = janela.montar(r, colunas=200, layout=[
        arranjo.analogico(["q0:0:rms", "q0:1:rms", "q0:2:rms"])])
    assert so_componentes["paineis"][0]["medida_aplicavel"] is False

    # Basta UM canal do IED no gráfico para o botão voltar a mandar em algo.
    com_canal = janela.montar(r, colunas=200, layout=[
        arranjo.analogico(["q0:1:rms", "c0:instantaneo"])])
    assert com_canal["paineis"][0]["medida_aplicavel"] is True


def test_painel_vazio_nao_trava_a_medida():
    """Ali ainda não há contradição nenhuma: travar um controle antes de haver
    conteúdo é dizer "não pode" sem ter por quê."""
    pacote = janela.montar(trifasico(), colunas=200,
                           layout=[arranjo.analogico([])])
    assert pacote["paineis"][0]["medida_aplicavel"] is True


def test_o_sinal_do_OscLab_nao_se_faz_passar_pelo_canal_do_arquivo():
    """`IA RMS` não é `Current IA`: é conta nossa, com um ciclo de janela em
    cima. O pacote precisa deixar a tela distinguir os dois — é pelo `familia`
    que ela decide se escreve o nome do arquivo ao lado."""
    r = trifasico()
    pacote = janela.montar(r, colunas=200,
                           layout=[arranjo.analogico(["c0:instantaneo"],
                                                     medida="rms")])
    linha = pacote["paineis"][0]["sinais"][0]
    assert linha["sinal"] == "Current IA · RMS"
    assert linha["familia"] == "calculado"      # a tela some com o nome do arquivo
    # E o canal de origem continua no pacote, para o hover e para o aviso de
    # TC/TP: quem confere precisa saber de onde a conta saiu.
    assert linha["nome"] == "Current IA"
    assert linha["indice"] == 0

    cru = janela.montar(r, colunas=200,
                        layout=[arranjo.analogico(["c0:instantaneo"])])
    assert cru["paineis"][0]["sinais"][0]["familia"] == "canal"


# ---------------------------------------------------------------------------
# O nome, e o desenho do nome
# ---------------------------------------------------------------------------

def test_o_nome_e_UM_SO_e_sai_inteiro():
    """Houve uma versão em que o nome vinha partido em três — `("IAW ·",
    "60Hz", "RMS")` — para a tela poder desenhar a frequência em subscrito.
    Saiu: `IAW ·60Hz`, com o ponto colado no subscrito, lia pior que
    `IAW · 60Hz`, e o nome passava a existir em duas formas, com um teste só
    para garantir que as duas diziam a mesma coisa.

    Uma forma só é mais barata que duas formas conferidas.
    """
    for s in catalogo.de_registro(trifasico()):
        assert not hasattr(s, "partes")
        assert s.nome and s.nome == s.nome.strip()

    por_id = {s.id: s for s in catalogo.de_registro(trifasico())}
    assert por_id["c0:instantaneo"].nome == "Current IA"
    assert por_id["v0:rms"].nome == "Current IA · RMS"
    assert por_id["v0:filtrado"].nome == "Current IA · 60Hz"
    assert por_id["v0:fundamental"].nome == "Current IA · 60Hz RMS"
    # Componente simétrica já É a fundamental: não leva sufixo de frequência.
    # O `G1` no fim é o grupo trifásico de onde ela saiu.
    assert por_id["q0:1:rms"].nome == "I1 G1"


def test_num_registro_de_50_Hz_o_nome_diz_50():
    """O `60` sai da frequência NOMINAL DO REGISTRO. Escrever `60` num arquivo
    de 50 Hz seria um nome errado que nada na tela denunciaria."""
    por_id = {s.id: s for s in catalogo.de_registro(trifasico(freq=50.0))}
    assert por_id["v0:fundamental"].nome == "Current IA · 50Hz RMS"




# ---------------------------------------------------------------------------
# O resíduo no tempo: `IN`, `VN`
# ---------------------------------------------------------------------------

def test_o_residuo_e_a_soma_das_tres_fases_amostra_a_amostra():
    """Sem janela, sem filtro, sem fasor: `ia+ib+ic` na própria amostra.

    É a definição inteira, e é por ela que o resíduo enxerga o que o `3I0` não
    enxerga. Qualquer janela que entrasse aqui — nem que fosse de um ciclo —
    faria dele uma segunda cópia do `3I0` com outro nome.
    """
    r = trifasico(amplitudes=(3 * PICO, PICO, PICO))
    pacote = janela.montar(r, colunas=100_000,
                           layout=com_correntes(r, ["q0:n:instantaneo"]))
    desenhado = sinal(pacote["paineis"][0], "q0:n:instantaneo")["serie"]
    esperado = r.analog[0] + r.analog[1] + r.analog[2]
    # A tolerância é o arredondamento do pacote, não da conta: o que vai para
    # o navegador é arredondado para desenhar, e comparar com 1e-9 aqui testaria
    # o transporte em vez da soma.
    for i in (0, 1, 7, 123, 400, 599):
        assert abs(desenhado[i] - esperado[i]) < 0.06


def test_o_residuo_comeca_na_PRIMEIRA_amostra():
    """Diferente de toda componente simétrica, que só existe depois de um ciclo
    inteiro: soma de três números não precisa de histórico nenhum."""
    r = trifasico(amplitudes=(3 * PICO, PICO, PICO))
    pacote = janela.montar(r, colunas=100_000,
                           layout=com_correntes(r, ["q0:n:instantaneo",
                                                    "q0:0:rms"]))
    painel = pacote["paineis"][0]
    assert sinal(painel, "q0:n:instantaneo")["serie"][0] is not None
    assert sinal(painel, "q0:0:rms")["serie"][0] is None


def test_a_curva_e_o_cursor_do_residuo_dao_o_MESMO_numero():
    """Mesma armadilha das componentes: a curva vem de uma passada sobre o
    registro inteiro e o cursor de uma janela só. Duas implementações da mesma
    identidade divergem em silêncio, meses depois."""
    r = trifasico(amplitudes=(3 * PICO, PICO, PICO))
    i = 400
    for identidade in ("q0:n:instantaneo", "q0:n:rms"):
        pacote = janela.montar(r, colunas=100_000,
                               layout=com_correntes(r, [identidade]))
        desenhado = sinal(pacote["paineis"][0], identidade)["serie"][i]
        lido = leitura.em(r, [(float(r.time[i]), 0, 0.0), (None, 0, 0.0)],
                          layout=com_correntes(r, [identidade]))
        do_cursor = lido["cursores"][0]["sinais"][identidade]["valor"]
        assert abs(desenhado - do_cursor) < 0.02, identidade


def test_o_residuo_ve_a_DC_que_o_3I0_nao_ve():
    """**É este o motivo de `IN` existir ao lado de `3I0`.**

    Trinca equilibrada mais uma DC pura numa fase: o resíduo no tempo é essa
    DC, constante. O `3I0` é módulo de fasor de 60 Hz e não enxerga nada ali —
    responde zero, corretamente, para a pergunta que ele responde.

    Num arquivo real essa DC é a assimetria da falta e o harmônico do TC
    saturando. Um relé de terra com filtro de RMS vê o primeiro número; um com
    filtro de fundamental vê o segundo. Ter os dois na tela é o que permite
    explicar por que dois relés no mesmo vão atuaram diferente.
    """
    r = trifasico()                      # equilibrado: resíduo alternado = 0
    deslocamento = 37.0
    r.analog = r.analog.copy()
    r.analog[0] += deslocamento

    i = 400
    lido = leitura.em(r, [(float(r.time[i]), 0, 0.0), (None, 0, 0.0)],
                      layout=[arranjo.analogico(["q0:n:rms", "q0:0:rms"])])
    valores = lido["cursores"][0]["sinais"]
    assert valores["q0:n:rms"]["valor"] == pytest_aprox(deslocamento, rel=1e-6)
    assert abs(valores["q0:0:rms"]["valor"]) < 0.01
    # E a tabelinha DIZ que a DC está ali — é o campo que denuncia a diferença.
    assert valores["q0:n:rms"]["dc_valor"] == pytest_aprox(deslocamento, rel=1e-6)


def test_em_regime_senoidal_o_residuo_eficaz_E_o_3I0():
    """A contrapartida do teste anterior: sem DC e sem harmônico os dois têm
    que dar o MESMO número. Se divergirem aqui, é erro de conta — não é
    grandeza diferente."""
    r = trifasico(amplitudes=(3 * PICO, PICO, PICO))
    i = 400
    lido = leitura.em(r, [(float(r.time[i]), 0, 0.0), (None, 0, 0.0)],
                      layout=[arranjo.analogico(["q0:n:rms", "q0:0:rms"])])
    valores = lido["cursores"][0]["sinais"]
    assert valores["q0:n:rms"]["valor"] == pytest_aprox(
        valores["q0:0:rms"]["valor"], rel=1e-6)


def test_o_rodape_do_residuo_FILTRADO_nao_promete_DC_nem_harmonico():
    """Com o filtro aceso, `IN G1` desenha `IN G1 · 60Hz`. A nota de sempre
    ("leva a DC e os harmônicos") descreveria justamente o que o filtro tirou.
    O mesmo vale para o `IN G1` de um registro que o relé já gravou filtrado."""
    r = trifasico()
    aceso = janela.montar(r, colunas=200, filtro=True,
                          layout=[arranjo.analogico(["q0:n:instantaneo"])])
    rodape = aceso["paineis"][0]["rodape"]
    assert janela.nota_do_residuo({"IN G1"}, filtrado=True) in rodape
    assert janela.nota_do_residuo({"IN G1"}) not in rodape
    assert "60 Hz" in janela.nota_do_residuo({"IN G1"}, filtrado=True)

    # Os dois no mesmo painel, com o filtro apagado: cada um com a sua nota.
    os_dois = janela.montar(
        r, colunas=200,
        layout=[arranjo.analogico(["q0:n:instantaneo", "q0:n:filtrado"])])
    rodape = os_dois["paineis"][0]["rodape"]
    assert janela.nota_do_residuo({"IN G1"}) in rodape
    assert janela.nota_do_residuo({"IN G1"}, filtrado=True) in rodape

    cev = trifasico()
    cev.filtering = Filtering.FILTRADO
    rodape = janela.montar(cev, colunas=200, layout=[
        arranjo.analogico(["q0:n:instantaneo"])])["paineis"][0]["rodape"]
    assert janela.nota_do_residuo({"IN G1"}, filtrado=True) in rodape


def test_o_rodape_diz_QUAL_conta_foi_feita():
    """A linha de origem é a mesma para resíduo e componente — os três canais
    são os mesmos. A nota do fim é que muda, e tem que mudar: dizer «módulo do
    fasor de um ciclo» embaixo de uma senoide somada no tempo descreveria a
    conta errada.
    """
    r = trifasico()
    so_residuo = janela.montar(
        r, colunas=200, layout=[arranjo.analogico(["q0:n:instantaneo"])])
    rodape = so_residuo["paineis"][0]["rodape"]
    assert any('"Current IA"' in linha for linha in rodape)
    assert janela.nota_do_residuo({"IN G1"}) in rodape
    assert janela.NOTA_DAS_COMPONENTES not in rodape

    so_componente = janela.montar(
        r, colunas=200, layout=[arranjo.analogico(["q0:0:rms"])])
    rodape = so_componente["paineis"][0]["rodape"]
    assert janela.NOTA_DAS_COMPONENTES in rodape
    assert not any("soma das três fases" in linha for linha in rodape)

    os_dois = janela.montar(
        r, colunas=200,
        layout=[arranjo.analogico(["q0:n:instantaneo", "q0:0:rms"])])
    rodape = os_dois["paineis"][0]["rodape"]
    assert janela.nota_do_residuo({"IN G1"}) in rodape
    assert janela.NOTA_DAS_COMPONENTES in rodape
    # Uma linha de origem só: a trinca é a mesma para os dois.
    #
    # A conta é pelo `— "`, e não por um traço solto: a nota das
    # componentes diz "módulo do fasor de um ciclo" e entrava na conta sozinha.
    # Passava porque a linha de origem começava com `de "` quando o conjunto
    # não tinha apelido; hoje todo grupo tem nome e ela começa com `G1 — de`.
    assert sum(1 for linha in rodape if ' — "' in linha) == 1


# ---------------------------------------------------------------------------
# A componente contínua como sinal
# ---------------------------------------------------------------------------

def test_o_catalogo_oferece_a_continua_no_registro_BRUTO():
    por_id = {s.id: s for s in catalogo.de_registro(trifasico())}
    assert por_id["v0:dc"].nome == "Current IA · DC"
    # Sem frequência no nome: `IA · 60Hz DC` se leria como "a DC da componente
    # de 60 Hz", que é zero por definição.
    assert "Hz" not in por_id["v0:dc"].nome


def test_registro_ja_filtrado_NAO_oferece_a_continua():
    """O relé tira a contínua antes de gravar, então num `.CEV` ela é zero por
    construção. Medido nos três `.CEV` do parque, só em regime: mediana de
    0,00 % a 0,02 % da fundamental, contra 0,2 % a 1,1 % nos COMTRADE brutos.

    Oferecer a curva ali seria oferecer uma linha em cima do zero, com alguns
    por cento de artefato de janela nas bordas — e quem olhasse procuraria
    significado físico numa coisa que o relé já removeu.
    """
    r = trifasico()
    r.filtering = Filtering.FILTRADO
    assert "v0:dc" not in {s.id for s in catalogo.de_registro(r)}


def test_a_continua_nao_muda_com_os_botoes_da_tela():
    """O filtro não tem par para ela — a contínua do sinal filtrado é zero por
    definição —, e a medida instantâneo/RMS só pega nos canais do IED."""
    r = trifasico()
    disponiveis = catalogo.por_id(r)
    for filtro in (False, True):
        for medida in ("instantaneo", "rms"):
            saiu = catalogo.efetivo("v0:dc", medida, filtro, disponiveis)
            assert saiu.id == "v0:dc"


def test_a_curva_e_o_cursor_da_continua_dao_o_MESMO_numero():
    r = trifasico(amplitudes=(3 * PICO, PICO, PICO))
    r.analog = r.analog.copy()
    r.analog[0] += 55.0                      # uma assimetria conhecida
    i = 400
    pacote = janela.montar(r, colunas=100_000,
                           layout=com_correntes(r, ["v0:dc"]))
    desenhado = sinal(pacote["paineis"][0], "v0:dc")["serie"][i]
    lido = leitura.em(r, [(float(r.time[i]), 0, 0.0), (None, 0, 0.0)],
                      layout=com_correntes(r, ["v0:dc"]))
    linha = lido["cursores"][0]["sinais"]["v0:dc"]
    assert linha["valor"] == pytest_aprox(55.0, rel=1e-6)
    assert abs(desenhado - linha["valor"]) < 0.06
    # O percentual da fundamental — a convenção do SIGRA — continua no pacote,
    # no campo próprio. É ele que se compara com a coluna do SIGRA.
    assert linha["dc"] == pytest_aprox(100.0 * 55.0 / (3 * PICO / math.sqrt(2)),
                                       rel=1e-2)


def test_o_residuo_oferece_a_CONTINUA_no_registro_bruto():
    """`IN · DC` é a parte de 0 Hz do resíduo, complementar ao `3I0`, que é a
    de 60 Hz. Não estava na tela: a contínua de cada FASE estava, a do
    resíduo não — e é ela que passa pelo TC de neutro."""
    por_id = {s.id: s for s in catalogo.de_registro(trifasico())}
    assert por_id["q0:n:dc"].nome == "IN G1 · DC"
    assert por_id["q1:n:dc"].nome == "VN G2 · DC"


def test_registro_filtrado_nao_oferece_a_continua_do_residuo():
    """Mesma razão da contínua dos canais: o relé tira a DC antes de gravar,
    então num `.CEV` ela é zero por construção."""
    r = trifasico()
    r.filtering = Filtering.FILTRADO
    assert "q0:n:dc" not in {s.id for s in catalogo.de_registro(r)}


def test_o_residuo_se_decompoe_e_PARSEVAL_fecha():
    """**O teste que dá razão a `IN · DC` existir ao lado de `3I0`.**

    A onda do resíduo se parte em três pedaços ortogonais — 0 Hz, 60 Hz e
    harmônicos — e o eficaz dela amarra os três:

        IN·RMS² = 3I0² + IN·DC² + harmônicos²

    Sem harmônico, a identidade fecha exata. Se alguém trocar o estimador de
    um dos três, ela abre — e nenhum dos três, olhado sozinho, denunciaria.
    """
    r = trifasico()
    r.analog = r.analog.copy()
    r.analog[0] += 55.0          # desequilíbrio puro de DC numa fase

    i = 400
    lido = leitura.em(r, [(float(r.time[i]), 0, 0.0), (None, 0, 0.0)],
                      layout=[arranjo.analogico(["q0:n:rms", "q0:n:dc",
                                                 "q0:0:rms"])])
    v = lido["cursores"][0]["sinais"]
    eficaz = v["q0:n:rms"]["valor"]
    continua = v["q0:n:dc"]["valor"]
    fundamental = v["q0:0:rms"]["valor"]

    # A trinca é equilibrada, então o resíduo alternado é zero: sobra a DC.
    assert continua == pytest_aprox(55.0, rel=1e-6)
    assert abs(fundamental) < 0.01
    assert eficaz == pytest_aprox(math.sqrt(fundamental**2 + continua**2),
                                  rel=1e-6)


def test_a_curva_e_o_cursor_da_continua_do_residuo_dao_o_MESMO_numero():
    r = trifasico(amplitudes=(3 * PICO, PICO, PICO))
    r.analog = r.analog.copy()
    r.analog[0] += 55.0
    i = 400
    pacote = janela.montar(r, colunas=100_000,
                           layout=com_correntes(r, ["q0:n:dc"]))
    desenhado = sinal(pacote["paineis"][0], "q0:n:dc")["serie"][i]
    lido = leitura.em(r, [(float(r.time[i]), 0, 0.0), (None, 0, 0.0)],
                      layout=com_correntes(r, ["q0:n:dc"]))
    do_cursor = lido["cursores"][0]["sinais"]["q0:n:dc"]["valor"]
    assert do_cursor == pytest_aprox(55.0, rel=1e-6)
    assert abs(desenhado - do_cursor) < 0.06


# ---------------------------------------------------------------------------
# A LINHA e o BLOCO: o que arruma a tela em matriz
# ---------------------------------------------------------------------------

def test_a_LINHA_junta_as_contas_do_mesmo_canal():
    """`IAW`, `IAW · RMS`, `IAW · DC`, `IAW · 60Hz` e `IAW · 60Hz RMS` são cinco
    sinais e UMA linha do catálogo: a do canal. É o que deixa a tela ser uma
    matriz de canais × contas em vez de uma lista de cento e vinte nomes — e
    por isso a linha nasce aqui, junto do nome, e não no navegador."""
    por_linha: dict[str, set[str]] = {}
    for s in catalogo.de_registro(trifasico()):
        por_linha.setdefault(s.linha, set()).add(s.grandeza)
    assert por_linha["Current IA"] == {"instantaneo", "rms", "dc",
                                       "filtrado", "fundamental"}
    # O resíduo é linha própria, com as MESMAS colunas de um canal — inclusive
    # o eficaz de 60 Hz, que é o número do `3I0` (pedido do usuário, out/2026).
    assert por_linha["IN G1"] == {"instantaneo", "rms", "dc",
                                  "filtrado", "fundamental"}
    # A componente é linha de uma coluna só: fasor não tem valor instantâneo.
    assert por_linha["3I0 G1"] == {"fundamental"}


def test_o_GRUPO_do_canal_e_o_do_conjunto_dele():
    grupos = {s.linha: s.grupo for s in catalogo.de_registro(trifasico())}
    assert grupos["Current IA"] == grupos["IN G1"] == grupos["3I0 G1"] == "G1"
    assert grupos["Voltage A-G"] == grupos["VN G2"] == "G2"


def test_o_BLOCO_separa_alternado_de_sequencia():
    blocos = {s.linha: s.bloco for s in catalogo.de_registro(trifasico())}
    assert blocos["Current IA"] == "alternado"
    # O resíduo é senoide somada no tempo, não fasor: fica com os alternados.
    assert blocos["IN G1"] == "alternado"
    assert blocos["3I0 G1"] == blocos["I1 G1"] == "sequencia"


def test_o_que_nao_e_alternado_vai_para_OUTROS_com_o_motivo():
    """A tela não afirma que este canal é contínuo — afirma que não sabe tirar
    fasor dele, que é o que foi medido. Ver `analysis/presenca.py`."""
    r = trifasico()
    canais = list(r.analog_channels)
    canais.append(AnalogChannel(index=6, name="Freq", unit="Hz", phase=""))
    r.analog_channels = tuple(canais)
    r.analog = np.vstack([r.analog, np.full((1, r.analog.shape[1]), 60.0)])

    do_hertz = [s for s in catalogo.de_registro(r) if s.linha == "Freq"]
    # Uma linha, uma coluna: a onda como o relé gravou, e nada mais.
    assert [s.grandeza for s in do_hertz] == ["instantaneo"]
    assert do_hertz[0].bloco == "outros"
    assert do_hertz[0].motivo == "não passou no teste de alternado"
    assert do_hertz[0].grupo == ""


def test_canal_sem_unidade_declarada_diz_ISSO_e_nao_outra_coisa():
    """As colunas `ANAnn` de um CEV não declaram unidade, e ali convivem kV, A,
    grau e hertz. O motivo tem que ser o certo: quem lê decide se vale abrir o
    arquivo no editor de texto para descobrir o que é aquilo."""
    r = trifasico()
    canais = list(r.analog_channels)
    canais.append(AnalogChannel(index=6, name="ANA14", unit="", phase=""))
    r.analog_channels = tuple(canais)
    r.analog = np.vstack([r.analog, np.full((1, r.analog.shape[1]), 7.0)])

    do_ana = [s for s in catalogo.de_registro(r) if s.linha == "ANA14"]
    assert [s.bloco for s in do_ana] == ["outros"]
    assert do_ana[0].motivo == "o arquivo não declara unidade"


# ---------------------------------------------------------------------------
# A COLUNA: qual sinal é, e não só que conta se fez
# ---------------------------------------------------------------------------

def test_a_coluna_separa_o_filtrado_do_bruto():
    """A matriz responde duas perguntas: QUAL sinal (o filtrado, só 60 Hz, ou o
    bruto, tudo o que o relé gravou) e COMO olhar (onda, eficaz, contínua).
    Enquanto as cinco colunas foram irmãs, nada dizia que `onda` e `60 Hz` eram
    sinais diferentes."""
    por_nome = {s.nome: s.coluna for s in catalogo.de_registro(trifasico())}
    assert por_nome["Current IA"] == "bruto.onda"
    assert por_nome["Current IA · RMS"] == "bruto.rms"
    assert por_nome["Current IA · DC"] == "bruto.dc"
    assert por_nome["Current IA · 60Hz"] == "filtrado.onda"
    assert por_nome["Current IA · 60Hz RMS"] == "filtrado.rms"
    # A componente simétrica nasce do filtro, e mora na coluna dele mesmo num
    # registro bruto: ela é o módulo de um fasor de um ciclo.
    assert por_nome["3I0 G1"] == "filtrado.rms"


def test_num_registro_JA_FILTRADO_o_canal_mora_na_coluna_do_filtrado():
    """Num `.CEV` as amostras SÃO a componente de 60 Hz — não existe bruto
    naquele arquivo. Pôr o canal e o eficaz dele nas colunas do bruto fazia a
    tela dizer que se estava olhando a onda crua quando não se estava.

    O NOME não muda por isso: a ressalva de que o relé filtrou é do registro
    inteiro, e quem a diz é o cabeçalho."""
    r = trifasico()
    r.filtering = Filtering.FILTRADO
    por_nome = {s.nome: s.coluna for s in catalogo.de_registro(r)}
    assert por_nome["Current IA"] == "filtrado.onda"
    assert por_nome["Current IA · RMS"] == "filtrado.rms"
    assert por_nome["IN G1"] == "filtrado.onda"
    # E o bruto não existe: nenhuma coluna dele é oferecida.
    assert not [c for c in por_nome.values() if c.startswith("bruto.")]


# ---------------------------------------------------------------------------
# A trinca em DELTA, do arquivo até a curva
# ---------------------------------------------------------------------------

def _em_delta(amplitudes=(PICO, PICO, PICO),
              defasagens=(0.0, -120.0, -240.0), n=600, taxa=1200.0,
              freq=60.0) -> Record:
    """Um registro com `VAB`, `VBC`, `VCA` — as DIFERENÇAS entre três fases.

    As amostras saem das fases de verdade e depois se subtraem, que é o que o
    TP em delta faz fisicamente. Assim o teste tem o gabarito: sabe qual é o
    `V1` de fase que a tela TEM que mostrar.
    """
    t = np.arange(n) / taxa
    fases_ = [a * np.sin(2 * np.pi * freq * t + math.radians(d))
              for a, d in zip(amplitudes, defasagens)]
    linhas = [fases_[0] - fases_[1], fases_[1] - fases_[2],
              fases_[2] - fases_[0]]
    r = Record(source=Path("sintetico"), format_name="teste")
    r.line_frequency = freq
    # A fase vem da ESCOLHA do usuário, que é o caminho que este marco abriu:
    # o nome `VAB` ainda é deduzido como fase A, e corrigir isso sozinho é
    # outra decisão — ver a pendência anotada no relatório do marco.
    r.analog_channels = tuple(
        AnalogChannel(index=i, name=nome, unit="V", phase="",
                      phase_escolhida=laco)
        for i, (nome, laco) in enumerate(
            (("VAB", "AB"), ("VBC", "BC"), ("VCA", "CA"))))
    r.analog = np.vstack(linhas)
    r.time = t
    r.status = np.zeros((0, n), dtype=np.int8)
    return r


def test_em_delta_nao_existe_residuo_nem_sequencia_zero():
    """Os dois saem de `VAB+VBC+VCA`, que é zero por identidade algébrica.

    Oferecê-los desenharia uma linha plana no gráfico dizendo «não há falta à
    terra» — afirmação que ninguém mediu, numa trinca onde o neutro não está.
    """
    nomes = {s.nome for s in catalogo.de_registro(_em_delta())}
    assert not [x for x in nomes if x.startswith("3V0")]
    assert not [x for x in nomes if x.startswith("VN")]
    assert [x for x in nomes if x.startswith("V1")]
    assert [x for x in nomes if x.startswith("V2")]


def test_em_delta_o_V1_sai_referido_a_FASE():
    """O número que a tela mostra tem que ser o `V1` das fases, não o dos
    laços — que é √3 maior. 73 % de erro, na unidade certa e sem aviso."""
    registro = _em_delta()
    escalas = {}
    alvo = next(s for s in catalogo.de_registro(registro)
                if s.nome.startswith("V1"))
    n = registro.analog.shape[1]
    serie = catalogo.serie(registro, alvo, 0, n, registro.trechos,
                           "arquivo", escalas)
    bons = serie[np.isfinite(serie)]
    # Equilibrado: V1 de fase é o próprio valor eficaz da fase.
    assert abs(float(np.median(bons)) - PICO / math.sqrt(2.0)) < 0.01


def test_em_delta_a_curva_e_o_cursor_continuam_batendo():
    """A mesma identidade por dois caminhos — soma móvel e janela única. É
    assim que duas implementações da mesma conta divergem em silêncio."""
    registro = _em_delta(amplitudes=(PICO, 0.4 * PICO, 0.8 * PICO),
                         defasagens=(0.0, -150.0, 95.0))
    escalas = {}
    alvo = next(s for s in catalogo.de_registro(registro)
                if s.nome.startswith("V2"))
    n = registro.analog.shape[1]
    serie = catalogo.serie(registro, alvo, 0, n, registro.trechos,
                           "arquivo", escalas)
    i = n - 40
    por_ciclo = registro.line_frequency and (1.0 / registro.line_frequency) / (
        registro.time[1] - registro.time[0])
    lido = catalogo.fasor_de_componente(registro, alvo, i, por_ciclo,
                                        "arquivo", 1.0)
    assert lido is not None
    assert abs(lido[0] - float(serie[i])) < 0.01
