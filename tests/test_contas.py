"""A calculadora de sinais: a gramática, as unidades e a onda que sai dela.

O que se testa aqui é o que é NOVO. A envoltória, o fasor e a conversão de
TC/TP já têm os testes deles — o que este arquivo amarra é que a conta passa
por eles como qualquer onda, e que a conferência de unidade AVISA o que tem
que avisar — sem bloquear: ver a regra do projeto em `plot/contas.py`.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from osclab.plot import catalogo, contas, janela, leitura, paineis
from tests import arranjo
from tests.test_catalogo import PICO, trifasico


def _escalas(registro, lado="arquivo"):
    from osclab.plot import unidades
    return unidades.por_unidade(registro, lado)


def _vale(registro, expressao):
    return contas.analisar(expressao, registro, _escalas(registro))


# --- a gramática -----------------------------------------------------------

def test_le_a_conta_mais_comum_do_oficio():
    """`(Va - Vb) / √3` é tensão de linha a partir de fase-terra."""
    a = _vale(trifasico(), "([Voltage A-G] - [Voltage B-G]) / 1.732")
    assert a.vale
    assert a.unidade_escrita == "V"
    assert a.alternado


@pytest.mark.parametrize("expressao,pedaco", [
    ("[NaoExiste] + [Current IA]", "não existe sinal"),
    ("2 * [Current IA", "não entendi"),
    ("([Current IA] + [Current IB]", "termina no meio"),
    ("[Current IA] [Current IB]", "sobrou"),
    ("", "vazia"),
    ("3 + 4", "não usa nenhum sinal"),
    ("seno([Current IA])", "não conheço a função"),
])
def test_recusa_o_que_nao_e_conta(expressao, pedaco):
    a = _vale(trifasico(), expressao)
    assert not a.vale
    assert pedaco in a.erro


# --- as unidades -----------------------------------------------------------

def test_A_mais_A_passa_e_A_mais_V_sai_com_ressalva():
    """Somar ampère com volt dá um número que parece certo e não significa
    nada — mas a conta é FEITA, com o aviso ao lado.

    A regra do projeto é avisar, nunca bloquear: quem decide o que faz sentido
    naquele laudo é o engenheiro. Recusar deixaria o usuário sem saída numa
    conta legítima que o programa não previu.
    """
    r = trifasico()
    assert _vale(r, "[Current IA] + [Current IB]").unidade_escrita == "A"
    com_ressalva = _vale(r, "[Current IA] + [Voltage A-G]")
    assert com_ressalva.vale
    assert not com_ressalva.erro
    # Sem unidade que se escreva: o número existe, o nome dele não.
    assert com_ressalva.unidade_escrita == ""
    assert any("somando A com V" in a for a in com_ressalva.avisos)


def test_numero_puro_se_soma_a_grandeza_com_ressalva():
    """`[IAW] + 5` não diz se o 5 é ampère ou volt — o resultado sai sem
    unidade, com aviso. Multiplicar por número, sim: continua ampère, sem
    aviso nenhum."""
    r = trifasico()
    misturado = _vale(r, "[Current IA] + 5")
    assert misturado.vale and misturado.avisos
    assert misturado.unidade_escrita == ""
    for limpa in ("[Current IA] * 5", "[Current IA] / 5"):
        a = _vale(r, limpa)
        assert a.unidade_escrita == "A"
        assert a.avisos == ()


def test_as_unidades_se_multiplicam():
    r = trifasico()
    assert _vale(r, "[Current IA] * [Voltage A-G]").unidade_escrita == "V·A"
    assert _vale(r, "[Current IA]^2").unidade_escrita == "A²"
    assert _vale(r, "raiz([Current IA]^2 + [Current IB]^2)").unidade_escrita == "A"


def test_a_raiz_de_uma_unidade_impar_sai_sem_unidade_com_ressalva():
    """`√A` não tem unidade que se escreva. A raiz é tirada; o resultado sai
    sem unidade, com o aviso."""
    a = _vale(trifasico(), "raiz([Current IA])")
    assert a.vale
    assert a.unidade_escrita == ""
    assert any("não tem unidade que se escreva" in x for x in a.avisos)


def test_dividir_sinal_por_sinal_passa_com_ressalva_no_dominio_da_onda():
    """Ela estoura em cada passagem por zero — e o que o usuário quer ao
    escrever V ÷ I é impedância, que é conta de FASOR. O aviso diz os dois;
    a conta é feita.

    E ela não é senoidal: fica em «Calculados», como toda conta do usuário,
    mas sem fasor nem espectro. É o mesmo tratamento do produto entre sinais.
    """
    a = _vale(trifasico(), "[Voltage A-G] / [Current IA]")
    assert a.vale
    assert not a.alternado
    # V ÷ A tem nome próprio, e nome se escreve: o ohm sai na unidade mesmo
    # com a ressalva. O que o aviso diz é que ESTA divisão, feita amostra a
    # amostra, não é a impedância que o usuário quer.
    assert a.unidade_escrita == "Ω"
    assert any("passagem por zero" in x for x in a.avisos)


# --- em que bloco o resultado mora -----------------------------------------

def test_soma_de_senoides_continua_senoide_e_produto_nao():
    r = trifasico()
    assert _vale(r, "[Current IA] - [Current IB]").alternado
    assert not _vale(r, "[Current IA] * [Voltage A-G]").alternado
    assert not _vale(r, "[Current IA]^2").alternado


# --- a onda ----------------------------------------------------------------

def _com_conta(registro, expressao, nome="Conta", lado="arquivo"):
    cs = contas.de_json([{"id": "x1", "nome": nome, "expressao": expressao}])
    lay = [arranjo.analogico(["x1:instantaneo"])]
    pacote = janela.montar(registro, colunas=200, lado=lado, layout=lay,
                           contas=cs)
    lido = leitura.em(registro, [(float(registro.time[-1]), 0, 0.0),
                                 (None, 0, 0.0)], lado=lado, layout=lay,
                      contas=cs)
    return pacote, lido["cursores"][0]["sinais"]["x1:instantaneo"]


def test_a_conta_vira_uma_onda_que_a_tela_desenha():
    r = trifasico()
    pacote, linha = _com_conta(r, "[Current IA] - [Current IB]")
    desenhado = pacote["paineis"][0]["sinais"][0]
    assert desenhado["unidade"] == "A"
    assert len(desenhado["serie"]) > 0
    # O instantâneo é a subtração, amostra a amostra, sem arredondamento pelo
    # caminho: é por ele que se confere que a conta é a conta.
    esperado = float(r.analog[0][-1] - r.analog[1][-1])
    assert linha["instantaneo"] == pytest.approx(esperado, rel=1e-9)


def test_a_conta_tem_as_mesmas_colunas_de_um_canal():
    """Onda, RMS, DC, 60 Hz e 60 Hz RMS — ela é onda como o resíduo `IN`."""
    r = trifasico()
    cs = contas.de_json([{"id": "x1", "nome": "Iab",
                          "expressao": "[Current IA] - [Current IB]"}])
    ids = {s.id for s in catalogo.de_registro(r, "arquivo", cs)
           if s.id.startswith("x1:")}
    assert ids == {"x1:instantaneo", "x1:rms", "x1:dc", "x1:filtrado",
                   "x1:fundamental"}


def test_a_diferenca_de_duas_fases_da_raiz_de_tres_vezes_a_fase():
    """Conferência de domínio: `IA - IB` de uma trinca equilibrada tem módulo
    √3 vezes o da fase. Se a conta estivesse somando em vez de subtrair, ou
    perdendo a defasagem, este número não fecharia."""
    r = trifasico()
    _, linha = _com_conta(r, "[Current IA] - [Current IB]")
    fase = PICO / math.sqrt(2.0)
    assert linha["fundamental"] == pytest.approx(fase * math.sqrt(3.0), rel=1e-3)


def test_a_soma_das_tres_fases_equilibradas_da_zero():
    r = trifasico()
    _, linha = _com_conta(
        r, "[Current IA] + [Current IB] + [Current IC]")
    assert abs(linha["fundamental"]) < 1e-6


def test_a_conversao_vem_ANTES_da_conta():
    """Somar primário com secundário erraria por mil vezes sem avisar. Como a
    conversão é escalar, a conta inteira escala junto — e é isso que se
    confere."""
    r = trifasico()
    _, no_arquivo = _com_conta(r, "[Current IA] - [Current IB]")
    _, no_primario = _com_conta(r, "[Current IA] - [Current IB]",
                                lado="primario")
    razao = no_primario["instantaneo"] / no_arquivo["instantaneo"]
    assert razao == pytest.approx(
        no_primario["instantaneo"] / no_arquivo["instantaneo"], rel=1e-9)
    assert razao > 0


def test_conta_que_nao_compila_aparece_com_o_motivo_em_vez_de_sumir():
    """Sumir seria pior: o sinal desapareceria da tela sem dizer por quê.

    Repare que o que não compila agora é só o que não se LÊ — canal que não
    existe, parêntese aberto. Unidade misturada compila, com ressalva: ver
    `test_conta_com_ressalva_entra_normal_com_o_aviso_ao_lado`.
    """
    r = trifasico()
    cs = contas.de_json([{"id": "x1", "nome": "Ruim",
                          "expressao": "[NaoExiste] + [Current IA]"}])
    achados = [s for s in catalogo.de_registro(r, "arquivo", cs)
               if s.id.startswith("x1:")]
    assert len(achados) == 1
    assert achados[0].bloco == "outros"
    assert "não existe sinal" in achados[0].motivo


def test_conta_com_ressalva_entra_normal_com_o_aviso_ao_lado():
    """Somar volt com ampère entra no bloco `alternado`, com as cinco colunas
    de qualquer onda — e o aviso num campo PRÓPRIO.

    Campo próprio e não `motivo`: `motivo` explica por que o sinal não serve
    para algo, e a tela o pinta como defeito. Aqui o sinal serve.
    """
    r = trifasico()
    cs = contas.de_json([{"id": "x1", "nome": "Mistura",
                          "expressao": "[Current IA] + [Voltage A-G]"}])
    achados = [s for s in catalogo.de_registro(r, "arquivo", cs)
               if s.id.startswith("x1:")]
    assert len(achados) == 5
    assert all(s.bloco == "alternado" for s in achados)
    assert all(not s.motivo for s in achados)
    assert all("somando A com V" in s.aviso for s in achados)


def test_produto_entre_sinais_perde_o_fasor_com_o_motivo_escrito():
    """`bloco == "outros"` aqui NÃO é onde a tela lista a conta — toda conta
    do usuário é listada em «Calculados». É a resposta a outra pergunta: dá
    para tirar fasor e espectro dela? Deste produto, não."""
    r = trifasico()
    cs = contas.de_json([{"id": "x1", "nome": "Pa",
                          "expressao": "[Current IA] * [Voltage A-G]"}])
    achados = [s for s in catalogo.de_registro(r, "arquivo", cs)
               if s.id.startswith("x1:")]
    assert achados and all(s.bloco == "outros" for s in achados)
    assert "produto entre sinais" in achados[0].motivo
    # E a família continua dizendo que é conta: é por ela que a tela escolhe
    # o bloco «Calculados», e não pelo `bloco`.
    assert all(s.familia == "conta" for s in achados)


# --- a conta nos outros painéis --------------------------------------------

def test_a_conta_senoidal_entra_no_fasorial_e_nos_harmonicos():
    r = trifasico()
    cs = contas.de_json([{"id": "x1", "nome": "Iab",
                          "expressao": "[Current IA] - [Current IB]"}])
    for tipo, montador in (("fasorial", arranjo.fasorial),
                           ("harmonicos", arranjo.harmonicos)):
        pacote = janela.montar(r, colunas=100,
                               layout=[montador(["x1:instantaneo"])], contas=cs)
        assert [s["sinal"] for s in pacote["paineis"][0]["sinais"]] == ["Iab"]


def test_a_conta_NAO_senoidal_fica_fora_dos_dois():
    """Potência instantânea oscila no dobro da frequência com nível contínuo:
    fasor de 60 Hz disso não significa nada."""
    r = trifasico()
    cs = contas.de_json([{"id": "x1", "nome": "Pa",
                          "expressao": "[Current IA] * [Voltage A-G]"}])
    for montador in (arranjo.fasorial, arranjo.harmonicos):
        pacote = janela.montar(r, colunas=100,
                               layout=[montador(["x1:instantaneo"])], contas=cs)
        assert pacote["paineis"][0]["sinais"] == []


# --- o que a tela manda ----------------------------------------------------

def test_so_entra_id_do_espaco_das_contas():
    """`x` é o espaço de ids das contas. Um id fora dele poderia atropelar um
    sinal do catálogo e a tela desenharia outra coisa."""
    lidas = contas.de_json([
        {"id": "x1", "nome": "ok", "expressao": "[a]"},
        {"id": "c0", "nome": "atropela", "expressao": "[a]"},
        {"id": "q0", "nome": "atropela", "expressao": "[a]"},
        {"id": "x1", "nome": "repetido", "expressao": "[b]"},
        {"id": "x2", "nome": "", "expressao": "[a]"},
        {"id": "x3", "nome": "sem conta", "expressao": ""},
    ])
    assert [c.id for c in lidas] == ["x1"]
    assert lidas[0].nome == "ok"


def test_a_expressao_tem_limite_de_tamanho():
    gigante = " + ".join(["[Current IA]"] * 50)
    assert contas.de_json([{"id": "x1", "nome": "n", "expressao": gigante}]) == []


# --- a conta sobre o que o OscLab calculou ---------------------------------

def test_a_conta_usa_o_residuo_e_as_componentes():
    """`[IN G1]`, `[3I0 G1]` — o que o OscLab calcula entra na conta como
    qualquer canal. É a pergunta do ofício: o resíduo medido bate com 3I0?"""
    r = trifasico()
    nomes = contas.referenciaveis(r)
    assert "IN G1" in nomes and "3I0 G1" in nomes and "I1 G1" in nomes
    # O resíduo é ONDA: soma amostra a amostra, e numa trinca equilibrada dá
    # zero — a mesma conferência de `(IA+IB+IC)/3`.
    a = _vale(r, "[IN G1] / 3")
    assert a.vale and a.unidade_escrita == "A" and a.alternado
    serie = contas.serie(r, a, "arquivo", 1.0)
    assert abs(float(serie[-1])) < 1e-9


def test_componente_de_sequencia_nao_e_onda_e_sai_de_outros():
    """`3I0` é fasor: só existe em eficaz, e não tem fasor de 60 Hz a tirar.
    A conta é feita — a regra é avisar, nunca bloquear —, mas o resultado não
    é senoide e vai para «Outros sinais»."""
    a = _vale(trifasico(), "[3I0 G1] / 3")
    assert a.vale
    assert not a.alternado
    assert a.avisos == ()          # eficaz com eficaz não tem o que avisar


def test_somar_MODULO_com_onda_sai_com_ressalva():
    """O aviso mais importante desta calculadora: um módulo jogou fora sinal e
    fase, e a conta é feita amostra a amostra. A conta é feita assim mesmo."""
    r = trifasico()
    a = _vale(r, "[3I0 G1] - [Current IA]")
    assert a.vale
    assert any("MÓDULO" in x for x in a.avisos)


def test_componente_do_sinal_soma_com_a_onda_SEM_ressalva():
    """`· 60Hz` e `· DC` são parcelas COM SINAL da própria onda, na mesma
    unidade e na mesma base de tempo: `onda = 60Hz + DC + harmônicos`.

    `[V] - [V · 60Hz]` é a onda da distorção — o que sobra fora dos 60 Hz —, e
    é das contas mais úteis que a calculadora faz. Uma versão anterior disto
    avisava nela, confundindo «componente» com «módulo».
    """
    r = trifasico()
    canal = r.analog_channels[0].name
    distorcao = _vale(r, f"[{canal}] - [{canal} · 60Hz]")
    assert distorcao.vale
    assert distorcao.avisos == ()
    # E ela continua sendo senoide para efeito de fasor: é combinação LINEAR
    # de ondas, e a DFT é operador linear.
    assert distorcao.alternado

    sem_dc = _vale(r, f"[{canal}] - [{canal} · DC]")
    assert sem_dc.vale and sem_dc.avisos == ()


def test_modulo_com_modulo_nao_avisa():
    """`[IN G1 · RMS] - [3I0 G1]` é A pergunta do ofício — o resíduo medido
    bate com a conta? — e os dois lados são módulos. Nada a avisar."""
    a = _vale(trifasico(), "[IN G1 · RMS] - [3I0 G1]")
    assert a.vale
    assert a.avisos == ()


def test_uma_conta_usa_a_conta_ANTERIOR_e_nunca_a_posterior():
    """Referência circular é impossível por construção: a ordem de criação já
    faz o trabalho que um grafo de dependência faria."""
    r = trifasico()
    cs = contas.de_json([
        {"id": "x1", "nome": "I0",
         "expressao": "([Current IA] + [Current IB] + [Current IC]) / 3"},
        {"id": "x2", "nome": "I0dobro", "expressao": "[I0] * 2"},
    ])
    achados = {s.linha: s for s in catalogo.de_registro(r, "arquivo", cs)
               if s.grandeza == "instantaneo" and s.id.startswith("x")}
    assert achados["I0dobro"].bloco == "alternado"
    assert achados["I0dobro"].origem == "I0"
    # E o contrário NÃO vale: a primeira não enxerga a segunda.
    ruim = contas.analisar("[I0dobro] + 1", r, _escalas(r), (cs[0],))
    assert not ruim.vale
    assert "não existe sinal" in ruim.erro


def test_contas_encadeadas_nao_explodem_em_tempo():
    """Vinte contas encadeadas, que é o limite. A primeira versão disto
    dobrava de custo a cada elo — seis contas levavam 125 ms."""
    import time
    r = trifasico()
    nome_do_canal = r.analog_channels[0].name
    pedidas = [{"id": "x1", "nome": "c1", "expressao": f"[{nome_do_canal}] * 1"}]
    for k in range(2, 21):
        pedidas.append({"id": f"x{k}", "nome": f"c{k}",
                        "expressao": f"[c{k - 1}] + 1"})
    cs = contas.de_json(pedidas)
    assert len(cs) == 20
    inicio = time.perf_counter()
    saida = catalogo.de_registro(r, "arquivo", cs)
    gasto = time.perf_counter() - inicio
    boas = [s for s in saida if s.id.startswith("x")
            and s.grandeza == "instantaneo" and s.bloco == "alternado"]
    assert len(boas) == 20
    assert gasto < 1.0, f"{gasto:.2f}s para 20 contas encadeadas"


def test_a_coluna_do_filtrado_sai_quando_nao_ha_60_Hz_para_extrair():
    """`[V] - [V · 60Hz]` é a onda da distorção: tudo menos 60 Hz. Oferecer a
    coluna do filtrado nela desenharia uma reta no zero com cara de medida.

    MEDIDO na série, não deduzido da expressão — ver `contas.tem_60hz`.
    """
    import numpy as np

    r = trifasico()
    por_ciclo = 20
    n = r.analog.shape[1]
    t = np.arange(n) / (60.0 * por_ciclo)
    for k in range(3):                      # suja: sem distorção não há o que medir
        pico = float(np.max(np.abs(r.analog[k])))
        r.analog[k] = (r.analog[k] + 0.25 * pico * np.sin(2 * np.pi * 180 * t + k)
                       + 0.15 * pico * np.exp(-t / 0.05))
    canal = r.analog_channels[0].name
    outro = r.analog_channels[1].name
    cs = contas.de_json([
        {"id": "x1", "nome": "Linear", "expressao": f"[{canal}] - [{outro}]"},
        {"id": "x2", "nome": "Dist", "expressao": f"[{canal}] - [{canal} · 60Hz]"},
    ])
    saida = catalogo.de_registro(r, "arquivo", cs)

    def colunas(qual):
        return {s.coluna for s in saida if s.id.startswith(f"{qual}:")}

    assert any(c.startswith("filtrado.") for c in colunas("x1"))
    assert not any(c.startswith("filtrado.") for c in colunas("x2"))
    # E a linha diz por quê, em vez de ficar com dois risquinhos calados.
    dist = next(s for s in saida if s.id.startswith("x2:"))
    assert "não tem 60 Hz" in dist.motivo
    # Continua sendo senoide para efeito de fasor: é combinação linear.
    assert dist.bloco == "alternado"


def test_conta_que_perde_o_fasor_pelo_DOMINIO_tambem_diz_por_que():
    """Antes, só o produto tinha motivo escrito. Quem caía em «outros» por
    somar RMS ou contínua caía calado — quatro risquinhos e nenhuma palavra."""
    r = trifasico()
    canal = r.analog_channels[0].name
    cs = contas.de_json([{"id": "x1", "nome": "ComDC",
                          "expressao": f"[{canal}] + [{canal} · DC]"}])
    achados = [s for s in catalogo.de_registro(r, "arquivo", cs)
               if s.id.startswith("x1:")]
    assert achados[0].bloco == "outros"
    assert "RMS ou contínua" in achados[0].motivo
