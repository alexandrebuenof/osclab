"""Canal ligado × entrada aberta, e o que some da tela por causa disso.

O que se afirma aqui não é um número bonito: é que **as duas condições são
necessárias**. Há um teste para cada uma sozinha errando num caso real —
a tensão da bateria, que não tem 60 Hz e é canal de verdade, e o TC de neutro,
que é minúsculo e é canal de verdade.

E há um teste para a regra que custou uma descoberta no SEL-487E: esconder duas
fases de três é pior que não esconder nenhuma.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from osclab.analysis import presenca
from osclab.formats import conjuntos
from osclab.formats.base import AnalogChannel, Record

TAXA = 1920.0          # 32 amostras por ciclo a 60 Hz
N = 128                # quatro ciclos
PICO = 100.0


def _t() -> np.ndarray:
    return np.arange(N) / TAXA


def senoide(pico: float = PICO, grau: float = 0.0) -> np.ndarray:
    return pico * np.cos(2 * np.pi * 60.0 * _t() - np.deg2rad(grau))


def ruido(pico: float = 1.0, semente: int = 7) -> np.ndarray:
    """Entrada aberta: o conversor lendo a si mesmo. Semente fixa, de propósito."""
    return np.random.default_rng(semente).uniform(-pico, pico, N)


def registro(*canais: tuple[str, str, np.ndarray]) -> Record:
    r = Record(source=Path("x"), format_name="teste")
    r.analog_channels = tuple(
        AnalogChannel(index=i, name=nome, unit=unidade)
        for i, (nome, unidade, _) in enumerate(canais))
    r.analog = np.array([v for _, _, v in canais], dtype=np.float64)
    r.time = _t()
    return r


def trinca(grandeza: str, terminal: str, unidade: str,
           fazer) -> list[tuple[str, str, np.ndarray]]:
    """Uma trinca na nomenclatura da SEL: `IAW`, `IBW`, `ICW`.

    Com `terminal` vazio saem `IA`, `IB`, `IC` — o registro de uma trinca só.
    """
    return [(f"{grandeza}{f}{terminal}", unidade, fazer(g))
            for f, g in (("A", 0.0), ("B", 120.0), ("C", 240.0))]


def nomes(reg: Record, indices) -> set[str]:
    return {c.name for c in reg.analog_channels if c.index in indices}


# ---------------------------------------------------------------------------
# As duas condições
# ---------------------------------------------------------------------------

def test_a_trinca_que_e_so_ruido_nao_esta_ligada_em_nada():
    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 *trinca("I", "X", "A", lambda g: ruido(1.0)))
    assert nomes(r, presenca.sem_sinal(r)) == {"IAX", "IBX", "ICX"}


def test_a_TENSAO_DA_BATERIA_nao_some_mesmo_sem_60_Hz():
    """132 V contínuos, fundamental ZERO — e é o canal mais real que existe.

    Se a regra fosse só "tem 60 Hz?", ela sumiria. O que a salva é ser o maior
    canal em volts do registro.
    """
    r = registro(*trinca("V", "Y", "kV", lambda g: senoide(10.0, g)),
                 ("VDC1", "V", np.full(N, 132.0)))
    assert presenca.sem_sinal(r) == frozenset()


def test_o_canal_PEQUENO_E_REAL_nao_some():
    """Um TC de neutro lendo 2 A com as fases em 100 A é 2 % do maior — e é
    medição legítima. O que o salva é ter 60 Hz dentro."""
    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 ("IN", "A", senoide(2.0)))
    assert presenca.sem_sinal(r) == frozenset()


def test_registro_sem_amostra_nao_opina():
    r = Record(source=Path("x"), format_name="teste")
    assert presenca.sem_sinal(r) == frozenset()


def test_taxa_que_nao_fecha_um_ciclo_nao_opina():
    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)))
    r.time = np.arange(N) / 120.0        # 2 amostras por ciclo
    assert presenca.sem_sinal(r) == frozenset()


# ---------------------------------------------------------------------------
# O que de fato some da tela: só trinca inteira
# ---------------------------------------------------------------------------

def test_SO_SOME_TRINCA_INTEIRA_nunca_duas_fases_de_tres():
    """Aconteceu no SEL-487E: o `ICU` passou raspando do limiar e as outras
    duas fases não. Esconder duas de três deixaria uma fase solta na tela, com
    cara de que as outras não existem."""
    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 ("IAX", "A", ruido(1.0)), ("IBX", "A", ruido(1.0, 9)),
                 ("ICX", "A", senoide(30.0, 240.0)))      # esta está viva
    assert len(presenca.sem_sinal(r)) == 2                # a medição acusa duas
    assert conjuntos.canais_sem_sinal(r) == frozenset()   # e a tela não esconde


def test_canal_SOLTO_em_zero_nao_some():
    """A tensão residual `VNG` de um Schneider marca 0,14 V porque não há falta
    à terra. Esse zero é a resposta que alguém foi procurar no arquivo."""
    r = registro(*trinca("V", "Y", "V", lambda g: senoide(PICO, g)),
                 ("VNG", "V", ruido(0.5)))
    assert "VNG" in nomes(r, presenca.sem_sinal(r))
    assert conjuntos.canais_sem_sinal(r) == frozenset()


def test_o_vao_DESLIGADO_inteiro_nao_some():
    """Registro em que toda a corrente está em zero: o disjuntor estava aberto.
    Aí o zero é a informação, e não há com que comparar."""
    r = registro(*trinca("I", "", "A", lambda g: np.zeros(N)))
    assert conjuntos.canais_sem_sinal(r) == frozenset()


# ---------------------------------------------------------------------------
# O efeito no nome: é para isto que tudo isto existe
# ---------------------------------------------------------------------------

def test_TER_SINAL_ou_nao_NAO_MUDA_o_nome_da_trinca():
    """Um terminal que ninguém cabeou é uma trinca como as outras e recebe o
    próximo número. O que ele não faz é aparecer no gráfico de abertura — e
    isso é assunto do painel, não do nome.
    """
    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 *trinca("I", "X", "A", lambda g: ruido(1.0)))
    achados = {c.nome: c for c in conjuntos.de_registro(r)}
    assert achados["I*W"].rotulo == "G1"
    assert achados["I*X"].rotulo == "G2"
    assert achados["I*X"].sem_sinal is True
    assert all(c.origem_do_rotulo == conjuntos.OrigemDoRotulo.NUMERO
               for c in achados.values())


def test_com_uma_trinca_SO_o_grupo_ainda_se_chama_G1():
    """Não há o que distinguir, e por muito tempo o conjunto ficava sem apelido
    por isso. Hoje tem nome de qualquer jeito: o grupo é editável, e o editor,
    o rodapé do gráfico e o nome do sinal têm que chamá-lo da mesma coisa."""
    r = registro(*trinca("I", "", "A", lambda g: senoide(PICO, g)))
    assert conjuntos.de_registro(r)[0].rotulo == "G1"


def test_TRES_trincas_seguem_a_numeracao_mesmo_sem_sinal():
    """O SEL-487E tem cinco terminais de TC e três estão livres. Os cinco
    entram na mesma sequência."""
    r = registro(*trinca("I", "S", "A", lambda g: senoide(PICO, g)),
                 *trinca("I", "W", "A", lambda g: ruido(1.0)),
                 *trinca("I", "X", "A", lambda g: ruido(1.0, 11)))
    rotulos = {c.nome: c.rotulo for c in conjuntos.de_registro(r)}
    assert rotulos == {"I*S": "G1", "I*W": "G2", "I*X": "G3"}


# ---------------------------------------------------------------------------
# O que chega na tela
# ---------------------------------------------------------------------------

def _so_correntes(reg: Record):
    from osclab.plot import paineis
    return next(p for p in paineis.padrao(reg)
                if p.tipo == paineis.ANALOGICO and p.sinais)


def test_o_arranjo_padrao_nao_desenha_a_reserva():
    """O pedido: o SEL-451 abria com seis correntes, três delas uma reta em
    zero. Abre com três."""
    from osclab.plot import paineis

    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 *trinca("I", "X", "A", lambda g: ruido(1.0)))
    desenhados = _so_correntes(r).sinais
    assert desenhados == ("c0:instantaneo", "c1:instantaneo", "c2:instantaneo")
    assert paineis.padrao(r)[0].nome.startswith("Correntes")


def test_o_canal_sem_sinal_continua_INTEIRO_no_catalogo():
    """Some do desenho, nunca do programa: quem quiser conferir que a entrada
    está mesmo aberta precisa poder pôr a curva na tela."""
    from osclab.plot import catalogo

    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 *trinca("I", "X", "A", lambda g: ruido(1.0)))
    ids = {s.id for s in catalogo.de_registro(r)}
    assert {"c3:instantaneo", "c4:instantaneo", "c5:instantaneo"} <= ids


def test_a_componente_da_trinca_SEM_SINAL_existe_e_fica_ESCONDIDA():
    """Mesma regra dos canais dela, e pelo mesmo motivo.

    Fortescue aplicado a ruído de conversor não significa nada, e por isso a
    componente da trinca morta não aparece por padrão — quem a esconde é a
    caixa «ocultar sinais nulos», pelo campo `sem_sinal`. Mas ela EXISTE: fazer
    o sinal sumir do catálogo deixaria a lista escondida pela metade, e
    Fortescue sobre uma trinca legitimamente em zero (o outro lado de um trafo
    energizado por um só) dá zero, que é uma resposta e não um erro."""
    from osclab.plot import catalogo

    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 *trinca("I", "X", "A", lambda g: ruido(1.0)))
    componentes = [s for s in catalogo.de_registro(r) if s.id.startswith("q")]
    visiveis = {s.nome for s in componentes if not s.sem_sinal}
    ocultas = {s.nome for s in componentes if s.sem_sinal}
    resíduo = ("IN {g}", "IN {g} · RMS", "IN {g} · DC", "IN {g} · 60Hz",
               "IN {g} · 60Hz RMS")
    assert visiveis == {"3I0 G1", "I1 G1", "I2 G1",
                        *(x.format(g="G1") for x in resíduo)}
    assert ocultas == {"3I0 G2", "I1 G2", "I2 G2",
                       *(x.format(g="G2") for x in resíduo)}


def test_o_id_DA_COMPONENTE_nao_escorrega_quando_uma_trinca_some():
    """Os ids `q{i}` são POSIÇÃO na lista de conjuntos. Se pular a reserva
    renumerasse o resto, todo arranjo já salvo passaria a apontar para a trinca
    errada — e o gráfico abriria com a curva de outro equipamento, sem erro
    nenhum na tela.
    """
    from osclab.plot import catalogo

    # A reserva vem PRIMEIRO no arquivo, então ela é o conjunto 0.
    r = registro(*trinca("I", "X", "A", lambda g: ruido(1.0)),
                 *trinca("I", "W", "A", lambda g: senoide(PICO, g)))
    viva = [s.id for s in catalogo.de_registro(r)
            if s.id.startswith("q") and not s.sem_sinal]
    assert all(x.startswith("q1:") for x in viva), viva


def test_o_aviso_do_cabecalho_ENCOLHE_quando_o_canal_volta():
    """Um aviso que não acompanha o que se vê deixa de ser lido."""
    from dataclasses import replace

    from osclab.plot import janela, paineis

    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 *trinca("I", "X", "A", lambda g: ruido(1.0)))

    pacote = janela.montar(r, colunas=120)
    assert [x["nome"] for x in pacote["sem_sinal"]] == ["IAX", "IBX", "ICX"]
    assert all(x["unidade"] == "A" for x in pacote["sem_sinal"])

    arranjo = paineis.padrao(r)
    arranjo[0] = replace(arranjo[0],
                         sinais=arranjo[0].sinais + ("c3:instantaneo",))
    de_volta = janela.montar(r, colunas=120, layout=arranjo)
    assert [x["nome"] for x in de_volta["sem_sinal"]] == ["IBX", "ICX"]


def test_o_canal_sem_sinal_que_volta_diz_de_que_trinca_e():
    from dataclasses import replace

    from osclab.plot import janela, paineis

    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 *trinca("I", "X", "A", lambda g: ruido(1.0)))
    arranjo = paineis.padrao(r)
    arranjo[0] = replace(arranjo[0],
                         sinais=arranjo[0].sinais + ("c3:instantaneo",))
    pacote = janela.montar(r, colunas=120, layout=arranjo)
    nomes_na_tela = [s["sinal"] for s in pacote["paineis"][0]["sinais"]]
    assert nomes_na_tela == ["IAW", "IBW", "ICW", "IAX"]


def test_o_catalogo_MARCA_quais_canais_estao_sem_sinal():
    """O buscador esconde estes por padrão. Sem a marca, a tela teria que
    adivinhar pelo nome."""
    from osclab.plot import catalogo

    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 *trinca("I", "X", "A", lambda g: ruido(1.0)))
    por_id = {s.id: s for s in catalogo.de_registro(r)}
    assert por_id["c0:instantaneo"].sem_sinal is False
    assert por_id["c3:instantaneo"].sem_sinal is True
    # E a conta do OscLab sobre ele EXISTE, marcada do mesmo jeito. Já não
    # existia, e isso dava um botão de RMS que não fazia nada quando o usuário
    # desmarcava a caixa para conferir que a entrada está mesmo aberta.
    assert por_id["v3:fundamental"].sem_sinal is True
    assert por_id["v0:fundamental"].sem_sinal is False


def test_num_registro_SEM_canal_mudo_nada_e_marcado():
    """A caixinha do buscador só aparece quando há o que esconder."""
    from osclab.plot import catalogo

    r = registro(*trinca("I", "", "A", lambda g: senoide(PICO, g)))
    assert not any(s.sem_sinal for s in catalogo.de_registro(r))


# ---------------------------------------------------------------------------
# O arranjo de abertura
# ---------------------------------------------------------------------------

def _graficos(reg: Record):
    from osclab.plot import paineis
    nomes = {c.index: c.name for c in reg.analog_channels}
    return [(p.nome, [nomes[int(s.split(":")[0][1:])] for s in p.sinais])
            for p in paineis.padrao(reg) if p.tipo == paineis.ANALOGICO]


def test_a_abertura_mostra_SO_corrente_e_tensao():
    """Um relé grava muito mais que isso — tensão da bateria, frequência,
    ângulos que ele mesmo calculou —, e cada unidade dessas virava um gráfico.
    O que se olha primeiro num evento é corrente e tensão; o resto é escolha de
    quem analisa.
    """
    r = registro(*trinca("I", "", "A", lambda g: senoide(PICO, g)),
                 *trinca("V", "", "kV", lambda g: senoide(10.0, g)),
                 ("VDC1", "V", np.full(N, 132.0)),
                 ("FREQ", "Hz", np.full(N, 60.0)))
    assert [nome for nome, _ in _graficos(r)] == ["Correntes (A)",
                                                  "Tensões (kV)"]


def test_a_TENSAO_DA_BATERIA_nao_abre_grafico():
    """Ela é volt, e não é uma das três fases de nada. Era um gráfico inteiro
    com duas retas — uma em 132 V e outra em zero."""
    r = registro(*trinca("V", "", "kV", lambda g: senoide(10.0, g)),
                 ("VDC1", "V", np.full(N, 132.0)))
    canais = [c for _, lista in _graficos(r) for c in lista]
    assert "VDC1" not in canais


def test_o_RESIDUAL_solto_entra_no_grafico_da_trinca():
    """O `IG` de um SEL mede a corrente de neutro no ferro e não entra na
    trinca — o nome dele não sai do nome das fases trocando uma letra. Mas é a
    primeira coisa que alguém procura num evento à terra."""
    r = registro(*trinca("I", "", "A", lambda g: senoide(PICO, g)),
                 ("IG", "A", senoide(3.0)))
    assert _graficos(r)[0][1] == ["IA", "IB", "IC", "IG"]


def trafo(prefixo: str, nivel: str, unidade: str, pico: float):
    """Uma trinca nomeada como um Siemens nomeia: com o nível de tensão dentro."""
    return [(f"{prefixo} {nivel}:{prefixo[0]} {f}", unidade, senoide(pico, g))
            for f, g in (("A", 0.0), ("B", 120.0), ("C", 240.0))]


def test_num_TRAFO_a_ordem_e_corrente_e_tensao_de_CADA_LADO_JUNTAS():
    """A ordem em que se conta um evento: o que entra e o que sai de cada
    lado, juntos."""
    r = registro(*trafo("IC", "13.8kV", "A", PICO),
                 *trafo("VP", "13.8kV", "kV", 10.0),
                 *trafo("IC", "138kV", "A", PICO / 10),
                 *trafo("VP", "138kV", "kV", 100.0))
    assert [nome for nome, _ in _graficos(r)] == [
        "Correntes (A)", "Tensões (kV)",
        "Correntes (A)", "Tensões (kV)",
    ]


def test_o_numero_segue_a_ordem_do_ARQUIVO():
    """Sem lado para deduzir, a ordem é a única coisa que não é palpite."""
    r = registro(*trafo("IC", "13.8kV", "A", PICO),
                 *trafo("IC", "138kV", "A", PICO / 10))
    assert [nome for nome, _ in _graficos(r)] == ["Correntes (A)",
                                                  "Correntes (A)"]


def test_a_trinca_SEM_SINAL_nao_abre_grafico():
    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 *trinca("I", "X", "A", lambda g: ruido(1.0)))
    assert [nome for nome, _ in _graficos(r)] == ["Correntes (A)"]


def test_sem_trinca_nenhuma_a_tela_NAO_abre_vazia():
    """Quando o programa não reconhece trinca, ele não tem com que escolher —
    e uma tela vazia seria pior que uma tela cheia demais. Aí vale o arranjo
    antigo, um painel por unidade."""
    r = registro(("SINAL 1", "A", senoide(PICO)),
                 ("SINAL 2", "kV", senoide(10.0)))
    assert len(_graficos(r)) == 2


# ---------------------------------------------------------------------------
# Alternado × contínuo
# ---------------------------------------------------------------------------

def test_a_TENSAO_DA_BATERIA_nao_ganha_RMS_nem_filtro():
    """A componente de 60 Hz de 132 V contínuos é zero, e o "eficaz de um
    ciclo" de um número parado é o próprio número, apresentado como se fosse
    medida de alternada."""
    from osclab.plot import catalogo

    r = registro(*trinca("V", "", "kV", lambda g: senoide(10.0, g)),
                 ("VDC1", "V", np.full(N, 132.0)))
    assert "VDC1" not in nomes(r, presenca.alternados(r))
    ids = {s.id for s in catalogo.de_registro(r)}
    assert "v3:rms" not in ids and "v3:fundamental" not in ids
    assert {"v0:rms", "v0:fundamental"} <= ids


def test_canal_SEM_UNIDADE_nao_ganha_RMS_nem_filtro():
    """As colunas `ANAnn` de um CEV não declaram unidade, e ali convivem
    magnitude em kV, ângulo em grau e frequência em hertz. O ângulo é o caso
    que a medição sozinha não pega: ele gira de −180° a +180°, o que tem cara
    de fundamental."""
    angulo = np.linspace(-180.0, 180.0, N)
    r = registro(*trinca("I", "", "A", lambda g: senoide(PICO, g)),
                 ("3V2A", "", angulo))
    assert "3V2A" not in nomes(r, presenca.alternados(r))


def test_a_FREQUENCIA_nao_ganha_RMS_nem_filtro():
    r = registro(*trinca("I", "", "A", lambda g: senoide(PICO, g)),
                 ("FREQ", "Hz", 60.0 + 0.01 * senoide(1.0)))
    assert "FREQ" not in nomes(r, presenca.alternados(r))


def test_o_vao_com_o_DISJUNTOR_ABERTO_continua_tendo_eficaz():
    """Corrente zero o registro inteiro não é contínua: é alternada que não
    está passando. Tirar dela o botão de eficaz seria negar a medida por causa
    do resultado dela."""
    r = registro(*trinca("I", "", "A", lambda g: np.zeros(N)))
    assert len(presenca.alternados(r)) == 3


def test_um_painel_so_de_CONTINUA_trava_o_botao_de_RMS():
    """Botão que acende e não faz nada é pior que botão travado — o usuário
    acredita que a tabela mudou."""
    from osclab.plot import janela, paineis

    r = registro(*trinca("V", "", "kV", lambda g: senoide(10.0, g)),
                 ("VDC1", "V", np.full(N, 132.0)))
    so_bateria = [paineis.Painel(id="x", tipo=paineis.ANALOGICO, nome="",
                                 sinais=("c3:instantaneo",))]
    pacote = janela.montar(r, colunas=120, layout=so_bateria)
    assert pacote["paineis"][0]["medida_aplicavel"] is False

    com_tensao = [paineis.Painel(id="x", tipo=paineis.ANALOGICO, nome="",
                                 sinais=("c0:instantaneo", "c3:instantaneo"))]
    pacote = janela.montar(r, colunas=120, layout=com_tensao)
    assert pacote["paineis"][0]["medida_aplicavel"] is True


# ---------------------------------------------------------------------------
# A regra do apelido, caso a caso
# ---------------------------------------------------------------------------
#
# Cada caso desta seção é uma linha da regra que o Alexandre escreveu. A ordem
# importa tanto quanto o nome: é ela que diz qual trinca é qual na tela, e
# errar o lado de alta num laudo só aparece tarde.

def test_UMA_trinca_de_cada_nao_ganha_apelido():
    """É o alimentador, e é o caso mais comum: o colchete não tem o que
    distinguir e seria ruído em toda legenda."""
    r = registro(*trinca("I", "", "A", lambda g: senoide(PICO, g)),
                 *trinca("V", "", "kV", lambda g: senoide(10.0, g)))
    assert _graficos(r) == [
        ("Correntes (A)", ["IA", "IB", "IC"]),
        ("Tensões (kV)", ["VA", "VB", "VC"]),
    ]


def test_DUAS_trincas_com_uma_SEM_SINAL_continuam_numeradas():
    """A sem sinal sai do gráfico de abertura e continua ocupando o número
    dela: são quatro conjuntos no arquivo, então `G1` a `G4` — a contagem é do
    arquivo inteiro, correntes e tensões na mesma sequência."""
    from osclab.plot import catalogo

    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 *trinca("I", "X", "A", lambda g: ruido(1.0)),
                 *trinca("V", "Y", "kV", lambda g: senoide(10.0, g)),
                 *trinca("V", "Z", "kV", lambda g: ruido(0.01)))
    assert _graficos(r) == [
        ("Correntes (A)", ["IAW", "IBW", "ICW"]),
        ("Tensões (kV)", ["VAY", "VBY", "VCY"]),
    ]
    # O nome do grupo continua existindo — é o que nomeia as componentes
    # simétricas e o resíduo —, mas não aparece no nome de canal nenhum: canal
    # se chama como o arquivo escreveu.
    from osclab.formats import conjuntos
    assert [c.rotulo for c in conjuntos.de_registro(r)] == ["G1", "G2",
                                                            "G3", "G4"]
    # E a posição DENTRO da grandeza, que é o que emparelha os painéis, segue
    # contando de um para cada grandeza.
    assert [c.ordem for c in conjuntos.de_registro(r)] == [1, 2, 1, 2]
    nomes_nossos = {s.id: s.nome for s in catalogo.de_registro(r)
                    if s.familia == "canal"}
    assert nomes_nossos["c0:instantaneo"] == "IAW"
    assert nomes_nossos["c3:instantaneo"] == "IAX"
    assert nomes_nossos["c9:instantaneo"] == "VAZ"


def test_DUAS_trincas_vivas_sao_NUMERADAS_mesmo_com_nivel_de_tensao():
    """O programa não diz alta nem baixa — nem tendo o nível no nome. Nível
    diferente não prova que há transformador no meio."""
    r = registro(*trafo("IC", "138kV", "A", PICO / 10),
                 *trafo("VP", "138kV", "kV", 100.0),
                 *trafo("IC", "13.8kV", "A", PICO),
                 *trafo("VP", "13.8kV", "kV", 10.0))
    assert [nome for nome, _ in _graficos(r)] == [
        "Correntes (A)", "Tensões (kV)",
        "Correntes (A)", "Tensões (kV)",
    ]


def test_DUAS_trincas_vivas_SEM_nivel_viram_colchetes():
    """O caso do TWFL: duas linhas no mesmo nível. Chamar uma de alta e outra
    de baixa seria inventar um transformador que não existe."""
    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 *trinca("I", "X", "A", lambda g: senoide(PICO / 2, g)),
                 *trinca("V", "Y", "kV", lambda g: senoide(10.0, g)),
                 *trinca("V", "Z", "kV", lambda g: senoide(10.0, g)))
    assert [nome for nome, _ in _graficos(r)] == [
        "Correntes (A)", "Tensões (kV)",
        "Correntes (A)", "Tensões (kV)",
    ]


def test_TRES_trincas_vivas_sao_todas_numeradas():
    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 *trinca("I", "X", "A", lambda g: senoide(PICO / 2, g)),
                 *trinca("I", "Y", "A", lambda g: senoide(PICO / 3, g)))
    assert [nome for nome, _ in _graficos(r)] == [
        "Correntes (A)", "Correntes (A)", "Correntes (A)"]


def test_quando_os_apelidos_NAO_CORRESPONDEM_nao_se_intercala():
    """Duas trincas de corrente e uma de tensão não formam par nenhum.
    Intercalar só quebraria a sequência das correntes."""
    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 *trinca("I", "X", "A", lambda g: senoide(PICO / 2, g)),
                 *trinca("V", "", "kV", lambda g: senoide(10.0, g)))
    assert [nome for nome, _ in _graficos(r)] == [
        "Correntes (A)", "Correntes (A)", "Tensões (kV)"]


def test_a_SEGUNDA_BATERIA_nao_cabeada_tambem_perde_RMS_e_filtro():
    """A `VDC2` é a entrada da bateria reserva, que ninguém ligou. Ela lê ruído
    do conversor — e ruído oscila em torno do zero, então passava pelo teste de
    alternado. `VDC2 RMS` é o eficaz de um ruído: um número que existe e não
    mede nada.
    """
    from osclab.plot import catalogo

    r = registro(*trinca("V", "", "kV", lambda g: senoide(10.0, g)),
                 ("VDC1", "V", np.full(N, 132.0)),
                 ("VDC2", "V", ruido(0.02)))
    ids = {s.id for s in catalogo.de_registro(r)}
    assert {"c3:instantaneo", "c4:instantaneo"} <= ids      # os canais ficam
    assert not {"v3:rms", "v3:fundamental"} & ids           # a bateria
    assert not {"v4:rms", "v4:fundamental"} & ids           # e a reserva dela


def test_juntar_DUAS_TRINCAS_num_painel_tira_o_numero_do_titulo():
    """Um painel com a `G1` e a `G2` dentro não é o gráfico de nenhuma das
    duas, e carimbar uma delas no título afirmaria do painel inteiro uma coisa
    que vale para metade dele."""
    from dataclasses import replace

    from osclab.plot import janela, paineis

    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 *trinca("I", "X", "A", lambda g: ruido(1.0)))
    arranjo = paineis.padrao(r)
    arranjo[0] = replace(arranjo[0], sinais=arranjo[0].sinais + (
        "c3:instantaneo", "c4:instantaneo", "c5:instantaneo"))

    misturado = janela.montar(r, colunas=120, layout=arranjo)
    assert misturado["paineis"][0]["nome"] == "Correntes (A)"

    # E um painel só com a `G2` diz `G2`.
    so_ela = [paineis.Painel(id="x", tipo=paineis.ANALOGICO, nome="",
                             sinais=("c3:instantaneo", "c4:instantaneo",
                                     "c5:instantaneo"))]
    assert janela.montar(r, colunas=120, layout=so_ela)["paineis"][0]["nome"] \
        == "Correntes (A)"


def test_o_RESIDUAL_solto_leva_o_APELIDO_da_trinca_dele():
    """Sem isto, o painel do Siemens abria com `IA G1`, `IB G1`, `IC G1` e
    um `IN` sem apelido nenhum no meio — o canal que mais confirma de que lado
    o painel é, sendo o único a não dizer.

    O que este teste afirma é que o residual acompanha a trinca: ele é do mesmo
    vão, então leva o nome do grupo dela."""
    from osclab.plot import janela

    r = registro(*trinca("I", "", "A", lambda g: senoide(PICO, g)),
                 ("IG", "A", senoide(3.0)))
    pacote = janela.montar(r, colunas=120)
    assert [s["sinal"] for s in pacote["paineis"][0]["sinais"]] == [
        "IA", "IB", "IC", "IG"]


def test_o_residual_SEM_DONO_e_conjunto_de_UM_CANAL_SO():
    """Com duas trincas da mesma unidade e nada com que desempatar, o residual
    não é pendurado em nenhuma — pendurá-lo no lado errado é pior que deixá-lo
    solto.

    Ele ganha apelido próprio, e entre COLCHETES: `G1` passou a significar um
    grupo trifásico, e um residual solto não é um grupo — dar-lhe um `G` seria
    mentir no nome. O colchete existe por um caso real: o GE grava DOIS
    residuais assim (`J1 -IG` e `J1 Ig`), e sem isso os dois se chamariam `IN`
    no mesmo arquivo.
    """
    from osclab.formats import conjuntos

    r = registro(*trinca("I", "W", "A", lambda g: senoide(PICO, g)),
                 *trinca("I", "X", "A", lambda g: senoide(PICO, g)),
                 ("IG", "A", senoide(3.0)),
                 ("IN", "A", senoide(2.0)))
    apelidos = conjuntos.rotulos_por_canal(r)
    nomes = {c.name: apelidos.get(c.index) for c in r.analog_channels}
    assert nomes["IAW"] == "G1"
    assert nomes["IAX"] == "G2"
    assert nomes["IG"] == "[1]"
    assert nomes["IN"] == "[2]"
