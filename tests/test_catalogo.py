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
    corrompe 3I0, V1 e a localização de falta **sem dar erro nenhum**. Por isso
    ele aparece ao lado do canal: é a conferência, não um sinal a mais."""
    por_id = {s.id: s for s in catalogo.de_registro(trifasico())}
    canal = por_id["c0:instantaneo"]
    assert canal.nome == "Current IA"        # o nome do fabricante
    assert canal.familia == "canal"
    assert canal.fundamental == "IA"         # o vínculo que deduzimos


def test_canal_que_nao_reconhecemos_diz_que_nao_reconheceu():
    """Ficar em branco é a resposta certa: um palpite com cara de vínculo é
    pior que vínculo nenhum."""
    r = trifasico()
    canais = list(r.analog_channels)
    canais.append(AnalogChannel(index=6, name="VDC1", unit="V", phase=""))
    r.analog_channels = tuple(canais)
    r.analog = np.vstack([r.analog, np.full((1, r.analog.shape[1]), 125.0)])

    por_id = {s.id: s for s in catalogo.de_registro(r)}
    assert por_id["c6:instantaneo"].fundamental == ""
    # E as contas nossas continuam disponíveis para ele, com o nome do arquivo.
    assert por_id["v6:rms"].nome == "VDC1 RMS"


def test_a_lista_do_OscLab_nao_repete_o_canal():
    """`IA` não está lá: são as mesmas amostras do canal, e o vínculo já
    aparece do lado do IED. O que o OscLab oferece é o que o relé NÃO gravou."""
    por_id = {s.id: s for s in catalogo.de_registro(trifasico())}
    nossos = {s.nome for s in por_id.values() if s.familia == "calculado"}
    assert "IA" not in nossos
    assert {"IA RMS", "IA 60Hz", "IA 60Hz RMS"} <= nossos


def test_a_grandeza_esta_no_id_e_nao_depende_do_botao_de_filtro():
    """`IA RMS` não pode mudar de significado com um clique em outro lugar da
    tela. Cada variante é um sinal próprio, com id próprio."""
    por_id = {s.id: s for s in catalogo.de_registro(trifasico())}
    assert por_id["v0:rms"].nome == "IA RMS"
    assert por_id["v0:filtrado"].nome == "IA 60Hz"
    assert por_id["v0:fundamental"].nome == "IA 60Hz RMS"

    r = trifasico()
    # Mesmo com o filtro ligado no gráfico, `IA RMS` continua eficaz
    # verdadeiro — e não a fundamental.
    pacote = janela.montar(r, filtro=True, colunas=100_000,
                           layout=com_correntes(r, ["v0:rms"]))
    assert sinal(pacote["paineis"][0], "v0:rms")["sinal"] == "IA RMS"


def test_registro_ja_filtrado_oferece_SO_o_que_existe_de_verdade():
    """Num registro que o relé já filtrou, `IA RMS` — eficaz verdadeiro, com
    harmônicos — não existe: não há harmônico para incluir. O que existe é
    `IA 60Hz` (o próprio canal, que já É a componente de 60 Hz) e o eficaz
    dele. Oferecer `IA RMS` ali seria prometer uma medida que o arquivo não
    permite."""
    r = trifasico()
    r.filtering = Filtering.FILTRADO
    por_id = {s.id: s for s in catalogo.de_registro(r)}
    assert "v0:rms" not in por_id
    assert por_id["v0:filtrado"].nome == "IA 60Hz"
    assert por_id["v0:fundamental"].nome == "IA 60Hz RMS"

    # E a CONTA não é a que o nome sugere: filtrar de novo atrasaria um ciclo.
    assert por_id["v0:filtrado"].conta == "instantaneo"
    assert por_id["v0:fundamental"].conta == "rms"


def test_num_registro_filtrado_o_60Hz_e_o_proprio_canal():
    """Se a conta fosse aplicada de novo, a curva começaria um ciclo depois e
    ficaria atrasada em relação à onda do próprio gráfico."""
    r = trifasico()
    r.filtering = Filtering.FILTRADO
    pacote = janela.montar(r, colunas=100_000,
                           layout=com_correntes(r, ["v0:filtrado"]))
    painel = pacote["paineis"][0]
    serie = sinal(painel, "v0:filtrado")["serie"]
    assert serie[0] is not None          # a filtrada de verdade começaria vazia
    assert serie[0] == painel["sinais"][0]["serie"][0]


def test_o_que_os_botoes_do_painel_pegam_e_o_que_eles_nao_pegam():
    """A divisão que decide o significado de metade da tela.

    Um canal do IED é a amostra crua, e os botões do painel — o filtro e a
    medida — existem justamente para dizer o que fazer com ela: com o filtro
    ligado, `IA` vira `IA 60Hz` e a curva começa um ciclo depois, porque não há
    janela antes disso.

    Um sinal do OscLab, não. `IA RMS` foi escolhido pelo nome, com grandeza
    dentro do nome, e não pode mudar de significado com um clique em outro
    lugar da tela — foi o que o usuário pediu quando disse que o sinal posto à
    mão carrega a própria medida.
    """
    r = trifasico()
    r.filtering = Filtering.BRUTO        # senão `IA RMS` nem seria oferecido
    pacote = janela.montar(r, filtro=True, colunas=100_000,
                           layout=[arranjo.analogico(["c0:instantaneo",
                                                      "v0:rms"])])
    painel = pacote["paineis"][0]

    do_ied = sinal(painel, "c0:instantaneo")
    assert do_ied["sinal"] == "IA 60Hz"          # o botão pegou
    assert do_ied["serie"][0] is None            # e a janela do filtro aparece

    do_osclab = sinal(painel, "v0:rms")
    assert do_osclab["sinal"] == "IA RMS"        # o botão não pegou


def test_cada_conjunto_trifasico_rende_as_tres_componentes():
    componentes = {s.id: s.nome for s in catalogo.de_registro(trifasico())
                   if s.id.startswith("q")}
    assert componentes == {"q0:0:rms": "3I0", "q0:1:rms": "I1", "q0:2:rms": "I2",
                           "q1:0:rms": "3V0", "q1:1:rms": "V1", "q1:2:rms": "V2"}


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
    assert "3I0" not in componentes
    assert "3V0" in componentes       # as tensões continuam completas


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
    assert "3I0" not in componentes
    assert "3V0" in componentes


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
    assert linha["sinal"] == "IA RMS"
    assert linha["familia"] == "calculado"      # a tela some com o nome do arquivo
    # E o canal de origem continua no pacote, para o hover e para o aviso de
    # TC/TP: quem confere precisa saber de onde a conta saiu.
    assert linha["nome"] == "Current IA"
    assert linha["indice"] == 0

    cru = janela.montar(r, colunas=200,
                        layout=[arranjo.analogico(["c0:instantaneo"])])
    assert cru["paineis"][0]["sinais"][0]["familia"] == "canal"
