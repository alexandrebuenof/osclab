"""A lista de eventos do relé: o leitor, o tempo da aba e a rota.

Os textos abaixo têm a FORMA dos `.hdr` da Schneider do parque (conferidos
nos 250 do banco em 02/11/2026) e conteúdo inventado.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from osclab import paths
from osclab.formats import eventos
from osclab.plot import eventos as eventos_plot
from tests.fabrica import escrever_comtrade

EASERGY = """\
File type                     : Fault log (FT_RC)
Created by                    : Easergy Studio V9.3.3 (build 21.12.14.1)
Device                        : P439-655
Reference time for tRel       : Record start time
====================================================================================================

List of events
----------------------------------------------------------------------------------------------------
Line  |     tAbs     | tRel (s) | xxx.yyy | Description                | Value
----------------------------------------------------------------------------------------------------
  1   | 10:00:00.000 | 0.000    | 036.051 | MAIN  CB closed 3p EXT     | Present
  2   | 10:00:00.040 | 0.040    | 036.000 | MAIN  General starting     | Start
  3   | 10:00:00.055 | 0.055    | 035.071 | MAIN  Gen. trip command    | Start
  4   | 10:00:00.120 | 0.120    | 035.071 | MAIN  Gen. trip command    | End
  5   | 10:00:01.500 | 1.500    | 035.000 | FT_RC Record. in progress  | End
====================================================================================================

Measured data
----------------------------------------------------------------------------------------------------
Line  |     tAbs     | tRel (s) | xxx.yyy | Description                | Value
----------------------------------------------------------------------------------------------------
  1   | 10:00:00.060 | 0.060    | 010.198 | FT_DA Fault type           | B-N
  2   | 10:00:00.060 | 0.060    | 004.022 | FT_DA Fault location       | 12.3 km
"""

CONVERSOR = """\
                                       Fault log
     Device designation                     P439
     Reference time for tRel                Record start time

                                     Fault signals

    tAbs     |   tRel (s)   | Description                         | Value
----------------------------------------------------------------------------------------
09:00:00.000 | 00:00:00.000 | 113.019 GOOSE  Ext.Dev37 interm.pos | Present
09:00:00.031 | 00:00:00.031 | 035.071 MAIN  Gen. trip command     | Start

                                  Measured fault data

    tAbs     |   tRel (s)   | Description                         | Value
----------------------------------------------------------------------------------------
09:00:00.035 | 00:00:00.035 | 010.198 FT_DA Fault type            | A-B
"""

TXT = """\
     Device designation                 P439
     Reference time for tRel            Recording start time

                              Fault signals

    tAbs     |  tRel(s) | xxx.yyy Description                | Value
------------------------------------------------------------------------
08:00:00.000 |    0.000 | 036.051 MAIN  CB closed 3p EXT     | Present
08:00:00.192 |    0.192 | 035.071 MAIN  Gen. trip command    | Start

                               Fault data

    tAbs     |  tRel(s) | xxx.yyy Description                | Value
----------------------------------------------------------------------------------
08:00:00.216 |    0.216 | 004.022 FT_DA Fault location       | 7.5 km
"""


# ---------------------------------------------------------------------------
# O leitor: três jeitos de escrever a mesma tabela
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texto, n, trip", [(EASERGY, 5, 0.055), (CONVERSOR, 2, 0.031),
                                            (TXT, 2, 0.192)])
def test_os_tres_dialetos_dao_a_mesma_tabela(texto, n, trip):
    lista = eventos.de_texto(texto, "x.hdr")
    assert len(lista.eventos) == n
    ev = next(e for e in lista.eventos if e.descricao.endswith("Gen. trip command"))
    assert ev.t == pytest.approx(trip)
    assert ev.endereco == "035.071"
    assert ev.valor == "Start"
    assert lista.referencia_conhecida


def test_a_descricao_vai_como_o_rele_escreveu():
    """Nada se traduz nem se limpa: o espaço duplo entre o módulo e o nome é
    do relé, e é por ele que se casa a linha com o canal do COMTRADE."""
    lista = eventos.de_texto(EASERGY)
    assert lista.eventos[2].descricao == "MAIN  Gen. trip command"
    assert lista.eventos[0].hora == "10:00:00.000"


def test_o_bloco_de_dados_do_rele_vem_separado_da_lista():
    lista = eventos.de_texto(EASERGY)
    assert [d.valor for d in lista.dados] == ["B-N", "12.3 km"]
    assert all("FT_DA" in d.descricao for d in lista.dados)
    assert eventos.de_texto(CONVERSOR).dados[0].valor == "A-B"
    assert eventos.de_texto(TXT).dados[0].valor == "7.5 km"


def test_referencia_de_tempo_desconhecida_nao_vira_palpite():
    """Se o relé contasse o tRel do disparo e o programa achasse que é do
    início, todo clique poria o cursor no lugar errado, sem erro nenhum."""
    texto = EASERGY.replace("Record start time", "Trigger time")
    lista = eventos.de_texto(texto)
    assert not lista.referencia_conhecida
    assert lista.avisos
    pacote = eventos_plot.lista("A", "s", "", lista)
    assert all(e["t"] is None for e in pacote["eventos"])


def test_texto_sem_tabela_nao_e_lista():
    assert eventos.de_texto("Event: AG T\nLocation: 12.3\n") is None
    assert eventos.de_texto("") is None


#: Um relé que nunca vimos: a mesma informação, com o valor ANTES da descrição
#: e o tempo relativo numa coluna que não é número. Inventado.
DESCONHECIDO = """\
Fault signals
 Seq | Time         | State | Signal            | Rel
   1 | 10:00:00.000 | ON    | PTOC1 Str         | +0 ms
   2 | 10:00:00.040 | ON    | PTRC1 Op          | +40 ms
   3 | 10:00:00.090 | OFF   | XCBR1 Pos closed  | +90 ms
"""


def test_formato_que_nao_conhecemos_vira_TEXTO_CRU_e_nao_tabela_errada(tmp_path):
    """Pedido dele, 02/11/2026: tabela lida com as colunas trocadas é pior que
    o texto como veio — o texto ao menos não mente."""
    assert eventos.de_texto(DESCONHECIDO) is None
    (tmp_path / "x.hdr").write_text(DESCONHECIDO, encoding="utf-8")
    achada = eventos.do_registro(tmp_path, ["x.cfg", "x.hdr"])
    assert not achada.reconhecida
    assert "PTRC1 Op" in achada.cru
    pacote = eventos_plot.lista("A", "s", "", achada)
    assert pacote["tem"] is False
    assert pacote["cru"] and pacote["eventos"] == []
    assert pacote["motivo"] == eventos_plot.NAO_RECONHECIDA


def test_tabela_lida_pela_metade_tambem_vira_texto_cru():
    """Se muitas linhas com hora não se deixam ler, o dialeto não é o nosso."""
    metade = EASERGY.replace("| 0.040    |", "| quarenta |").replace(
        "| 0.055    |", "| x |").replace("| 0.120    |", "| y |")
    assert eventos.de_texto(metade) is None


def test_mesmo_reconhecida_a_lista_leva_o_arquivo_como_veio():
    """O botão «texto» (o arquivo como veio) é a saída para quando o programa ACHA que leu."""
    lista = eventos.de_texto(EASERGY, "x.hdr")
    assert lista.cru.startswith("File type")
    assert eventos_plot.lista("A", "s", "", lista)["cru"] == lista.cru


# ---------------------------------------------------------------------------
# O tempo da aba
# ---------------------------------------------------------------------------

def test_o_evento_do_outro_registro_entra_deslocado_pelo_alinhamento():
    """`d` é o MESMO que desloca as ondas: o instante t da aba cai em t + d no
    outro registro, então o evento dele entra em t − d."""
    lista = eventos.de_texto(EASERGY)
    pacote = eventos_plot.lista("B", "s", "", lista, d=0.010, fim=2.0)
    trip = next(e for e in pacote["eventos"] if e["valor"] == "Start"
                and e["descricao"].endswith("trip command"))
    assert trip["t"] == pytest.approx(0.045)


def test_o_que_passa_do_fim_da_gravacao_vem_marcado():
    """O relé continua listando depois que o COMTRADE acaba (4186 eventos no
    banco). Aparece, mas não leva o cursor: ali não há onda."""
    pacote = eventos_plot.lista("A", "s", "", eventos.de_texto(EASERGY), fim=1.0)
    fora = [e["descricao"] for e in pacote["eventos"] if e["fora"]]
    assert fora == ["FT_RC Record. in progress"]


def test_o_evento_aponta_o_digital_de_mesmo_nome():
    """O mesmo relé escreve `MAIN  Gen. trip command` na lista e
    `MAIN : Gen. trip command` no COMTRADE. Clicar no evento seleciona a tira."""
    from types import SimpleNamespace as C
    canais = [C(name="MAIN : General starting", index=3),
              C(name="MAIN : Gen. trip command", index=7),
              C(name="MAIN : Gen. trip command", index=9)]   # repetido: fica o primeiro
    digitais = eventos_plot.indice_dos_digitais(canais)
    pacote = eventos_plot.lista("A", "s", "", eventos.de_texto(EASERGY), digitais=digitais)
    por_nome = {e["descricao"]: e["digital"] for e in pacote["eventos"]}
    assert por_nome["MAIN  General starting"] == 3
    assert por_nome["MAIN  Gen. trip command"] == 7
    # sem digital de mesmo nome não se inventa nenhum
    assert por_nome["MAIN  CB closed 3p EXT"] is None


def test_sem_lista_o_pacote_diz_por_que():
    pacote = eventos_plot.lista("A", "s", "", None)
    assert pacote["tem"] is False
    assert ".hdr" in pacote["motivo"]


# ---------------------------------------------------------------------------
# A rota
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def acervo_temporario(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LIBRARY_DIR", tmp_path / "acervo")
    monkeypatch.setattr(paths, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(paths, "CONFIG_DIR", tmp_path / "config")


def _enviar(cliente, pasta: Path, nome: str, hdr: str | None) -> str:
    cfg = escrever_comtrade(pasta, nome=nome, n=256)
    arquivos = [(io.BytesIO(cfg.read_bytes()), cfg.name),
                (io.BytesIO(cfg.with_suffix(".dat").read_bytes()), f"{nome}.dat")]
    if hdr is not None:
        arquivos.append((io.BytesIO(hdr.encode("latin-1")), f"{nome}.hdr"))
    r = cliente.post("/api/acervo", data={"arquivos": arquivos},
                     content_type="multipart/form-data")
    return r.get_json()["aceitos"][0]["sha"]


def test_a_rota_le_o_hdr_que_veio_com_o_registro(cliente, tmp_path):
    sha = _enviar(cliente, tmp_path / "a", "UM", EASERGY)
    r = cliente.get(f"/api/eventos/{sha}").get_json()
    assert r["tem"] is True
    [lista] = r["listas"]
    assert lista["letra"] == "A"
    assert lista["de"] == "UM.hdr"
    assert len(lista["eventos"]) == 5


def test_a_rota_sem_lista_explica(cliente, tmp_path):
    sha = _enviar(cliente, tmp_path / "a", "UM", None)
    r = cliente.get(f"/api/eventos/{sha}").get_json()
    assert r["tem"] is False
    assert r["listas"][0]["motivo"]


def test_com_dois_registros_cada_lista_vem_com_a_letra_do_ied(cliente, tmp_path):
    a = _enviar(cliente, tmp_path / "a", "UM", EASERGY)
    b = _enviar(cliente, tmp_path / "b", "DOIS", CONVERSOR)
    r = cliente.post(f"/api/eventos/{a}", json={"registros": [{"sha": b}],
                                               "alinhar": "hora"}).get_json()
    assert [x["letra"] for x in r["listas"]] == ["A", "B"]
    assert len(r["listas"][1]["eventos"]) == 2


def test_rota_de_registro_que_nao_existe(cliente):
    assert cliente.get("/api/eventos/naoexiste").status_code == 404


# ---------------------------------------------------------------------------
# A tela
# ---------------------------------------------------------------------------

def _arquivo(*partes) -> str:
    raiz = Path(__file__).resolve().parents[1] / "src" / "osclab" / "web"
    return raiz.joinpath(*partes).read_text(encoding="utf-8")


def test_o_painel_existe_e_carrega_o_script():
    onda = _arquivo("templates", "onda.html")
    assert 'id="painel-dos-eventos"' in onda
    assert "js/eventos.js" in onda


def test_a_tela_nao_faz_conta_de_tempo_com_os_eventos():
    """O deslocamento de cada registro é do servidor: aqui só se compara o
    instante do cursor com o da linha para saber qual marcar."""
    js = _arquivo("static", "js", "eventos.js")
    assert "deslocamento" not in js
    assert "window.osclab.irPara(e.t)" in js
    assert '"osclab:cursores"' in js
    onda = _arquivo("static", "js", "onda.js")
    assert '"osclab:cursores"' in onda and '"osclab:janela"' in onda
