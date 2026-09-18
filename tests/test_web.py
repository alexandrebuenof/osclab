"""As rotas da interface web.

O que se testa aqui é o contrato HTTP — que a página sobe, que o envio aceita
um par de arquivos, que o acervo lista e remove. O desenho da tela não tem
teste automático; isso se confere olhando.
"""

from __future__ import annotations

import io

import pytest

from osclab import paths, version
from tests.fabrica import escrever_comtrade


@pytest.fixture(autouse=True)
def acervo_temporario(tmp_path, monkeypatch):
    """Nenhum teste toca o acervo de verdade do usuário."""
    monkeypatch.setattr(paths, "LIBRARY_DIR", tmp_path / "acervo")
    monkeypatch.setattr(paths, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(paths, "CONFIG_DIR", tmp_path / "config")


def _par_enviavel(tmp_path, nome="REGISTRO", **kw):
    """O par .cfg/.dat no formato que o Flask espera num multipart."""
    cfg = escrever_comtrade(tmp_path / f"origem-{nome}", nome=nome, **kw)
    dat = cfg.with_suffix(".dat")
    return [
        (io.BytesIO(cfg.read_bytes()), cfg.name),
        (io.BytesIO(dat.read_bytes()), dat.name),
    ]


# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------

def test_a_home_responde(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert b"OscLab" in r.data
    assert b"Arquivos do projeto" in r.data


def test_a_home_mostra_a_versao(cliente):
    r = cliente.get("/")
    assert version.read().encode() in r.data


def test_saude_devolve_json_util(cliente):
    r = cliente.get("/saude")
    assert r.status_code == 200
    dados = r.get_json()
    assert dados["versao"] == version.read()
    assert "comtrade" in dados["formatos"]
    assert dados["registros_no_acervo"] == 0


def test_rota_inexistente_e_404(cliente):
    assert cliente.get("/nao-existe").status_code == 404


# ---------------------------------------------------------------------------
# Envio
# ---------------------------------------------------------------------------

def test_envio_de_um_par_completo(cliente, tmp_path):
    r = cliente.post("/api/acervo",
                     data={"arquivos": _par_enviavel(tmp_path, n=64)},
                     content_type="multipart/form-data")
    assert r.status_code == 200
    corpo = r.get_json()
    assert len(corpo["aceitos"]) == 1
    assert corpo["aceitos"][0]["nome"] == "REGISTRO"
    assert corpo["aceitos"][0]["n_amostras"] == 64
    assert not corpo["problemas"]


def test_envio_so_do_cfg_fica_esperando_o_dat(cliente, tmp_path):
    """O .cfg sozinho nao e' erro: vai para a antessala esperar o .dat."""
    so_cfg = [_par_enviavel(tmp_path, n=32)[0]]
    r = cliente.post("/api/acervo", data={"arquivos": so_cfg},
                     content_type="multipart/form-data")
    corpo = r.get_json()
    assert not corpo["aceitos"]
    assert not corpo["problemas"]
    assert any("esperando o .dat" in linha for linha in corpo["aguardando"])
    assert len(corpo["na_antessala"]) == 1


def test_dat_enviado_depois_completa_o_par(cliente, tmp_path):
    """O par se fecha mesmo chegando em dois envios separados."""
    cfg, dat = _par_enviavel(tmp_path, n=32)
    cliente.post("/api/acervo", data={"arquivos": [cfg]},
                 content_type="multipart/form-data")
    r = cliente.post("/api/acervo", data={"arquivos": [dat]},
                     content_type="multipart/form-data")
    corpo = r.get_json()
    assert len(corpo["aceitos"]) == 1
    assert corpo["aceitos"][0]["n_amostras"] == 32
    assert not corpo["aguardando"]
    assert not corpo["na_antessala"]
    assert len(cliente.get("/api/acervo").get_json()["itens"]) == 1


def test_enviar_duas_vezes_nao_duplica(cliente, tmp_path):
    resposta = None
    for _ in range(2):
        resposta = cliente.post("/api/acervo",
                                data={"arquivos": _par_enviavel(tmp_path, n=32)},
                                content_type="multipart/form-data")
    assert len(resposta.get_json()["repetidos"]) == 1
    assert len(cliente.get("/api/acervo").get_json()["itens"]) == 1


def test_envio_vazio_nao_quebra(cliente):
    r = cliente.post("/api/acervo", data={}, content_type="multipart/form-data")
    assert r.status_code == 200
    assert r.get_json()["problemas"]


def test_varios_registros_de_uma_vez(cliente, tmp_path):
    arquivos = [
        *_par_enviavel(tmp_path / "a", nome="UM", n=32),
        *_par_enviavel(tmp_path / "b", nome="DOIS", n=64),
    ]
    r = cliente.post("/api/acervo", data={"arquivos": arquivos},
                     content_type="multipart/form-data")
    assert len(r.get_json()["aceitos"]) == 2


# ---------------------------------------------------------------------------
# Listar e remover
# ---------------------------------------------------------------------------

def test_acervo_comeca_vazio(cliente):
    assert cliente.get("/api/acervo").get_json()["itens"] == []


def test_lista_depois_do_envio(cliente, tmp_path):
    cliente.post("/api/acervo", data={"arquivos": _par_enviavel(tmp_path, n=32)},
                 content_type="multipart/form-data")
    itens = cliente.get("/api/acervo").get_json()["itens"]
    assert len(itens) == 1
    assert itens[0]["estacao"] == "SE TESTE"


def test_remover(cliente, tmp_path):
    envio = cliente.post("/api/acervo",
                         data={"arquivos": _par_enviavel(tmp_path, n=32)},
                         content_type="multipart/form-data")
    sha = envio.get_json()["aceitos"][0]["sha"]
    assert cliente.delete(f"/api/acervo/{sha}").status_code == 200
    assert cliente.get("/api/acervo").get_json()["itens"] == []


def test_remover_o_que_nao_existe(cliente):
    assert cliente.delete("/api/acervo/naoexiste").status_code == 404


# ---------------------------------------------------------------------------
# A janela da forma de onda: os gestos do mouse viram pedido HTTP
# ---------------------------------------------------------------------------

def _sha_de_um_registro(cliente, tmp_path, **kw):
    envio = cliente.post("/api/acervo",
                         data={"arquivos": _par_enviavel(tmp_path, **kw)},
                         content_type="multipart/form-data")
    return envio.get_json()["aceitos"][0]["sha"]


def test_a_janela_inteira_vem_por_padrao(cliente, tmp_path):
    sha = _sha_de_um_registro(cliente, tmp_path, n=256)
    dados = cliente.get(f"/api/onda/{sha}").get_json()
    assert dados["inteiro"] is True
    assert dados["de"] == dados["limite_de"]
    assert dados["grupos"]


def test_zoom_pela_rota_estreita_a_janela(cliente, tmp_path):
    sha = _sha_de_um_registro(cliente, tmp_path, n=512)
    todo = cliente.get(f"/api/onda/{sha}").get_json()
    meio = (todo["de"] + todo["ate"]) / 2

    perto = cliente.get(f"/api/onda/{sha}",
                        query_string={"de": todo["de"], "ate": todo["ate"],
                                      "zoom": 0.5, "foco": meio}).get_json()
    assert (perto["ate"] - perto["de"]) < (todo["ate"] - todo["de"])
    assert perto["inteiro"] is False
    # Os limites do registro não mudam com o zoom — é por eles que a tela sabe
    # que ainda há oscilografia fora da janela.
    assert perto["limite_ate"] == todo["limite_ate"]


def test_arrastar_pela_rota_anda_sem_mudar_a_largura(cliente, tmp_path):
    sha = _sha_de_um_registro(cliente, tmp_path, n=512)
    todo = cliente.get(f"/api/onda/{sha}").get_json()
    meio = (todo["de"] + todo["ate"]) / 2

    perto = cliente.get(f"/api/onda/{sha}",
                        query_string={"de": todo["de"], "ate": meio}).get_json()
    largura = perto["ate"] - perto["de"]

    andou = cliente.get(f"/api/onda/{sha}",
                        query_string={"de": perto["de"], "ate": perto["ate"],
                                      "andar": largura / 2}).get_json()
    assert andou["de"] > perto["de"]
    assert (andou["ate"] - andou["de"]) == pytest.approx(largura, rel=1e-6)


def test_botao_direito_volta_ao_registro_inteiro(cliente, tmp_path):
    sha = _sha_de_um_registro(cliente, tmp_path, n=256)
    todo = cliente.get(f"/api/onda/{sha}").get_json()
    meio = (todo["de"] + todo["ate"]) / 2

    volta = cliente.get(f"/api/onda/{sha}",
                        query_string={"de": meio, "ate": todo["ate"],
                                      "tudo": "1"}).get_json()
    assert volta["inteiro"] is True
    assert volta["de"] == pytest.approx(todo["de"])
    assert volta["ate"] == pytest.approx(todo["ate"])


def test_janela_absurda_na_url_nao_derruba_o_servidor(cliente, tmp_path):
    sha = _sha_de_um_registro(cliente, tmp_path, n=128)
    r = cliente.get(f"/api/onda/{sha}",
                    query_string={"de": "-1e9", "ate": "banana", "zoom": "xyz"})
    assert r.status_code == 200
    dados = r.get_json()
    assert dados["amostras_na_janela"] > 0


def test_janela_de_registro_que_nao_existe(cliente):
    assert cliente.get("/api/onda/naoexiste").status_code == 404


def test_a_janela_nao_escorrega_a_cada_gesto(cliente, tmp_path):
    """A largura tem que sobreviver a muitas idas e voltas.

    Custou um bug: a rota devolvia o instante da primeira e da última AMOSTRA
    dentro da janela, e a tela mandava isso de volta no gesto seguinte. Cada
    ida e volta encolhia a janela uma amostra, e o desenho escorregava sozinho.
    """
    sha = _sha_de_um_registro(cliente, tmp_path, n=1024)
    todo = cliente.get(f"/api/onda/{sha}").get_json()
    meio = (todo["de"] + todo["ate"]) / 2

    atual = cliente.get(f"/api/onda/{sha}",
                        query_string={"de": todo["de"], "ate": meio}).get_json()
    largura = atual["ate"] - atual["de"]

    for _ in range(30):
        atual = cliente.get(f"/api/onda/{sha}",
                            query_string={"de": atual["de"],
                                          "ate": atual["ate"]}).get_json()

    assert (atual["ate"] - atual["de"]) == pytest.approx(largura, rel=1e-9)


# ---------------------------------------------------------------------------
# A leitura dos cursores
# ---------------------------------------------------------------------------

def test_a_rota_de_leitura_devolve_valor_por_canal(cliente, tmp_path):
    sha = _sha_de_um_registro(cliente, tmp_path, na=3, n=256)
    todo = cliente.get(f"/api/onda/{sha}").get_json()
    meio = (todo["de"] + todo["ate"]) / 2

    dados = cliente.get(f"/api/onda/{sha}/leitura",
                        query_string={"t1": meio}).get_json()
    cursor = dados["cursores"][0]
    assert len(cursor["valores"]) == 3
    assert cursor["valores"][0]["unidade"] == "A"
    assert dados["cursores"][1] is None
    assert dados["entre"] is None


def test_a_rota_de_leitura_mede_o_tempo_entre_os_dois(cliente, tmp_path):
    sha = _sha_de_um_registro(cliente, tmp_path, na=1, n=512, taxa=960.0)
    dados = cliente.get(f"/api/onda/{sha}/leitura",
                        query_string={"t1": 0.0, "t2": 16 / 960.0}).get_json()
    assert dados["entre"]["ciclos"] == pytest.approx(1.0, abs=1e-3)
    assert "hz" not in dados["entre"]


def test_as_setas_chegam_ao_servidor(cliente, tmp_path):
    sha = _sha_de_um_registro(cliente, tmp_path, na=1, n=512, taxa=960.0)
    parado = cliente.get(f"/api/onda/{sha}/leitura",
                         query_string={"t1": 0.1}).get_json()["cursores"][0]

    uma = cliente.get(f"/api/onda/{sha}/leitura",
                      query_string={"t1": 0.1, "passo1": 1}).get_json()["cursores"][0]
    ciclo = cliente.get(f"/api/onda/{sha}/leitura",
                        query_string={"t1": 0.1, "ciclos1": 1}).get_json()["cursores"][0]

    assert uma["amostra"] == parado["amostra"] + 1
    assert ciclo["amostra"] == parado["amostra"] + 16


def test_leitura_sem_cursor_nenhum_nao_da_erro(cliente, tmp_path):
    sha = _sha_de_um_registro(cliente, tmp_path, n=64)
    dados = cliente.get(f"/api/onda/{sha}/leitura").get_json()
    assert dados["cursores"] == [None, None]
    assert dados["entre"] is None


def test_leitura_de_registro_que_nao_existe(cliente):
    assert cliente.get("/api/onda/naoexiste/leitura").status_code == 404


def test_a_rota_converte_para_primario(cliente, tmp_path):
    """A tela manda `lado` nos dois pedidos; os dois têm que responder igual."""
    sha = _sha_de_um_registro(cliente, tmp_path, na=1, n=128)
    arquivo = cliente.get(f"/api/onda/{sha}").get_json()["grupos"][0]
    primario = cliente.get(f"/api/onda/{sha}",
                           query_string={"lado": "primario"}).get_json()["grupos"][0]

    assert arquivo["unidade"] == "A"
    assert primario["unidade"] == "kA"          # 12 000 A passam do limiar

    meio = 0.05
    leitura_p = cliente.get(f"/api/onda/{sha}/leitura",
                            query_string={"t1": meio, "lado": "primario"}).get_json()
    assert leitura_p["cursores"][0]["valores"][0]["unidade"] == primario["unidade"]
