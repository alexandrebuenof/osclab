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
    assert dados["paineis"]


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

def test_a_rota_de_leitura_devolve_valor_por_sinal(cliente, tmp_path):
    """A leitura responde o que os painéis pediram, casado por id do sinal.

    Por posição não daria: com painéis, o mesmo canal pode estar em dois
    gráficos com medidas diferentes, e posição deixou de identificar nada.
    """
    sha = _sha_de_um_registro(cliente, tmp_path, na=3, n=256)
    todo = cliente.get(f"/api/onda/{sha}").get_json()
    meio = (todo["de"] + todo["ate"]) / 2
    arranjo = {"paineis": [{"id": "p1", "tipo": "analogico", "nome": "Correntes",
                            "sinais": [f"c{k}:instantaneo" for k in range(3)],
                            "medida": "instantaneo"}]}

    dados = cliente.post(f"/api/onda/{sha}/leitura", json=arranjo,
                         query_string={"t1": meio}).get_json()
    cursor = dados["cursores"][0]
    assert list(cursor["sinais"]) == ["c0:instantaneo", "c1:instantaneo",
                                      "c2:instantaneo"]
    assert cursor["sinais"]["c0:instantaneo"]["unidade"] == "A"
    assert dados["cursores"][1] is None
    assert dados["entre"] is None


def test_sem_painel_nenhum_a_leitura_nao_inventa_sinal(cliente, tmp_path):
    """A tabelinha mostra o que está na tela. Tela vazia, tabelinha vazia —
    e não "todos os canais do arquivo", que ninguém pediu."""
    sha = _sha_de_um_registro(cliente, tmp_path, na=3, n=256)
    dados = cliente.get(f"/api/onda/{sha}/leitura",
                        query_string={"t1": 0.05}).get_json()
    assert dados["cursores"][0]["sinais"] == {}


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


#: O arranjo que a tela manda no corpo do pedido: um painel com um canal só.
UM_PAINEL = {"paineis": [{"id": "p1", "tipo": "analogico", "nome": "Correntes",
                          "sinais": ["c0:instantaneo"], "medida": "instantaneo"}]}


def test_a_rota_converte_para_primario(cliente, tmp_path):
    """A tela manda `lado` nos dois pedidos; os dois têm que responder igual."""
    sha = _sha_de_um_registro(cliente, tmp_path, na=1, n=128)
    arquivo = cliente.post(f"/api/onda/{sha}",
                           json=UM_PAINEL).get_json()["paineis"][0]
    primario = cliente.post(f"/api/onda/{sha}", json=UM_PAINEL,
                            query_string={"lado": "primario"}).get_json()["paineis"][0]

    assert arquivo["unidade"] == "A"
    assert primario["unidade"] == "kA"          # 12 000 A passam do limiar

    meio = 0.05
    leitura_p = cliente.post(f"/api/onda/{sha}/leitura", json=UM_PAINEL,
                             query_string={"t1": meio,
                                           "lado": "primario"}).get_json()
    lido = leitura_p["cursores"][0]["sinais"]["c0:instantaneo"]
    assert lido["unidade"] == primario["unidade"]


def test_o_arranjo_da_tela_vai_no_corpo_do_pedido(cliente, tmp_path):
    """Arranjo é estrutura, e estrutura não cabe em `query string`.

    O nome de um gráfico pode ter vírgula, ponto-e-vírgula e acento; a lista de
    sinais é aninhada. Empacotar isso numa URL seria inventar um formato só
    para ter que desfazê-lo do outro lado — e a URL ainda tem teto de tamanho.
    """
    sha = _sha_de_um_registro(cliente, tmp_path, na=3, n=128)
    pacote = cliente.post(f"/api/onda/{sha}", json={"paineis": [
        {"id": "meu", "tipo": "analogico", "nome": "Só a fase C",
         "sinais": ["c2:instantaneo"], "medida": "rms"},
    ]}).get_json()

    assert len(pacote["paineis"]) == 1
    painel = pacote["paineis"][0]
    assert painel["id"] == "meu"
    assert painel["nome"] == "Só a fase C"          # o nome volta como foi
    assert [s["id"] for s in painel["sinais"]] == ["c2:instantaneo"]


def test_sem_arranjo_no_corpo_a_rota_abre_no_padrao(cliente, tmp_path):
    """A primeira janela nasce antes de a tela ter arranjo nenhum."""
    sha = _sha_de_um_registro(cliente, tmp_path, na=3, n=128)
    do_get = cliente.get(f"/api/onda/{sha}").get_json()
    torto = cliente.post(f"/api/onda/{sha}",
                         json={"paineis": "nada disso"}).get_json()

    assert [p["nome"] for p in do_get["paineis"]] == \
        [p["nome"] for p in torto["paineis"]]
    assert do_get["paineis"][0]["nome"] == "Correntes (A)"


# ---------------------------------------------------------------------------
# O contrato entre o pacote e a tela
# ---------------------------------------------------------------------------

def _campos_lidos_pela_tela(objeto: str) -> set[str]:
    """Os campos que `onda.js` lê de um objeto vindo do servidor.

    Só o primeiro nível: `dados.paineis` entra, `painel.tiras` não. É onde o
    defeito mora — um campo de topo que o servidor deixou de mandar não dá
    erro nenhum no navegador, vira `undefined`, e `undefined` desenha uma tela
    plausível e errada.
    """
    import re

    from osclab import paths
    texto = (paths.STATIC_DIR / "js" / "onda.js").read_text(encoding="utf-8")
    # Fora dos comentários: um campo citado só numa explicação não é leitura.
    # Em duas passadas, e não numa alternância só: `re.S` vale para o padrão
    # INTEIRO, então `//.*` com DOTALL comeria do primeiro `//` até o fim do
    # arquivo — e o teste passaria sempre, sem olhar nada.
    sem = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    sem = re.sub(r"//[^\n]*", "", sem)
    return set(re.findall(rf"\b{objeto}\.([a-z_]+)", sem))


def test_a_tela_nao_le_campo_que_o_servidor_nao_manda(cliente, tmp_path):
    """O defeito que este teste existe para pegar já aconteceu duas vezes.

    A refatoração para painéis tirou `dados.digitais` do pacote, e a tela
    continuou lendo — o resultado não foi erro, foi a margem esquerda parada no
    mínimo e TODO nome de digital cortado, sem nada denunciando. Um campo que
    some é invisível em JavaScript; aqui ele aparece.
    """
    sha = _sha_de_um_registro(cliente, tmp_path, na=3, n=128)
    pacote = cliente.get(f"/api/onda/{sha}").get_json()
    faltando = _campos_lidos_pela_tela("dados") - set(pacote)
    assert not faltando, f"onda.js lê do pacote da janela, e não vem: {faltando}"


def test_a_tela_nao_le_campo_que_a_leitura_nao_manda(cliente, tmp_path):
    """O mesmo, para o pacote dos cursores."""
    sha = _sha_de_um_registro(cliente, tmp_path, na=3, n=128)
    medida = cliente.get(f"/api/onda/{sha}/leitura",
                         query_string={"t1": 0.05}).get_json()
    faltando = _campos_lidos_pela_tela("medida") - set(medida)
    assert not faltando, f"onda.js lê da leitura, e não vem: {faltando}"


def _tokens_do_css() -> dict[str, dict[str, str]]:
    """As cores de traço declaradas no `osclab.css`, por tema.

    Lê o arquivo de verdade em vez de repetir a lista aqui: duas listas da
    mesma paleta é como elas divergem, e a que divergisse seria justamente a
    que o validador confere.
    """
    import re

    from osclab import paths
    texto = (paths.STATIC_DIR / "css" / "osclab.css").read_text(encoding="utf-8")
    # O tema claro vive sob `[data-tema="claro"]`; o escuro é o `:root`. O
    # corte é no SELETOR, em começo de linha — o comentário do topo do arquivo
    # também cita `[data-tema="claro"]`, e cortar ali deixava o tema escuro
    # com zero cores e o teste passando por vacuidade.
    corte = texto.index(':root[data-tema="claro"]')
    pedacos = {"escuro": texto[:corte], "claro": texto[corte:]}
    padrao = re.compile(r"(--(?:fase-[abcn]|calculado-[123]|traco-[123]))\s*:\s*(#[0-9a-f]{6})")
    return {tema: dict(padrao.findall(pedaco)) for tema, pedaco in pedacos.items()}


def test_o_validador_de_paleta_confere_as_cores_QUE_ESTAO_NO_CSS():
    """O `tools/paleta.py` carrega as cores na mão. Se o CSS mudar e ele não,
    ele passa a aprovar uma paleta que ninguém está usando — e a garantia de
    que as cores se separam vira papel."""
    import importlib.util
    import pathlib

    caminho = pathlib.Path(__file__).resolve().parents[1] / "tools" / "paleta.py"
    spec = importlib.util.spec_from_file_location("paleta", caminho)
    paleta = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(paleta)

    do_css = _tokens_do_css()
    for tema, cores in do_css.items():
        assert paleta.TEMAS[tema]["cores"] == cores, (
            f"tema {tema}: o validador e o CSS discordam")


def test_toda_cor_que_a_tela_usa_existe_no_css():
    """Token que não existe devolve string vazia no `getComputedStyle`, e o
    traço sai preto sobre fundo preto — invisível, sem erro nenhum."""
    import re

    from osclab import paths
    js = (paths.STATIC_DIR / "js" / "onda.js").read_text(encoding="utf-8")
    usados = set(re.findall(r'"(--[a-z0-9-]+)"', js))
    css = (paths.STATIC_DIR / "css" / "osclab.css").read_text(encoding="utf-8")
    declarados = set(re.findall(r"(--[a-z0-9-]+)\s*:", css))
    assert not (usados - declarados), f"onda.js usa e o CSS não declara: {usados - declarados}"


def test_as_cores_neutras_vao_da_mais_viva_para_a_mais_apagada():
    """A ordem em que as cores são distribuídas não é gosto, é croma.

    Um gráfico com três sinais calculados tem que receber as três cores que
    mais se separam do fundo e umas das outras; o cinza — que quase não tem
    cor — é o último. A ordem está escrita à mão no `onda.js`, e lista escrita
    à mão sai de ordem: este teste mede o croma de verdade e confere.
    """
    import importlib.util
    import math
    import pathlib
    import re

    from osclab import paths
    caminho = pathlib.Path(__file__).resolve().parents[1] / "tools" / "paleta.py"
    spec = importlib.util.spec_from_file_location("paleta", caminho)
    paleta = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(paleta)

    js = (paths.STATIC_DIR / "js" / "onda.js").read_text(encoding="utf-8")
    bloco = re.search(r"const CORES_NEUTRAS = \[(.*?)\];", js, re.S).group(1)
    ordem = re.findall(r'"(--[a-z0-9-]+)"', bloco)
    assert len(ordem) >= 4

    def croma(token: str) -> float:
        # O menor dos dois temas: uma cor que é viva no escuro e apagada no
        # claro é apagada, para quem está com o tema claro aberto.
        return min(
            math.hypot(*paleta.para_lab(paleta.de_hex(t["cores"][token]))[1:])
            for t in paleta.TEMAS.values()
        )

    cromas = [croma(x) for x in ordem]
    assert cromas == sorted(cromas, reverse=True), (
        f"fora de ordem: {list(zip(ordem, [round(c, 1) for c in cromas], strict=True))}")


def test_o_contrato_e_o_MESMO_nos_dois_lados():
    """O `CONTRATO` existe para pegar servidor velho com tela nova. Só que ele
    é um número escrito em DOIS arquivos, e subir um e esquecer o outro é o
    erro mais fácil do mundo — já aconteceu três vezes nesta sessão.

    Quando os dois divergem no repositório, a tela se recusa a desenhar e manda
    reiniciar o programa: um aviso correto para um problema que não existe, e
    que só aparece depois de subir o servidor e abrir o navegador. Aqui ele
    aparece no pytest.
    """
    import re

    from osclab import paths
    from osclab.plot import janela
    js = (paths.STATIC_DIR / "js" / "onda.js").read_text(encoding="utf-8")
    achado = re.search(r"const CONTRATO = (\d+);", js)
    assert achado, "a tela precisa declarar o CONTRATO dela"
    assert int(achado.group(1)) == janela.CONTRATO, (
        f"onda.js diz {achado.group(1)} e plot/janela.py diz {janela.CONTRATO}")
