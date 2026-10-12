"""O painel fasorial: quem entra, e qual é o 1 pu de cada um.

Os números do diagrama (módulo e ângulo) vêm da leitura do cursor, que já tem
os seus testes contra o SIGRA. O que se testa aqui é o que é NOVO: a base do pu
— e, sobretudo, as três armadilhas dela. Ver `plot/fasorial.py`.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from osclab.formats.base import Filtering
from osclab.plot import fasorial, janela, leitura, paineis
from tests import arranjo
from tests.test_catalogo import PICO, trifasico


def com_relacao(registro, correntes=(600.0, 5.0), tensoes=(13800.0, 115.0),
                escala="S"):
    """O mesmo registro, com o TC/TP declarado no `.cfg`."""
    canais = []
    for c in registro.analog_channels:
        p, s = correntes if c.unit == "A" else tensoes
        canais.append(replace(c, primary=p, secondary=s, scaling=escala))
    registro.analog_channels = tuple(canais)
    return registro


def pacote_fasorial(registro, sinais, lado="arquivo"):
    pacote = janela.montar(registro, colunas=200, lado=lado,
                           layout=[arranjo.fasorial(sinais)])
    return {s["id"]: s for s in pacote["paineis"][0]["sinais"]}


def test_o_painel_fasorial_aceita_so_o_que_tem_fasor():
    r = trifasico()
    pedidos = ["c0:instantaneo", "q0:n:instantaneo", "q0:0:rms", "q0:1:rms",
               # contas de uma linha: o fasor é da linha, não delas
               "v0:rms", "v0:filtrado", "q0:n:rms",
               "inexistente"]
    saiu = pacote_fasorial(r, pedidos)
    assert list(saiu) == ["c0:instantaneo", "q0:n:instantaneo", "q0:0:rms",
                          "q0:1:rms"]
    assert saiu["c0:instantaneo"]["sinal"] == "Current IA"
    assert saiu["q0:n:instantaneo"]["sinal"] == "IN G1"
    assert saiu["q0:0:rms"]["sinal"] == "3I0 G1"


def test_o_tipo_fasorial_sobrevive_a_ida_e_volta_pela_tela():
    lido = paineis.de_json([{"id": "f1", "tipo": "fasorial", "nome": "F",
                             "sinais": ["c0:instantaneo"]}])
    assert lido[0].tipo == paineis.FASORIAL
    assert lido[0].sinais == ("c0:instantaneo",)


def test_a_base_e_o_que_o_cfg_declara_no_lado_da_tela():
    """600/5: 5 A no secundário, 600 A no primário."""
    r = com_relacao(trifasico())
    sec = pacote_fasorial(r, ["c0:instantaneo"], lado="secundario")
    assert sec["c0:instantaneo"]["base"] == pytest.approx(5.0)
    pri = pacote_fasorial(r, ["c0:instantaneo"], lado="primario")
    # Na unidade que a tela mostra: 600 A primários são escritos em kA.
    assert pri["c0:instantaneo"]["unidade"] == "kA"
    assert pri["c0:instantaneo"]["base"] == pytest.approx(0.6)
    assert "600 / 5" in pri["c0:instantaneo"]["base_origem"]


def test_a_RAZAO_mais_o_secundario_nominal_viram_a_base():
    """O SEL-451 do parque grava `120 / 1` nos canais de corrente e de tensão:
    isso é a RELAÇÃO (RTC 600/5 = 120, RTP 13800/115 = 120), não o par de
    nominais. Usar o 120 como base dava 120 kV numa barra de 13,8 kV.

    Falta a outra metade do par, e ela é padrão de ofício: 5 A no secundário
    do TC, 115 V fase-fase no do TP. Com ela, `120 / 1` vira `600 / 5` e
    `13800 / 115` — o que está na placa. Medido no alimentador do parque: a
    pré-falta deu 101 % dos 7,967 kV derivados.
    """
    r = com_relacao(trifasico(), correntes=(120.0, 1.0), tensoes=(120.0, 1.0),
                    escala="S")
    saiu = pacote_fasorial(r, ["c0:instantaneo"], lado="secundario")
    assert saiu["c0:instantaneo"]["base"] == pytest.approx(5.0)
    assert "600 / 5" in saiu["c0:instantaneo"]["base_origem"]

    # No primário, a mesma relação dá a nominal do equipamento.
    r = com_relacao(trifasico(), correntes=(120.0, 1.0), tensoes=(120.0, 1.0))
    saiu = pacote_fasorial(r, ["c0:instantaneo"], lado="primario")
    assert saiu["c0:instantaneo"]["base"] == pytest.approx(0.6)   # 600 A em kA


def test_a_tensao_derivada_da_razao_e_CONFERIDA_na_pre_falta():
    """A barra sadia está na nominal, então a derivação tem que bater com o
    que o registro mede — fase-terra ou fase-fase. Quando não bate, não há
    base: vale o maior do registro, e a tela diz isso."""
    r = trifasico()
    eficaz = 115.0 / math.sqrt(3.0)
    r.analog = r.analog.copy()
    r.analog[3:6] *= eficaz * math.sqrt(2.0) / PICO
    com_relacao(r, correntes=(120.0, 1.0), tensoes=(120.0, 1.0), escala="S")
    saiu = pacote_fasorial(r, ["c3:instantaneo"], lado="secundario")
    assert saiu["c3:instantaneo"]["base"] == pytest.approx(115.0 / math.sqrt(3.0))
    assert "fase-terra" in saiu["c3:instantaneo"]["base_origem"]

    # Uma barra que não está em 115 V nem em 115/√3: a derivação é recusada.
    fora = trifasico()
    fora.analog = fora.analog.copy()
    fora.analog[3:6] *= 20.0 * math.sqrt(2.0) / PICO
    com_relacao(fora, correntes=(120.0, 1.0), tensoes=(120.0, 1.0), escala="S")
    saiu = pacote_fasorial(fora, ["c3:instantaneo"], lado="secundario")
    assert saiu["c3:instantaneo"]["base"] is None
    assert "não bate" in saiu["c3:instantaneo"]["base_origem"]


def test_a_relacao_respeita_o_PREFIXO_da_unidade_do_canal():
    """O SEL grava a tensão em kV e a relação como número puro: 115 V viram
    0,115 ali. Sem o prefixo a base sairia mil vezes maior — a ordem de erro
    que o pu existe para não ter."""
    r = trifasico()
    r.analog_channels = tuple(
        replace(c, unit="kV" if c.unit == "V" else c.unit,
                primary=120.0, secondary=1.0, scaling="P")
        for c in r.analog_channels)
    r.analog = r.analog.copy()
    r.analog[3:6] *= 7.967 * math.sqrt(2.0) / PICO     # 7,967 kV fase-terra
    saiu = pacote_fasorial(r, ["c3:instantaneo"], lado="primario")
    assert saiu["c3:instantaneo"]["base"] == pytest.approx(13.8 / math.sqrt(3.0),
                                                          rel=1e-3)


def test_a_relacao_em_kV_tambem_vale_no_lado_SECUNDARIO():
    """O mesmo arquivo do SEL — tensão em kV, gravada em primário, `120 / 1` —
    visto em SECUNDÁRIO.

    A base derivada está no lado da tela (115/√3 V, ou 0,0664 kV), mas a
    pré-falta que a confere saía do arquivo sem converter: 7,967 kV contra
    0,0664 kV dá 120×, nenhum candidato batia, e um RTP perfeitamente
    declarado caía no «maior do registro». A corrente não mostrava o problema
    porque ela não é conferida contra a pré-falta.
    """
    r = trifasico()
    r.analog_channels = tuple(
        replace(c, unit="kV" if c.unit == "V" else c.unit,
                primary=120.0, secondary=1.0, scaling="P")
        for c in r.analog_channels)
    r.analog = r.analog.copy()
    r.analog[3:6] *= 7.967 * math.sqrt(2.0) / PICO     # 7,967 kV fase-terra
    saiu = pacote_fasorial(r, ["c3:instantaneo"], lado="secundario")
    assert saiu["c3:instantaneo"]["base"] == pytest.approx(
        0.115 / math.sqrt(3.0), rel=1e-3)
    assert "fase-terra" in saiu["c3:instantaneo"]["base_origem"]


def test_base_de_tensao_que_a_pre_falta_desmente_nao_serve():
    """A tensão de uma barra sadia É a nominal dela, e isso é conferível. Um
    par que não bate com o que o registro mede não é nominal de nada."""
    r = trifasico()                       # pré-falta de 70,7 V eficazes
    com_relacao(r, tensoes=(500.0, 400.0))
    saiu = pacote_fasorial(r, ["c3:instantaneo"], lado="secundario")
    assert saiu["c3:instantaneo"]["base"] is None
    assert "não é a nominal" in saiu["c3:instantaneo"]["base_origem"]


def test_a_corrente_nao_tem_pre_falta_que_a_desminta():
    """A carga de um alimentador pode ser qualquer fração da nominal, então
    nenhuma medida do registro contradiz uma base de corrente. Só a peneira da
    razão vale para ela."""
    r = com_relacao(trifasico(), correntes=(600.0, 5.0))
    saiu = pacote_fasorial(r, ["c0:instantaneo"], lado="secundario")
    assert saiu["c0:instantaneo"]["base"] == pytest.approx(5.0)


def test_sem_relacao_no_arquivo_nao_ha_base():
    """O `.CEV` não traz relação nenhuma, e `1 / 1` é o que sobra. Inventar
    base daria um pu com cara de medida e sem significado."""
    saiu = pacote_fasorial(trifasico(), ["c0:instantaneo", "c3:instantaneo"])
    for s in saiu.values():
        assert s["base"] is None
        assert "não declara" in s["base_origem"]


def test_TP_declarado_fase_fase_vira_base_sobre_raiz_de_3():
    """`13800 / 115` num canal `VA`: sem correção a tensão sadia leria
    0,577 pu. A pré-falta medida denuncia — e a origem diz o que se fez."""
    r = trifasico()
    eficaz = 115.0 / math.sqrt(3.0)              # fase-terra secundária sadia
    r.analog = r.analog.copy()
    r.analog[3:6] *= eficaz * math.sqrt(2.0) / PICO
    com_relacao(r)
    saiu = pacote_fasorial(r, ["c3:instantaneo"], lado="secundario")
    assert saiu["c3:instantaneo"]["base"] == pytest.approx(115.0 / math.sqrt(3.0))
    assert "√3" in saiu["c3:instantaneo"]["base_origem"]


def test_TP_declarado_fase_terra_fica_como_esta():
    r = trifasico()
    r.analog = r.analog.copy()
    r.analog[3:6] *= 66.4 * math.sqrt(2.0) / PICO
    com_relacao(r, tensoes=(7967.0, 66.4))
    saiu = pacote_fasorial(r, ["c3:instantaneo"], lado="secundario")
    assert saiu["c3:instantaneo"]["base"] == pytest.approx(66.4)
    assert "√3" not in saiu["c3:instantaneo"]["base_origem"]


def test_residuo_e_componente_herdam_a_base_da_fase_A_da_trinca():
    r = com_relacao(trifasico())
    saiu = pacote_fasorial(r, ["q0:n:instantaneo", "q0:0:rms", "q0:2:rms"],
                           lado="primario")
    for s in saiu.values():
        assert (s["base"], s["unidade"]) == (pytest.approx(0.6), "kA")
        assert "Current IA" in s["base_origem"]


def test_a_leitura_traz_modulo_e_angulo_dos_sinais_do_fasorial():
    r = trifasico()
    i = 400
    lido = leitura.em(r, [(float(r.time[i]), 0, 0.0), (None, 0, 0.0)],
                      layout=[arranjo.fasorial(["c0:instantaneo", "c1:instantaneo",
                                                "q0:1:rms"])])
    v = lido["cursores"][0]["sinais"]
    assert v["c0:instantaneo"]["fundamental"] == pytest.approx(PICO / math.sqrt(2),
                                                             rel=1e-3)
    # B atrasada 120° de A, qualquer que seja a referência automática
    diferenca = (v["c1:instantaneo"]["angulo"] - v["c0:instantaneo"]["angulo"]
                 + 540) % 360 - 180
    assert diferenca == pytest.approx(-120.0, abs=0.05)
    assert v["q0:1:rms"]["fundamental"] == pytest.approx(PICO / math.sqrt(2),
                                                        rel=1e-3)


def test_o_fasorial_nao_sobrescreve_a_leitura_do_grafico_de_ondas():
    """O mesmo `c0:instantaneo` num gráfico com o filtro aceso é `IAW · 60Hz`.
    Se a linha do fasorial viesse por cima, a tabelinha daquele gráfico
    mostraria a amostra crua."""
    r = trifasico()
    r.filtering = Filtering.BRUTO
    i = 400
    layout = [arranjo.analogico(["c0:instantaneo"]),
              arranjo.fasorial(["c0:instantaneo"])]
    lido = leitura.em(r, [(float(r.time[i]), 0, 0.0), (None, 0, 0.0)],
                      filtro=True, layout=layout)
    linha = lido["cursores"][0]["sinais"]["c0:instantaneo"]
    assert linha["id_efetivo"] == "v0:filtrado"
    assert linha["angulo"] is not None and linha["fundamental"] is not None


def test_o_painel_fasorial_nao_tem_serie_nem_eixo():
    """Ele é de UM instante: série, escala vertical e eixo do tempo não existem
    nele. Mandar uma série vazia seria convidar a tela a desenhar uma reta."""
    r = trifasico()
    painel = janela.montar(r, colunas=200,
                           layout=[arranjo.fasorial(["c0:instantaneo"])
                                   ])["paineis"][0]
    assert painel["tipo"] == "fasorial"
    assert set(painel) == {"id", "tipo", "nome", "do_padrao", "sinais",
                           "rodape"}
    assert "serie" not in painel["sinais"][0]


def test_um_fasorial_junto_de_um_grafico_de_ondas_nao_atrapalha_o_desenho():
    """Os dois no mesmo arranjo: o de ondas continua com série e escala, e o
    fasorial entra sem eixo nenhum."""
    r = trifasico()
    pacote = janela.montar(r, colunas=200, layout=[
        arranjo.analogico(["c0:instantaneo"], identidade="p1"),
        arranjo.fasorial(["c0:instantaneo"], identidade="p2")])
    ondas, fasores = pacote["paineis"]
    assert ondas["sinais"][0]["serie"]
    assert fasores["tipo"] == "fasorial"


def test_o_pico_do_registro_vem_junto_e_e_do_registro_INTEIRO():
    """É a base de quem não tem RTC/RTP utilizável — o caso do parque inteiro.

    Sai do registro inteiro, e não do instante do cursor: depois que o
    disjuntor abre sobram alguns décimos de ampère, e normalizá-los por eles
    mesmos os mandaria ao raio do círculo como se fossem falta.
    """
    r = trifasico(amplitudes=(3 * PICO, PICO, PICO))
    r.analog = r.analog.copy()
    r.analog[:3, 400:] *= 0.01              # o disjuntor abre no meio
    saiu = pacote_fasorial(r, ["c0:instantaneo", "q0:0:rms",
                               "q0:n:instantaneo"])
    assert saiu["c0:instantaneo"]["pico"] == pytest.approx(3 * PICO / math.sqrt(2),
                                                           rel=1e-2)
    for s in saiu.values():
        assert s["pico"] > 0


def test_o_pico_nao_muda_com_a_janela_da_tela():
    """Ampliar um pedaço não pode mudar o tamanho das setas — duas telas do
    mesmo evento têm que se comparar."""
    r = trifasico(amplitudes=(3 * PICO, PICO, PICO))
    r.analog = r.analog.copy()
    r.analog[:3, 400:] *= 0.01
    inteiro = pacote_fasorial(r, ["c0:instantaneo"])["c0:instantaneo"]["pico"]
    pedaco = janela.montar(r, colunas=200, de=float(r.time[450]),
                           ate=float(r.time[550]),
                           layout=[arranjo.fasorial(["c0:instantaneo"])])
    assert pedaco["paineis"][0]["sinais"][0]["pico"] == pytest.approx(inteiro)


def test_o_fasorial_avisa_qual_canal_esta_SEM_SINAL():
    """O ângulo de um canal não cabeado é o ângulo do ruído do conversor, e a
    tela não desenha seta para ele — o módulo continua na tabela. Sem este
    campo, a seta mínima apontaria para um número sem significado."""
    # Duas trincas de corrente, uma cabeada e outra não — é o SEL-487E com
    # terminais de TC livres. A medida é por COMPARAÇÃO com a maior da mesma
    # unidade, então a trinca morta precisa de uma viva ao lado.
    from tests.test_presenca import registro, ruido, senoide, trinca
    r = registro(*trinca("I", "W", "A", lambda g: senoide(100.0, g)),
                 *trinca("I", "X", "A", lambda g: ruido(1.0)))
    saiu = pacote_fasorial(r, ["c0:instantaneo", "c3:instantaneo"])
    assert saiu["c0:instantaneo"]["sem_sinal"] is False
    assert saiu["c3:instantaneo"]["sem_sinal"] is True


def test_a_REFERENCIA_do_fasorial_entra_na_leitura_sem_estar_no_diagrama():
    """Medir o ângulo das correntes a partir de `VAY` é a conta de
    direcionalidade do ofício, e ela não obriga a tensão a estar desenhada.

    O fasor da referência é do servidor como o de qualquer outro — a tela não
    calcula fasor nenhum. Sem isto, o ângulo escolhido não teria de onde sair e
    a tela mostraria o ângulo absoluto achando que era o relativo.
    """
    r = trifasico()
    i = 400
    painel = paineis.Painel(id="pf", tipo=paineis.FASORIAL, nome="F",
                            sinais=("c0:instantaneo",),
                            referencia="c3:instantaneo")
    lido = leitura.em(r, [(float(r.time[i]), 0, 0.0), (None, 0, 0.0)],
                      layout=[painel])
    v = lido["cursores"][0]["sinais"]
    assert "c3:instantaneo" in v           # a referência foi lida
    assert v["c3:instantaneo"]["angulo"] is not None
    # e ela NÃO entra no desenho: o diagrama mostra o que foi escolhido
    desenhado = janela.montar(r, colunas=200, layout=[painel])["paineis"][0]
    assert [s["id"] for s in desenhado["sinais"]] == ["c0:instantaneo"]


def test_a_referencia_sobrevive_a_ida_e_volta_pela_tela():
    lido = paineis.de_json([{"id": "f1", "tipo": "fasorial", "nome": "F",
                             "sinais": ["c0:instantaneo"],
                             "referencia": "c3:instantaneo"}])
    assert lido[0].referencia == "c3:instantaneo"
    sem = paineis.de_json([{"id": "f1", "tipo": "fasorial", "sinais": []}])
    assert sem[0].referencia == ""


def test_o_fasorial_diz_de_que_canais_o_GRUPO_saiu():
    """`G1` não diz sozinho de que três canais ele veio, e num diagrama de
    `3I0`, `I1` e `IN` TODOS os sinais são desses — não há nome de arquivo a
    herdar em nenhum deles."""
    r = trifasico()
    painel = janela.montar(r, colunas=200, layout=[
        arranjo.fasorial(["q0:0:rms", "q0:n:instantaneo"])])["paineis"][0]
    assert any('"Current IA"' in linha for linha in painel["rodape"])
    assert any(linha.startswith("G1 — ") for linha in painel["rodape"])
    # No fasorial tudo é fasor de 60 Hz: a nota do resíduo não pode prometer
    # a DC e os harmônicos, que não estão ali.
    assert janela.nota_do_residuo({"IN G1"}, filtrado=True) in painel["rodape"]

    # Um diagrama só de canais do arquivo não precisa da nota: a legenda já
    # diz o nome de cada um.
    so_canais = janela.montar(r, colunas=200, layout=[
        arranjo.fasorial(["c0:instantaneo"])])["paineis"][0]
    assert so_canais["rodape"] == []


def test_o_par_escrito_em_VOLT_num_canal_em_QUILOVOLT_e_corrigido():
    """A norma manda o canal declarar a unidade dos DADOS; nada obriga o par de
    TC/TP a estar nela. Há fabricante que já grava `13800 / 115` — o par certo,
    o que é bom —, e se o canal foi gravado em kV a base sai mil vezes maior.

    Quem denuncia é o registro: uma base mil vezes acima do que o relé mediu
    não é base de nada. Dividir pelo prefixo põe tudo no lugar.
    """
    r = trifasico()
    r.analog = r.analog.copy()
    r.analog[3:6] *= 7.967 * math.sqrt(2.0) / PICO           # 7,967 kV
    r.analog_channels = tuple(
        replace(c, unit="kV" if c.unit == "V" else c.unit,
                primary=13800.0 if c.unit == "V" else 600.0,
                secondary=115.0 if c.unit == "V" else 5.0, scaling="P")
        for c in r.analog_channels)
    saiu = pacote_fasorial(r, ["c3:instantaneo"], lado="primario")
    assert saiu["c3:instantaneo"]["base"] == pytest.approx(13.8 / math.sqrt(3.0),
                                                          rel=1e-3)
    assert "1000×" in saiu["c3:instantaneo"]["base_origem"]


def test_par_que_o_registro_desmente_por_mil_vezes_nao_vira_base():
    """A corrente não tem pré-falta que a confira — a carga é qualquer fração
    da nominal. O que sobra é a ordem de grandeza, e ela pega o erro de mil
    vezes: um par em ampère num canal gravado em quiloampère."""
    r = trifasico()                                   # 70,7 A eficazes
    r.analog_channels = tuple(
        replace(c, unit="kA" if c.unit == "A" else c.unit,
                primary=600.0, secondary=5.0, scaling="P")
        for c in r.analog_channels if c.unit == "A")
    r.analog = r.analog[:3].copy()
    saiu = pacote_fasorial(r, ["c0:instantaneo"], lado="primario")
    # 600 kA contra 70,7 kA medidos: a razão cabe, e a base fica como está.
    assert saiu["c0:instantaneo"]["base"] == pytest.approx(600.0)

    # Agora o mesmo par num canal que mede mil vezes menos: o prefixo entra.
    r2 = trifasico(amplitudes=(PICO / 1000, PICO / 1000, PICO / 1000))
    r2.analog_channels = tuple(
        replace(c, unit="kA" if c.unit == "A" else c.unit,
                primary=600.0, secondary=5.0, scaling="P")
        for c in r2.analog_channels if c.unit == "A")
    r2.analog = r2.analog[:3].copy()
    saiu = pacote_fasorial(r2, ["c0:instantaneo"], lado="primario")
    assert saiu["c0:instantaneo"]["base"] == pytest.approx(0.6)
    assert "1000×" in saiu["c0:instantaneo"]["base_origem"]


def test_a_regua_de_uma_COMPONENTE_e_a_das_fases_que_a_produziram():
    """`V2` de um sistema são dois ou três por cento da tensão de fase.
    Normalizado por si mesmo ele encheria o círculo em qualquer registro, e um
    desequilíbrio de 2 % se leria igual a um de 30 % — que é o contrário do
    que o diagrama existe para mostrar.

    Sem RTC/RTP utilizável, o 1 pu da sequência tem que ser o pico da FASE.
    """
    r = trifasico(amplitudes=(PICO, 0.9 * PICO, 1.1 * PICO))   # desequilíbrio
    saiu = pacote_fasorial(r, ["c0:instantaneo", "q0:2:rms", "q0:0:rms"])
    da_fase = saiu["c0:instantaneo"]["pico"]
    assert saiu["q0:2:rms"]["pico"] == pytest.approx(da_fase)
    assert saiu["q0:0:rms"]["pico"] == pytest.approx(da_fase)
    # e o pico da fase é mesmo o da fase, não o da componente
    assert da_fase == pytest.approx(PICO / math.sqrt(2), rel=1e-2)
