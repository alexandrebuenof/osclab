"""Comissionamento: o OscLab contra os números que o PRÓPRIO relé gravou.

## A ideia

Todo arquivo de oscilografia traz, além das amostras, medidas que o relé
calculou por dentro: o resíduo que ele mediu numa entrada própria, as
componentes que ele gravou em coluna, os fasores que ele carimbou no cabeçalho.
**Esses números são um gabarito escrito pelo fabricante.** Comparar o OscLab
contra eles não precisa de arquivo de referência nenhum — e vale para qualquer
arquivo novo que o Alexandre largue na pasta.

Foi essa a razão de descartar o plano anterior, de um `gabarito.json` chaveado
por sha256: um gabarito que a gente mesmo escreve prova que a conta não mudou,
não que ela está certa. Este aqui prova as duas coisas.

## As três camadas, e o que cada uma prende

1. **Sintéticos** (`tests/fabrica.py`): resposta CONHECIDA — "a senoide tinha
   100 A de pico, o leitor tem que devolver 100 A". Prende a MATEMÁTICA, de
   forma absoluta. É melhor que comparar com software: não há segunda
   implementação para estar errada.
2. **Este arquivo**: prende matemática MAIS leitura — escala de TC/TP, ordem de
   canal, base de tempo — contra o que o relé afirma.
3. **SIGRA**: terceiro independente, manual, cursor a cursor. Ver `CLAUDE.md`.
   Cobre os arquivos da SEL que não trazem gabarito nenhum dentro.

## Os arquivos não entram no repositório

Identificam instalação, data e comportamento da rede, e o repositório é
público. Então estes testes ficam desligados por padrão:

    set OSCLAB_AMOSTRAS=C:\\Users\\alexa\\Documents\\06 - Ferramentas\\Oscilografias
    python app.py --testes

## As tolerâncias saem de MEDIDA, não de chute

Cada uma tem o número medido ao lado, e a folga é deliberada: apertar até o
valor medido faria o teste quebrar no próximo arquivo por variação legítima.

## As contas moram em `tests/conferencias.py`

E não aqui, porque `tools/comissionar.py` roda as MESMAS conferências sobre o
banco inteiro e grava o placar — uma conta só nos dois lugares. Cada
conferência devolve linhas com veredito; este arquivo reprova quando alguma
diverge e pula, com o motivo escrito, quando nenhuma se aplica.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from osclab.formats import registry
from tests import conferencias as C

_RAIZ = os.environ.get("OSCLAB_AMOSTRAS", "").strip()
AMOSTRAS = Path(_RAIZ).expanduser() if _RAIZ else None

pytestmark = pytest.mark.skipif(
    AMOSTRAS is None or not AMOSTRAS.is_dir(),
    reason="defina OSCLAB_AMOSTRAS apontando para a pasta das oscilografias reais",
)

PRINCIPAIS = (".cfg", ".cff", ".cev")


def _e_oscilografia(caminho: Path) -> bool:
    """Um `.cfg` só é COMTRADE se tiver o `.dat` irmão.

    `.cfg` é extensão disputada: um `pyvenv.cfg` de ambiente virtual do Python
    mora em qualquer pasta de projeto, tem 300 bytes de `home = ...` e casaria
    com a varredura. O comissionamento reprovaria por não conseguir lê-lo — e
    reprovar por motivo besta é o caminho mais curto para alguém desligar a
    suíte.

    **O critério é estrutural, não lista de nomes**, e é essa a diferença que
    importa: um arquivo que não traz o par de dados não é oscilografia
    nenhuma. Um `.CEV` — que é auto-contido — continua entrando sempre, e foi
    justamente um `.CEV` que o programa não lia (o do SEL-787) que este teste
    denunciou. A guarda não podia ser larga a ponto de ter escondido aquele.
    """
    if caminho.suffix.lower() != ".cfg":
        return True
    return any(caminho.with_suffix(ext).is_file()
               for ext in (".dat", ".DAT", ".Dat"))


def _arquivos() -> list[Path]:
    if AMOSTRAS is None or not AMOSTRAS.is_dir():
        return []
    return sorted(p for p in AMOSTRAS.rglob("*")
                  if p.is_file() and p.suffix.lower() in PRINCIPAIS
                  and _e_oscilografia(p))


def _ids(caminhos: list[Path]) -> list[str]:
    base = AMOSTRAS or Path(".")
    return [str(p.relative_to(base)) for p in caminhos]


SEM_AMOSTRAS = ("defina OSCLAB_AMOSTRAS apontando para a pasta das "
                "oscilografias reais")


def _casos(caminhos: list[Path]) -> dict:
    """Os argumentos do `parametrize`, com um caso visível quando não há
    arquivo nenhum.

    Sai como dicionário para entrar com `**`: o terceiro posicional do
    `parametrize` é `indirect`, não `ids`, e passar a lista ali dentro falha
    de um jeito que não parece o que é.

    Sem isto, uma lista vazia some do relatório com a mensagem genérica do
    pytest — «got empty parameter set» —, e quem roda a suíte lê "pulou" sem
    saber o que fazer para não pular. Um teste que não roda tem que DIZER por
    que não rodou; senão a suíte fica verde afirmando uma coisa que não
    conferiu.
    """
    if caminhos:
        return {"argvalues": caminhos, "ids": _ids(caminhos)}
    return {"argvalues": [pytest.param(
                None, marks=pytest.mark.skip(reason=SEM_AMOSTRAS))],
            "ids": ["sem amostras"]}


CAMINHOS = _arquivos()
CEVS = [p for p in CAMINHOS if p.suffix.lower() == ".cev"]


def _exigir(linhas: list[C.Linha]) -> None:
    """Reprova se alguma linha diverge (ou quebrou); pula se nenhuma se aplica.

    O pulo leva os motivos: «não se aplica» sem dizer por quê é o teste
    afirmando que conferiu o que não conferiu.
    """
    ruins = [x for x in linhas if x.veredito in (C.DIVERGE, C.ERRO)]
    assert not ruins, "; ".join(
        f"{x.item or x.conferencia}: "
        + (f"erro {x.erro:.3f} {x.unidade} (tolerância {x.tolerancia:g})"
           if x.erro is not None else x.veredito)
        + (f" — {x.motivo}" if x.motivo else "")
        for x in ruins)
    if not any(x.veredito == C.CONFERE for x in linhas):
        pytest.skip("; ".join(sorted({x.motivo for x in linhas})))


# ---------------------------------------------------------------------------
# 1. O resíduo que o relé MEDIU contra o que o OscLab CALCULA
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("caminho", **_casos(CAMINHOS))
def test_o_residuo_calculado_bate_com_o_MEDIDO(caminho: Path):
    """**A conferência mais forte que existe neste arquivo.**

    O resíduo medido vem de uma entrada própria do relé; o nosso vem da soma
    de três canais. São dois caminhos FISICAMENTE independentes para o mesmo
    número — se a trinca estiver errada, se uma fase entrar com sinal trocado,
    se a escala de TC estiver furada, isto abre. Nenhuma comparação com outro
    software prova tanto: software comparado com software pode estar errado
    dos dois lados.

    Ver `conferencias.TOLERANCIA_DO_RESIDUO` para por que a folga é larga e
    por que isso não enfraquece o que o teste pega.
    """
    _exigir(C.residuo(caminho, registry.read(caminho)))


# ---------------------------------------------------------------------------
# 2. Os fasores que o relé carimbou no cabeçalho do `.CEV`
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("caminho", **_casos(CEVS))
def test_o_fasor_de_PRE_FALTA_do_cabecalho_aparece_na_nossa_conta(caminho: Path):
    """O relé gravou o fasor que ele mediu. Ele tem que existir na nossa curva.

    A asserção é «existe uma amostra em que bate», e não «bate na amostra tal»:
    qual instante a SEL usa é convenção interna dela, e fixar um palpite sobre
    isso testaria o palpite. O que importa é que o número do relé esteja lá.

    **Só a pré-falta vale em todo arquivo** — e só quando o arquivo tem um
    ciclo inteiro antes do disparo (ver `conferencias.fasor_de_pre_falta`).
    """
    _exigir(C.fasor_de_pre_falta(caminho, registry.read(caminho)))


@pytest.mark.parametrize("caminho", **_casos(CEVS))
def test_o_fasor_de_FALTA_bate_quando_a_falta_cabe_numa_janela(caminho: Path):
    """E quando não cabe, o teste PULA em vez de reprovar.

    O `.CEV` de 4 amostras por ciclo do parque registra um curto de 1,5 ciclo.
    Não existe janela de um ciclo inteiramente dentro dele, e o relé calculou o
    fasor dele por dentro, a 16 amostras por ciclo ou mais, ANTES de decimar o
    relatório para 4. Medido ali: 18,9 % de erro de módulo.

    **Isso não é defeito do leitor, é resolução do relatório** — e é limite que
    vale saber antes de confiar num arquivo de 4 amostras por ciclo para
    conferir corrente de falta.
    """
    _exigir(C.fasor_de_falta(caminho, registry.read(caminho)))


# ---------------------------------------------------------------------------
# 3. As colunas que o relé gravou, contra as nossas componentes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("caminho", **_casos(CEVS))
def test_as_colunas_do_rele_batem_EM_REGIME(caminho: Path):
    """Em regime, e só: fora dele a comparação mede a janela, não a conta.

    **Regime aqui é a nossa grandeza parada durante a janela INTEIRA da
    coluna** (dez ciclos), não só um ciclo: no SEL-451 de Araputanga também
    `V1M` e `3V2M` são média móvel, e o topo da rampa passava no critério de
    um ciclo (ver `conferencias.parado_na_janela`). E um valor do relé menor
    que dez degraus de gravação das fases — o `3V0M` de 0,007 kV sobre fases
    gravadas com 0,01 kV — não se confere em por cento.
    """
    _exigir(C.colunas(caminho, registry.read(caminho)))


# ---------------------------------------------------------------------------
# 4. O mesmo evento exportado duas vezes
# ---------------------------------------------------------------------------

def _pares_do_mesmo_evento() -> list[tuple[Path, Path]]:
    chaves = {}
    for caminho in CAMINHOS:
        try:
            chaves[caminho] = C.chave_de_evento(registry.read(caminho))
        except Exception:
            continue
    return C.pares_do_mesmo_evento(chaves)


PARES = _pares_do_mesmo_evento()


@pytest.mark.parametrize(
    "par",
    PARES or [pytest.param(None, marks=pytest.mark.skip(
        reason=SEM_AMOSTRAS if AMOSTRAS is None
        else "não há o mesmo evento exportado nos dois formatos"))],
    ids=([f"{a.stem[:18]}|{b.stem[:18]}" for a, b in PARES] or ["sem par"]))
def test_o_mesmo_evento_exportado_DUAS_VEZES_da_o_mesmo_numero(par):
    """O `.CEV` filtrado e o COMTRADE bruto do mesmo curto.

    São dois arquivos com taxas diferentes (8 e 33,33 amostras por ciclo),
    escalas diferentes (o `.CEV` grava eficaz e o leitor converte para
    instantâneo) e conteúdo diferente (um já filtrado pelo relé, o outro
    cru). Se os dois derem a mesma pré-falta, o caminho de leitura dos DOIS
    formatos está certo — e é o `.CEV` que carrega para o COMTRADE a
    validação que ele recebeu do cabeçalho do relé.

    **No mesmo instante relativo ao disparo** — ver `conferencias.mesmo_evento`.
    """
    _exigir(C.mesmo_evento(registry.read(par[0]), registry.read(par[1])))


# ---------------------------------------------------------------------------
# 5. A hora do TRIP que o relé carimbou, contra o nosso canal digital
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("caminho", **_casos(CEVS))
def test_a_hora_do_TRIP_cai_na_amostra_em_que_o_digital_MUDA(caminho: Path):
    """**Esta é a única conferência que prende a BASE DE TEMPO.**

    Todo o resto compara número com número na mesma amostra, e passaria igual
    se o registro inteiro estivesse deslocado no tempo. Aqui não: o relé
    carimbou uma hora de RELÓGIO, e para ela virar índice de amostra passam a
    hora do disparo, o recuo pela marca `>` e a taxa. Se qualquer um estiver
    errado, o trip cai noutra amostra.

    E prende o desempacotamento dos digitais junto — a tira hexadecimal vira
    bit na posição certa, ou o `TRIP` não estaria ali.

    Medido no alimentador: o relé carimba 13:36:57,980, que dá a amostra 208, e
    é exatamente onde `TRIP` muda. Das 481 amostras do registro, só 40 têm
    mudança alguma, e a 208 é a maior rajada delas (17 digitais).
    """
    _exigir(C.trip(caminho, registry.read(caminho)))


# ---------------------------------------------------------------------------
# 6. O instantâneo que o relé gravou coluna a coluna (SEL-787)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("caminho", **_casos(CEVS))
def test_o_instantaneo_do_cabecalho_aparece_na_nossa_conta(caminho: Path):
    """O SEL-787 grava, no cabeçalho, o valor de CADA COLUNA num instante.

    O campo se chama igual ao título da coluna, unidade inclusive —
    `IAW1(A)`, `VB(V)` —, e é isso que o distingue do bloco `IA_PF`/`IA` do
    451, cujos campos não trazem unidade. Por isso o casamento é por nome
    EXATO: no 451 nenhum campo casa e o teste pula; no 787 casam os doze.

    Foi com este gabarito que se provou que o `.CEV` do 787 também vem em
    eficaz, mesmo sendo relatório BRUTO: com o ×√2 os canais fecham dentro de
    1,3 %; sem ele, erram 30 %.
    """
    _exigir(C.instantaneo(caminho, registry.read(caminho)))


# ---------------------------------------------------------------------------
# 7. O neutro medido cujo NOME diz de que trinca ele é
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("caminho", **_casos(CAMINHOS))
def test_o_neutro_que_o_NOME_liga_a_trinca_tambem_confere(caminho: Path):
    """Quatro pares que a dedução do programa deixa de lado, de propósito.

        SEL-787   IGW1  → I*W1        IGW2  → I*W2
        GE        J1 -IG → J1 -I*     J1 Ig → J1 I*

    São neutros de verdade, com a trinca escrita no próprio nome. Conferi-los
    aqui é ganho puro: mais gabarito, nenhum risco na tela.
    """
    _exigir(C.neutro_pelo_nome(caminho, registry.read(caminho)))


# ---------------------------------------------------------------------------
# 8. As colunas LENTAS do relé: sequência positiva, negativa e terra
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("caminho", **_casos(CEVS))
def test_as_colunas_LENTAS_de_corrente_batem_EM_REGIME(caminho: Path):
    """`LI1M`, `L3I2M` e `LIGM` — médias móveis de dez ciclos.

    Era só o `LI1M`: as outras duas «nunca tinham trecho comparável», e não
    tinham porque o critério de regime olhava um ciclo só. Com a nossa grandeza
    parada a janela inteira (`conferencias.parado_na_janela`) a pré-falta de
    um registro longo serve para as três; e a sequência negativa e o terra da
    carga, quase sempre menores que dez degraus de uma corrente gravada em
    inteiro, pulam pela resolução do arquivo, com o motivo escrito.
    """
    _exigir(C.colunas_lentas(caminho, registry.read(caminho)))
