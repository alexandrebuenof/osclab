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
    # A raiz é o MENU de módulos desde que o acervo foi para `/arquivos`.
    r = cliente.get("/")
    assert r.status_code == 200
    assert b"OscLab" in r.data
    assert b'href="/arquivos"' in r.data


def test_a_tela_de_arquivos_responde(cliente):
    r = cliente.get("/arquivos")
    assert r.status_code == 200
    assert "Arquivos do projeto" in r.get_data(as_text=True)


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
    # A fábrica escreve `IAW`, `IBW`, `ICW`: uma trinca de corrente e nenhuma
    # de tensão — não há o que distinguir, e o apelido não aparece.
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


def test_a_rota_corrige_a_trinca_de_uma_componente(cliente, tmp_path):
    """A componente é o ÚNICO sinal cuja origem é palpite.

    `IAW · RMS` sai do canal 0 por definição — o id dele diz isso. `3I0 G1`
    sai de três canais que o programa escolheu olhando nomes, e quando escolhe
    errado a componente sai na unidade certa, na ordem de grandeza certa, sem
    nada na tela denunciando.
    """
    cfg = escrever_comtrade(tmp_path, na=6, n=256)
    dat = cfg.with_suffix(".dat")
    envio = {"arquivos": [(cfg.open("rb"), cfg.name), (dat.open("rb"), dat.name)]}
    sha = cliente.post("/api/acervo", data=envio,
                       content_type="multipart/form-data").get_json()["aceitos"][0]["sha"]

    antes = cliente.get(f"/api/onda/{sha}?colunas=200").get_json()
    componente = next(x for x in antes["catalogo"] if x["id"] == "q0:0:rms")
    assert componente["origem"] == "IAW, IBW, ICW"
    assert componente["conjunto"]["canais"] == {"A": 0, "B": 1, "C": 2}
    chave = componente["conjunto"]["chave"]

    # E o sinal de um canal só NÃO traz conjunto: não há o que corrigir ali.
    de_um_canal = next(x for x in antes["catalogo"] if x["id"] == "v0:rms")
    assert de_um_canal["conjunto"] is None

    r = cliente.post(f"/api/onda/{sha}/trincas",
                     json={chave: {"A": 0, "B": 4, "C": 5}})
    assert r.status_code == 200
    assert r.get_json()["trincas"] == {chave: {"A": 0, "B": 4, "C": 5}}

    depois = cliente.get(f"/api/onda/{sha}?colunas=200").get_json()
    corrigida = next(x for x in depois["catalogo"] if x["id"] == "q0:0:rms")
    assert corrigida["origem"] == "IAW, IBX, ICX"


def test_corrigir_trinca_de_registro_que_nao_existe(cliente):
    assert cliente.post("/api/onda/naoexiste/trincas",
                        json={"I*W": {"A": 0, "B": 1, "C": 2}}).status_code == 404


def test_a_tela_pede_colunas_em_PIXEL_DE_VERDADE():
    """O canvas é criado com `largura × devicePixelRatio`, e o Chrome
    multiplica esse fator pelo zoom do navegador: a 80 % ele vale 0,8.

    Pedindo colunas em pixel de CSS, o servidor mandava ~1 ponto por pixel de
    CSS e o canvas tinha 0,8 pixel real para cada um — mais pontos que pixels,
    e o traçador escolhia. Dava batimento no envelope da onda, que não está no
    arquivo. Vale para os dois lados: acima de 100 %, ou em tela HiDPI, o traço
    saía mais grosseiro do que a tela conseguiria mostrar.
    """
    from osclab import paths
    js = (paths.STATIC_DIR / "js" / "onda.js").read_text(encoding="utf-8")
    assert 'p.set("colunas", String(colunasDeVerdade()))' in js
    corpo = js[js.index("function colunasDeVerdade"):]
    corpo = corpo[:corpo.index("\n  }")]
    assert "devicePixelRatio" in corpo
    assert "larguraDisponivel()" in corpo


def test_so_o_AVISO_leva_triangulo():
    """O aviso é do LEITOR — o que ele fez, deixou de fora ou não conseguiu
    confirmar. O relato é do RELÉ: a classificação do evento, a distância que
    ele calculou.

    Carimbar `⚠` numa frase como "o relé classificou o evento como AB T"
    ensina o usuário a ignorar o triângulo, e aí o aviso que importa passa
    despercebido junto. É a mesma regra do `bruto` que saiu do cabeçalho.
    """
    from osclab import paths
    js = (paths.STATIC_DIR / "js" / "acervo.js").read_text(encoding="utf-8")
    trecho = js[js.index("for (const aviso of item.avisos"):]
    trecho = trecho[:trecho.index("return el;")]
    assert '"sinal-de-aviso", "⚠"' in trecho
    # O relato entra sem triângulo nenhum.
    relato = trecho[trecho.index("item.relatos"):]
    assert "⚠" not in relato


def test_o_cabecalho_NAO_anuncia_a_gravacao_bruta():
    """`bruto` é o caso comum — todo COMTRADE do parque cai nele — e um aviso
    que aparece sempre deixa de ser lido.

    O que continua aparecendo é o que MUDA o que se pode fazer: `filtrado`
    trava o botão do filtro, e `desconhecido` diz que o programa não decidiu e
    por isso deixou o botão livre. O diagnóstico em si continua sendo medido —
    ver `analysis/filtragem.py`; o que mudou é quando ele vai para a tela.
    """
    from osclab import paths
    js = (paths.STATIC_DIR / "js" / "onda.js").read_text(encoding="utf-8")
    trecho = js[js.index("function mostrarFiltragem"):]
    trecho = trecho[:trecho.index("alvo.hidden")]
    # Sem a palavra "gravação": ela é o RÓTULO da ficha, escrito pelo CSS logo
    # antes do valor (`data-rot="gravação"`). Repeti-la no valor dava
    # "GRAVAÇÃO gravação já filtrada pelo relé" na mesma linha da tira.
    # Curto e técnico desde 21/10/2026; o resto vai para o hover.
    assert '"já filtrada"' in trecho
    assert '"indeterminada"' in trecho
    assert "gravação bruta" not in trecho


def test_o_botao_da_medida_oferece_o_CONTRARIO_do_que_esta_na_tela():
    """Botão é verbo: ele diz o que o clique VAI DAR, não o que já está.

    Era o estado — escrevia `RMS` com o gráfico em RMS. Lido isolado, isso é
    indistinguível de uma promessa («apertar aqui dá RMS»), e a cada clique a
    palavra trocava para a que acabara de deixar de valer.

    E a largura continua travada, pelo mesmo motivo de sempre: a palavra muda
    a cada clique, e sem o mínimo o «+ sinal» ao lado anda alguns pixels no
    exato instante em que alguém acabou de acertá-lo com o mouse.
    """
    import re

    from osclab import paths
    js = (paths.STATIC_DIR / "js" / "onda.js").read_text(encoding="utf-8")
    trecho = js[js.index("const vaiDar ="):]
    trecho = trecho[:trecho.index("botaoMedida.addEventListener")]
    # Em RMS, o botão oferece o instantâneo — e vice-versa.
    assert 'painel.medida === "rms" ? "instantaneo" : "rms"' in trecho
    assert '"ver RMS" : "ver onda"' in trecho
    # O MESMO desenho do cartão de sinal, e não um ícone só deste botão.
    assert "iconeDaFolha(vaiDar" in trecho
    assert '"instantâneo"' not in js

    css = (paths.STATIC_DIR / "css" / "osclab.css").read_text(encoding="utf-8")
    bloco = css[css.index(".grafico-titulo .medida {"):]
    assert re.search(r"min-width:\s*[\d.]+em", bloco[:bloco.index("}")])


def test_o_nome_do_sinal_e_escrito_INTEIRO_na_tela():
    """Houve uma versão que escrevia a frequência em `<sub class="hz">`, com o
    servidor mandando o nome partido em três. Saiu: `IAW ·60Hz`, com o ponto
    colado no subscrito, lia pior que `IAW · 60Hz`, e o nome passava a existir
    em duas formas que precisavam ser conferidas uma contra a outra.

    Este teste é a guarda da volta: se alguém recriar o subscrito sem recriar o
    estilo dele, o navegador aplica o padrão, que estica a linha — a legenda e
    a tabelinha ganham um pixel de altura só onde há frequência, e as linhas
    deixam de se alinhar.
    """
    from osclab import paths
    js = (paths.STATIC_DIR / "js" / "onda.js").read_text(encoding="utf-8")
    assert 'criar("sub", "hz"' not in js
    assert '"partes"' not in js and ".partes" not in js

def test_o_botao_do_filtro_nao_carimba_uma_FREQUENCIA_no_rotulo():
    """O botão dizia `60 Hz`. Num registro de 50 Hz isso era um rótulo errado
    que nada na tela denunciava — e o rótulo do botão é estático, então nem
    havia como ele acompanhar o arquivo. Agora ele diz o que FAZ, e a setinha
    ao lado diz qual filtro é.
    """
    import re

    from osclab import paths
    html = (paths.TEMPLATES_DIR / "onda.html").read_text(encoding="utf-8")
    botao = re.search(r'<button[^>]*id="filtro"[^>]*>(.*?)</button>', html,
                      re.S)
    assert botao, "o botão do filtro sumiu do onda.html"
    assert not re.search(r"\d+\s*Hz", botao.group(1)), botao.group(1)


def test_o_menu_suspenso_nasce_VAZIO_no_html():
    """Fechar um menu é esvaziar a âncora dele. Se a âncora fosse o grupo
    inteiro, fechar levaria os botões junto — foi o que aconteceu na primeira
    tentativa do menu do ímã. Os dois pontos de montagem têm que estar vazios.
    """
    import re

    from osclab import paths
    html = (paths.TEMPLATES_DIR / "onda.html").read_text(encoding="utf-8")
    for alvo in ("menu-do-ima", "menu-do-filtro"):
        achado = re.search(rf'<span id="{alvo}">(.*?)</span>', html, re.S)
        assert achado, f"o ponto de montagem {alvo} sumiu"
        assert not achado.group(1).strip(), f"{alvo} nasceu com conteúdo dentro"


def test_TODA_classe_que_a_tela_cria_existe_no_css():
    """`criar("div", "menu-suspenso")` com o CSS ainda chamando `.menu-ima`
    deixa o menu sem borda, sem fundo e por cima do gráfico — funcionando, e
    ilegível. Não dá erro nenhum.

    Confere só as classes de UMA palavra que o `onda.js` cria: as compostas
    (`achado mudou`) misturam classe de estado, que o CSS declara junto.
    """
    import re

    from osclab import paths
    js = (paths.STATIC_DIR / "js" / "onda.js").read_text(encoding="utf-8")
    css = (paths.STATIC_DIR / "css" / "osclab.css").read_text(encoding="utf-8")
    declaradas = set(re.findall(r"\.([a-z][a-z0-9-]*)", css))
    usadas = {c for c in re.findall(r'criar\("[a-z]+",\s*"([a-z0-9-]+)"', js)}
    assert not (usadas - declaradas), f"o onda.js cria e o CSS não tem: {usadas - declaradas}"


def test_o_RODAPE_do_painel_diz_de_que_canais_do_arquivo_aquilo_saiu(cliente,
                                                                     tmp_path):
    """É a contrapartida do `G1`.

    O ordinal não depende de fabricante nenhum, e é justamente por não depender
    que ele não diz nada sozinho: `G1` é a primeira trinca DAQUELE arquivo. O
    rodapé é onde o programa responde "`G1` é qual?", citando os nomes do
    arquivo entre aspas — sem elas, um `TC BUC 69kV:I A` no meio de uma lista
    com espaços e dois-pontos vira sopa, e um `J1 -IA` parece subtração.

    Já houve a rotulagem manual no lugar disto. Ela existia para CONSERTAR um
    palpite do programa; o programa não palpita mais, então não há o que
    consertar — há o que INFORMAR, e informar é barato.
    """
    cfg = escrever_comtrade(tmp_path, na=6, n=256)
    dat = cfg.with_suffix(".dat")
    envio = {"arquivos": [(cfg.open("rb"), cfg.name), (dat.open("rb"), dat.name)]}
    sha = cliente.post("/api/acervo", data=envio,
                       content_type="multipart/form-data").get_json()["aceitos"][0]["sha"]

    pacote = cliente.get(f"/api/onda/{sha}?colunas=200").get_json()
    graficos = [p for p in pacote["paineis"] if p["tipo"] == "analogico"]
    # Os dois painéis se chamam igual — o título é só a unidade — e quem os
    # distingue é o nome dos canais, que é o do arquivo.
    assert [p["nome"] for p in graficos] == ["Correntes (A)", "Correntes (A)"]
    assert [s["sinal"] for s in graficos[0]["sinais"]] == ["IAW", "IBW", "ICW"]
    assert [s["sinal"] for s in graficos[1]["sinais"]] == ["IAX", "IBX", "ICX"]

    # Sem calculado no gráfico não há rodapé: o nome do canal já está na
    # legenda, e o grupo dele se pergunta no catálogo ou no editor de grupos.
    assert graficos[0]["rodape"] == []
    assert graficos[1]["rodape"] == []

    # Com a componente, o rodapé aparece e diz de que trinca ela saiu.
    arranjo = {"paineis": [{"id": "p1", "tipo": "analogico", "nome": "",
                            "sinais": ["c0:instantaneo", "q0:0:rms"],
                            "medida": "instantaneo"}]}
    com = cliente.post(f"/api/onda/{sha}?colunas=200", json=arranjo).get_json()
    assert com["paineis"][0]["rodape"] == [
        'G1 — "IAW", "IBW", "ICW"',
        "componentes simétricas: módulo do fasor de um ciclo, em eficaz",
    ]


def test_o_rodape_NAO_aparece_quando_nao_ha_CALCULADO(cliente, tmp_path):
    """Um painel com as três fases e mais nada não tem rodapé: a linha
    repetiria o nome do arquivo que já está na legenda. Ela existe para
    traduzir o `G1` de um `3I0 G1` — o que sai de TRÊS canais e não tem nome de
    arquivo a herdar."""
    sha = _sha_de_um_registro(cliente, tmp_path, na=3, n=128)
    pacote = cliente.get(f"/api/onda/{sha}?colunas=200").get_json()
    grafico = next(p for p in pacote["paineis"] if p["tipo"] == "analogico")
    assert grafico["nome"] == "Correntes (A)"
    assert grafico["rodape"] == []


def test_o_traco_suave_so_vale_onde_ha_POUCA_amostra_por_ciclo():
    """Num sinal com descontinuidade de verdade — a entrada de uma falta num
    registro bruto — uma curva suave passaria por fora do degrau e desenharia
    um pico que não existe. Registro filtrado não tem degrau.

    A regra mora no `onda.js`; o que este teste guarda é que ela continua
    CONDICIONAL, e não aplicada a todo traço.
    """
    from osclab import paths
    js = (paths.STATIC_DIR / "js" / "onda.js").read_text(encoding="utf-8")
    assert "AMOSTRAS_PARA_SUAVIZAR = 8" in js
    assert "dados.amostras_da_janela_do_fasor <= AMOSTRAS_PARA_SUAVIZAR" in js
    # E nunca sobre traço reduzido: ali o desenho já é mínimo e máximo por
    # coluna de pixel, e arredondar isso inventaria forma onde há estatística.
    assert "!dados.reduzido" in js


def test_canal_sem_vinculo_NAO_e_anunciado_como_problema():
    """A coluna fica vazia, e essa é a decisão.

    Escrevia «não reconhecido» em cor de aviso. A tensão da bateria e as
    grandezas que o relé já calculou nunca vão ter vínculo, porque não são fase
    de nada: a linha inteira ficava marcada como problema num registro em que
    não há problema nenhum. Aviso que aparece no caso normal deixa de ser lido
    como aviso e passa a ser lido como defeito do programa.
    """
    from osclab import paths
    js = (paths.STATIC_DIR / "js" / "onda.js").read_text(encoding="utf-8")
    assert "não reconhecido" not in js
    css = (paths.STATIC_DIR / "css" / "osclab.css").read_text(encoding="utf-8")
    assert ".vinculo.nenhum" not in css, "sobrou regra de CSS sem dono"


# ---------------------------------------------------------------------------
# O apelido do registro, e a exportação com ele
# ---------------------------------------------------------------------------

def test_renomear_vale_na_TELA_e_nao_no_disco(cliente, tmp_path):
    """`UPC1 ALIMENTADOR 11SEL-451-521_09_202613...` é o nome que o fabricante
    exporta, e ele não diz que evento é aquele. O nome novo vale dentro do
    OscLab; o arquivo continua com o nome original, porque é pelo nome base que
    o leitor acha o `.dat` a partir do `.cfg`."""
    from osclab.library import acervo

    sha = _sha_de_um_registro(cliente, tmp_path, na=3, n=128)
    de_antes = acervo.obter(sha).nome_do_arquivo

    r = cliente.post(f"/api/acervo/{sha}/nome",
                     json={"nome": "  curto na SE Barra do Garças  "})
    assert r.status_code == 200
    assert r.get_json()["nome"] == "curto na SE Barra do Garças"
    assert r.get_json()["nome_do_arquivo"] == de_antes

    # O acervo passa a mostrar o nome novo; os arquivos no disco, não.
    assert acervo.obter(sha).nome == "curto na SE Barra do Garças"
    nomes = {c.name for c in acervo.pasta_do_registro(sha).iterdir()}
    assert f"{de_antes}.cfg" in nomes and f"{de_antes}.dat" in nomes

    # Apagar o apelido devolve o nome do arquivo, sem precisar lembrar dele.
    r = cliente.post(f"/api/acervo/{sha}/nome", json={"nome": "   "})
    assert r.get_json()["nome"] == de_antes
    assert acervo.obter(sha).nome == de_antes


def test_o_apelido_nao_aceita_o_que_estraga_nome_de_arquivo(cliente, tmp_path):
    """O apelido vira nome de arquivo na exportação: `19/01` ali abriria uma
    pasta que não existe."""
    from osclab.library import acervo

    sha = _sha_de_um_registro(cliente, tmp_path, na=3, n=128)
    r = cliente.post(f"/api/acervo/{sha}/nome", json={"nome": 'curto 19/01 <A:B>'})
    assert r.get_json()["nome"] == "curto 19-01 -A-B-"
    assert acervo.obter(sha).nome == "curto 19-01 -A-B-"


def test_exportar_sai_em_zip_com_os_DOIS_arquivos_renomeados(cliente, tmp_path):
    """Um COMTRADE são dois arquivos, e o leitor acha um a partir do outro pelo
    NOME BASE: renomear só um entregaria um par que não abre."""
    import io
    import zipfile

    sha = _sha_de_um_registro(cliente, tmp_path, na=3, n=128)
    cliente.post(f"/api/acervo/{sha}/nome", json={"nome": "curto na SE"})

    r = cliente.get(f"/api/acervo/{sha}/exportar")
    assert r.status_code == 200
    assert "curto na SE.zip" in r.headers["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(r.data)) as zip_:
        assert sorted(zip_.namelist()) == ["curto na SE.cfg", "curto na SE.dat"]
        # E o conteúdo é o do arquivo, não um arquivo vazio com nome bonito.
        assert zip_.read("curto na SE.cfg").decode("utf-8").strip()


def test_o_desenho_e_o_clique_dividem_as_pistas_pela_MESMA_conta():
    """Quem desenha e quem decide em que traço se clicou têm que usar a mesma
    divisão em pistas.

    Se as duas divergirem um pixel, clicar na fase B marca a fase A — e isso
    não aparece em teste de número nenhum, nem no gráfico: a tela fica certa,
    só a seleção fica errada. Por isso a conta é uma função só, e este teste
    guarda que os dois lugares continuam chamando ELA.

    `pintar` desenha; `sinalPerto` responde ao clique.
    """
    from osclab import paths
    js = (paths.STATIC_DIR / "js" / "onda.js").read_text(encoding="utf-8")

    for quem in ("function pintar(", "function sinalPerto("):
        inicio = js.index(quem)
        # Até o fim da função: o próximo `\n  }` na coluna da declaração.
        corpo = js[inicio:]
        corpo = corpo[:corpo.index("\n  }\n")]
        assert "pistasDoPainel(" in corpo, quem

    # E a divisão tem que usar a escala do PAINEL, não uma por pista: três
    # ondas normalizadas para encher cada faixa diriam que as três fases estão
    # iguais numa falta monofásica.
    inicio = js.index("function pistasDoPainel(")
    corpo = js[inicio:js.index("\n  }\n", inicio)]
    assert "painel.minimo" not in corpo and "painel.maximo" not in corpo


# ---------------------------------------------------------------------------
# A barra da onda
# ---------------------------------------------------------------------------

def _onda_js() -> str:
    from osclab import paths
    return (paths.STATIC_DIR / "js" / "onda.js").read_text(encoding="utf-8")


def test_a_barra_da_onda_pede_as_DUAS_condicoes():
    """Ela aparece com o cursor em movimento E sem analógico na tela.

    Uma condição só não serve, e cada uma erra para um lado: sem o movimento
    ela fica pendurada o tempo todo cobrindo o topo da tela; sem a segunda ela
    desenha a mesma onda que já está à vista, duas vezes, uma delas pior.
    """
    js = _onda_js()
    trecho = js[js.index("function barraCabe()"):]
    trecho = trecho[:trecho.index("function montarBarra")]
    assert "movendoCursor" in trecho
    assert "!algumAnalogicoNaTela()" in trecho


def test_o_analogico_so_conta_como_VISIVEL_com_meia_altura_na_tela():
    """Um gráfico que aparece pela borda com dez pixels não localiza ninguém —
    e é justamente aí que a barra tem que entrar."""
    js = _onda_js()
    trecho = js[js.index("function algumAnalogicoNaTela()"):]
    trecho = trecho[:trecho.index("function barraCabe")]
    assert "r.height / 2" in trecho


def test_a_barra_da_onda_e_sempre_AGRUPADA():
    """Mesmo com o painel em «um sinal por gráfico».

    São quarenta e quatro pixels: três pistas dariam catorze cada, e em catorze
    pixels não se vê forma de onda nenhuma — que é a única coisa que a barra
    tem para dizer. Então ela desenha os sinais do painel num laço só, sem
    passar por `pistasDoPainel`.
    """
    js = _onda_js()
    trecho = js[js.index("function pintarBarra()"):]
    trecho = trecho[:trecho.index("  // --- cursores de medição")]
    assert "pistasDoPainel" not in trecho
    assert "empilhado" not in trecho
    assert "for (const sinal of painel.sinais)" in trecho


def test_a_barra_ocupa_o_LUGAR_do_canvas_que_espelha():
    """O risco do cursor tem que cair na mesma coluna de pixel do gráfico
    grande. Isso só acontece se a barra tiver a mesma esquerda, a mesma largura
    e as mesmas margens do desenho — com outra largura a posição vira apenas
    proporcional, e o olho não liga uma coisa à outra sozinho."""
    js = _onda_js()
    trecho = js[js.index("function pintarBarra()"):]
    trecho = trecho[:trecho.index("  // --- cursores de medição")]
    assert "bloco_._canvas.getBoundingClientRect()" in trecho
    assert "caixa.style.left" in trecho
    assert "caixa.style.width" in trecho
    assert "const x0 = MARGEM.esq;" in trecho
    assert "const x1 = L - MARGEM.dir;" in trecho


def test_o_Tab_so_e_sequestrado_com_a_barra_na_tela():
    """Fora dela, `Tab` continua sendo a tecla de navegação do navegador —
    sequestrá-la sempre quebraria o teclado de quem não usa mouse. E a volta
    fecha: do último analógico ela retorna ao primeiro."""
    js = _onda_js()
    trecho = js[js.index('if (evento.key === "Tab"'):]
    trecho = trecho[:trecho.index('if (evento.key === "Delete"')]
    assert "barraCabe()" in trecho
    assert "% quantos" in trecho          # a volta fecha no primeiro


def test_a_barra_SOME_quando_o_gesto_acaba():
    """Com o mouse o `pointerup` diz exatamente quando; pelo teclado não há
    evento de fim, e ela fica mais um instante antes de sumir sozinha."""
    js = _onda_js()
    soltar = js[js.index("function soltar(evento)"):]
    soltar = soltar[:soltar.index("if (faixa) {")]
    assert "terminouDeMoverCursor();" in soltar
    assert "terminouDeMoverCursor(BARRA_SOME_EM);" in js


def test_a_faixa_do_registro_INTEIRO_saiu_do_programa(cliente, tmp_path):
    """Ela era a tentativa anterior: uma tira com o arquivo todo, embaixo do
    último painel, em eficaz. Saiu porque respondia a pergunta errada — o
    usuário queria ver EM QUE PONTO DA ONDA o cursor está, e em duzentas
    colunas sobre sessenta ciclos não existe onda para mostrar. Quem responde
    isso agora é a barra, que espelha a janela e não o arquivo.
    """
    sha = _sha_de_um_registro(cliente, tmp_path)
    assert cliente.get(f"/api/onda/{sha}/visao").status_code == 404

    js = _onda_js()
    for sumido in ("pintarFaixaDeContexto", "pintarMiniatura", "buscarVisao",
                   "ALTURA_DA_FAIXA"):
        assert sumido not in js, f"{sumido} ficou para trás no onda.js"

    from osclab.plot import janela
    assert not hasattr(janela, "visao_geral")


def test_o_PASSO_da_lista_de_sinais_e_multiplo_de_quatro():
    """Por que as barras de energia pareciam de espessuras diferentes.

    A barra tem altura inteira em pixels de tela (4px → 5 a 125 %), mas altura
    inteira não basta: uma barra de 5 pixels que começa em 402,11 pinta de
    402,11 a 407,11 e toca SEIS fileiras, a primeira com 89 % de tinta e a
    última com 11 %. Na linha de baixo a fração é outra, e a mesma barra
    aparece mais grossa.

    O que torna a fração igual em todas as linhas é o PASSO da lista ser um
    múltiplo de 4 px de CSS — 4 vira inteiro nos zooms que existem na prática
    (×1,25 = 5; ×1,5 = 6; ×1,75 = 7; ×2 = 8). Então o cartão mede 30 e o vão
    2, e o cabeçalho de bloco tem altura TRAVADA, senão o bloco dos calculados
    (com o `ƒx`, mais alto) desencontra tudo que vem depois dele.
    """
    import re

    from osclab import paths
    css = (paths.STATIC_DIR / "css" / "osclab.css").read_text(encoding="utf-8")

    def valor(seletor, campo):
        bloco = css[css.index(seletor):]
        bloco = bloco[:bloco.index("}")]
        achado = re.search(rf"{campo}:\s*([\d.]+)px", bloco)
        assert achado, f"{campo} sumiu de {seletor}"
        return float(achado.group(1))

    # As três medidas da grade saem de VARIÁVEIS, e os valores de partida
    # delas moram no `:root`: é o `ajustarGradeDaLista`, no `onda.js`, que as
    # reescreve arredondadas para um número inteiro de pixels de tela.
    raiz = css[css.index(":root {"):]
    raiz = raiz[:raiz.index("\n}")]
    def doRoot(nome):
        achado = re.search(rf"{nome}:\s*([\d.]+)px", raiz)
        assert achado, f"{nome} sumiu do :root"
        return float(achado.group(1))

    alto = doRoot("--miolo-do-cartao")                   # 20
    vao = doRoot("--vao-do-cartao")                      # 2
    # 20 de conteúdo + 4+4 de respiro + 1+1 de moldura = 30; com o vão, 32.
    passo = alto + 8 + 2 + vao
    assert passo % 4 == 0, f"o passo da lista deu {passo}px, e não é múltiplo de 4"
    assert doRoot("--alto-da-barra") == 4

    # E o CSS usa as variáveis, em vez dos números soltos de antes.
    assert "min-height: var(--miolo-do-cartao, 20px);" in css
    assert "height: var(--alto-da-barra, 4px);" in css
    assert "margin: 0 0 var(--vao-do-cartao, 2px);" in css

    assert valor(".busca .cabeca-de-bloco {", "height") % 4 == 0
    assert valor(".busca .bloco-do-grupo .cabeca-de-bloco {", "height") % 4 == 0


def test_a_moldura_do_cursor_copia_a_geometria_do_desenho_analogico():
    """O risco da moldura tem que cair na MESMA coluna de pixel do cursor no
    gráfico de ondas. Isso exige copiar a largura E a esquerda do desenho
    analógico — o corpo do fasorial e o dos harmônicos começam em outro lugar,
    e só a largura deixava a moldura vinte pixels à direita.
    """
    js = _onda_js()
    trecho = js[js.index("function pintarMolduras("):]
    trecho = trecho[:trecho.index("function comMolduras(")]
    assert "refDoDesenho()" in trecho
    assert "ref.width" in trecho
    assert "ref.left" in trecho


def test_a_moldura_reserva_a_altura_da_etiqueta_SEMPRE():
    """Com ou sem cursor. Se a etiqueta só ocupasse espaço quando há cursor, o
    painel inteiro pularia 11 px a cada `1` ou `Esc`."""
    js = _onda_js()
    trecho = js[js.index("function pintarMolduras("):]
    trecho = trecho[:trecho.index("function comMolduras(")]
    assert "const alto = comEtiqueta ? ETIQUETA_DA_MOLDURA + SULCO : SULCO;" \
        in trecho


def test_a_moldura_nao_usa_a_classe_topo():
    """`.topo` é o cabeçalho da PÁGINA, com 20 px de respiro à esquerda e
    `display: flex`. Uma moldura com essa classe herdava os dois e saía
    desalinhada do desenho — o defeito que ela existe para não ter."""
    js = _onda_js()
    assert 'moldura-${onde}' in js
    assert '"moldura-do-cursor topo"' not in js


def test_a_tira_digital_cai_no_PIXEL_DA_TELA():
    """O terceiro caso do mesmo defeito, depois das barras de energia e das
    molduras — e desta vez na grade da TELA, não na do CSS.

    Arredondar em pixel de CSS não bastava: num monitor a 125% (o do
    laboratório), um `x` inteiro em CSS vale 1,25 px de tela e só é inteiro de
    quatro em quatro. Nos outros três a borda cai no meio de um pixel físico e
    o navegador a dilui em duas colunas — a barra fina e a grossa, diluídas
    cada uma para o seu lado, mostram um fiozinho mais claro exatamente na
    troca de 0 para 1. Era a «leve descontinuidade» que sobrou depois da
    primeira correção.

    Três condições, as três aqui: altura par, e as bordas (x e y) na grade da
    tela.
    """
    import re

    js = _onda_js()
    fina = float(re.search(r"const FINA = ([\d.]+);", js).group(1))
    grossa = float(re.search(r"const GROSSA = ([\d.]+);", js).group(1))
    assert fina % 2 == 0, f"FINA = {fina}, e altura ímpar cai em meio pixel"
    assert grossa % 2 == 0, f"GROSSA = {grossa}, idem"

    assert "const noPixel = (v) => Math.round(v * dpr) / dpr;" in js

    trecho = js[js.index("const trecho = (i, j, ligado) =>"):]
    trecho = trecho[:trecho.index("let inicio = 0;")]
    assert "noPixel(emX(tempo[i]))" in trecho
    assert "noPixel(fim(j))" in trecho
    assert "noPixel(meio - alto / 2)" in trecho
    assert "noPixel(meio + alto / 2)" in trecho
    # O destaque da tira escolhida não pode quebrar a paridade.
    assert "(escolhida ? 2 : 0)" in trecho


def test_a_cor_das_tiras_e_de_CADA_painel():
    """Dois painéis de digitais na tela — um de proteção, outro de comando —
    podem querer cores diferentes. E o padrão volta a ser padrão: escolher
    «--digital» grava `null`, senão o painel ficaria preso ao tom de hoje se
    ele mudar no tema ou na versão."""
    js = _onda_js()
    trecho = js[js.index("function escolherCorDasTiras("):]
    trecho = trecho[:trecho.index("function abrirPaletaDasTiras(")]
    assert 'cor === "--digital" ? null : cor' in trecho
    assert 'return token(meu.cor_tiras || "--digital");' in js


def test_o_PINCEL_pinta_uma_tira_e_a_mesma_cor_de_novo_APAGA():
    """O pincel é o que pinta e o que apaga: assim ninguém precisa procurar
    uma borracha. Escolha dele, 19/10/2026."""
    js = _onda_js()
    assert "function pincelarTira(" in js
    assert "agora === pincel.cor ? \"\" : pincel.cor" in js
    # a cor do pincel mora no mesmo lugar da cor de um traço: na tela, no
    # Ctrl+Z, e longe do servidor
    assert "escolherCor(painel.id, qual," in js
    assert "--ic-pincel:" in _osclab_css()


def test_o_pincel_mora_no_CABECALHO_DO_PAINEL_de_digitais():
    """É ali que ele age. Uma ferramenta que só vale para um painel, posta no
    cabeçalho da tela inteira, promete o que não cumpre — ele mandou tirar de
    lá em 19/10/2026."""
    onda = _template("onda.html")
    assert 'id="pincel"' not in onda          # saiu da fileira de chaves
    assert 'id="cor-do-pincel"' not in onda
    js = _onda_js()
    assert "function controleDoPincel(" in js
    assert "[busca, controleDoPincel(painel), ...engrenagemDoPainel(" in js
    # e o modo de pintar é de CADA painel
    assert "pincel.pintando[painel.id] = !pintando(painel.id)" in js
    assert ".controle-do-pincel" in _osclab_css()


def test_o_pincel_e_o_circulo_sao_DOIS_alvos_numa_peca_so():
    """Dois botões soltos lado a lado se leriam como duas ferramentas; com a
    moldura em volta, lê-se como uma ferramenta com uma cor carregada."""
    js = _onda_js()
    assert 'criar("button", "lado-pincel")' in js
    assert 'criar("button", "lado-cor")' in js
    assert "abrirPaletaDoPincel(botaoCor, painel.id)" in js
    css = _osclab_css()
    assert ".controle-do-pincel .lado-cor" in css
    assert ".controle-do-pincel.pintando" in css


def test_a_engrenagem_das_digitais_vem_em_dois_GRUPOS():
    """«Agrupar» e «Cor», cada um com as suas opções — escolha dele,
    19/10/2026. Seis botões soltos na mesma caixa não têm onde o olho parar."""
    js = _onda_js()
    trecho = js[js.index("[busca, controleDoPincel(painel)"):]
    trecho = trecho[:trecho.index("])],")]
    assert trecho.index('"Agrupar"') < trecho.index('"Cor"')
    assert "chaveDeAgrupar(painel, \"nenhum\")" in trecho
    assert "chaveDeAgrupar(painel, \"categoria\")" in trecho
    assert "botaoDaCorDasTiras(painel)" in trecho
    assert 'chaveDeCategoria(painel, "pintar")' in trecho
    assert '"sem agrupamento"' in js
    assert "function desagrupar(" in js
    assert ".titulo-de-grupo" in _osclab_css()


def test_a_cor_de_uma_tira_segue_a_ordem_pincel_categoria_painel():
    """O que a mão fez à mão é o mais específico que existe, e não pode ser
    desfeito por uma chave ligada depois sem ninguém entender por quê."""
    js = _onda_js()
    trecho = js[js.index("function corDaTira("):]
    trecho = trecho[:trecho.index("/** A paleta do PINCEL")]
    assert trecho.index("meu.cores") < trecho.index("por_categoria")
    assert trecho.index("por_categoria") < trecho.index("cor_tiras")


def test_as_opcoes_por_CATEGORIA_nascem_apagadas_sem_dicionario():
    """Apagada e CLICÁVEL: o clique diz o que falta. Chave que não responde é
    a tela discutindo com quem clicou."""
    js = _onda_js()
    assert "function chaveDeCategoria(" in js
    assert '"pintar por categoria"' in js
    assert '"agrupar por categoria"' in js
    assert 'b.classList.add("sem-dicionario")' in js
    assert "Sem dicionário não há categoria" in js
    assert ".medida.sem-dicionario" in _osclab_css()


def test_AGRUPAR_por_categoria_reordena_os_sinais_e_recarrega():
    """É o servidor que monta as tiras na ordem em que os sinais chegam — a
    mesma estrada de quando se acrescenta um sinal novo."""
    js = _onda_js()
    assert "function agruparPorCategoria(" in js
    assert "trocarSinais(painel.id, ordenados);" in js
    assert 'CATEGORIAS_EM_ORDEM = ["trip", "partida", "bloqueio", "estado", "io",' in js


def _osclab_css() -> str:
    from osclab import paths
    return (paths.STATIC_DIR / "css" / "osclab.css").read_text(encoding="utf-8")


def test_o_clique_no_desenho_nao_e_desfeito_pela_regra_do_clique_FORA():
    """Clicar num traço ou numa tira destacava o sinal — e o destaque sumia no
    mesmo gesto.

    A escolha acontece no `pointerup`. O `click` que vem logo depois tem como
    alvo a ÁREA inteira, não o canvas: a captura de ponteiro o retira do
    caminho normal de eventos. `areaDoEvento`, que pergunta pelo alvo,
    devolvia `null` ali; `noDesenho(null)` dá falso; e a regra de «clicou
    fora, limpa a seleção» apagava o que o `pointerup` tinha acabado de
    escolher. Por isso só o nome da legenda funcionava.

    A correção é a mesma que o `painelEscolhido` logo acima já fazia sozinho:
    decidir pela POSIÇÃO do clique.
    """
    js = _onda_js()
    assert "function areaPelaPosicao(evento)" in js
    assert "noDesenho(areaDoEvento(evento) || areaPelaPosicao(evento))" in js
    # E o gesto do cursor não pode levar a seleção junto: é na moldura e na
    # barra que se PEGA o cursor, e as duas ficam fora de qualquer desenho.
    assert '.closest(".moldura-do-cursor, .barra-da-onda")' in js


def test_o_clique_DUPLO_destaca_a_tira_digital():
    """E mora na ÁREA, não no canvas: a captura de ponteiro do arrasto leva o
    `click` e o `dblclick` junto para a área, e um ouvinte no canvas nunca é
    chamado — foi assim que a primeira versão disto não fez nada.

    E marca, em vez de alternar: os dois cliques do duplo já ligaram e
    desligaram a tira pelo caminho normal.
    """
    js = _onda_js()
    trecho = js[js.index('area.addEventListener("dblclick"'):]
    trecho = trecho[:trecho.index("// Sair da área")]
    assert "areaDoEvento(evento) || areaPelaPosicao(evento)" in trecho
    assert "digitalPerto(painel, a.y)" in trecho
    assert "marcarSelecao(" in trecho
    assert "alternarSelecao(" not in trecho


def test_o_cursor_da_MOLDURA_se_arrasta():
    """A moldura existe para que o fasorial e os harmônicos sejam lidos sem
    perder o cursor de vista. Mostrando o risco e não deixando pegá-lo, ela
    obrigava a rolar a tela até um analógico — exatamente o que ela veio
    evitar."""
    js = _onda_js()
    assert "function cursorArrastavelNaMoldura(m)" in js
    assert "for (const m of el._molduras) cursorArrastavelNaMoldura(m);" in js
    trecho = js[js.index("function cursorArrastavelNaMoldura(m)"):]
    trecho = trecho[:trecho.index("function comMolduras(")]
    # Pelo ímã, como na onda: dois jeitos de parar no mesmo ponto não podem
    # dar dois valores.
    assert "grudarCursor(pego," in trecho
    assert "lerCursores();" in trecho


def test_ver_amostras_ACENDE_sem_refazer_o_bloco():
    """O clique ligava os pontos e não dizia nada: `desenharTudo` refazia os
    blocos, a âncora do menu morria junto e o botão sumia antes de ser visto
    aceso. Os pontinhos são detalhe de canvas — repintar basta.

    E `escolhido`, que é a classe de aceso dos botões de gráfico; `aceso` é a
    dos seletores de duas teclas e não tem regra para `.medida`.
    """
    js = _onda_js()
    trecho = js[js.index("function alternarAmostras("):]
    trecho = trecho[:trecho.index("function alternarEmpilhado(")]
    assert "repintarAgora();" in trecho
    assert "desenharTudo();" not in trecho
    assert 'b.classList.toggle("escolhido", ligado);' in js
    assert ".menu-suspenso .linha-de-ajuste .medida.escolhido" in _osclab_css()


def test_a_ficha_ESCRITA_PELO_JS_nao_empilha_o_conteudo():
    """A ficha é de duas linhas — rótulo em cima, valor embaixo — e continua
    sendo.

    O que estava torto eram só as três fichas que o JavaScript escreve: elas
    herdavam a flex-coluna das outras, e o conteúdo da dos canais sem sinal
    («6 canais», o «·» e o botão) virava três itens de flex, um por linha,
    centralizados. Em bloco, o rótulo é o `::before` — que é `block`, e por
    isso fica em cima como nas demais — e o resto flui inline.
    """
    css = _osclab_css()
    ficha = css[css.index(".tira .fi {"):css.index(".tira .val")]
    assert "flex-direction: column" in ficha, "a ficha é de duas linhas"
    assert ".tira .fi-js { display: block; min-width: 0; }" in css
    rotulo = css[css.index("content: attr(data-rot);"):][:60]
    assert "display: block;" in rotulo


def test_a_resposta_ATRASADA_nao_mexe_no_cursor_que_esta_na_mao():
    """O servidor encosta o cursor na amostra mais próxima, e a resposta chega
    alguns milissegundos depois. Aplicá-la no cursor que a mão está arrastando
    puxa a linha de volta para onde o mouse estava — um cabo de guerra que se
    vê como a linha se teletransportando.

    O arrasto no GRÁFICO já era protegido por `arrastando.cursor`; o arrasto na
    MOLDURA não existia quando aquilo foi escrito e não entrava na regra, e era
    lá que o defeito aparecia. Agora quem responde é um só: `cursorNaMao`.
    """
    js = _onda_js()
    assert "let cursorNaMao = null;" in js
    assert "if (cursorNaMao === k) return;" in js
    assert "if (arrastando && arrastando.cursor === k) return;" not in js
    # Posto e tirado nos DOIS arrastos.
    assert js.count("cursorNaMao = k;") == 2
    assert js.count("cursorNaMao = null;") == 3     # a declaração e os dois fins


def test_a_escala_do_fasorial_nao_e_MENU_DENTRO_DE_MENU():
    """O caminho continua sendo ajustes → escala → as duas opções, mas o
    segundo passo abre DENTRO da caixa do primeiro.

    `menuSuspenso` mantém um menu aberto por vez: abrir o segundo fechava a
    engrenagem, e a engrenagem levava junto a âncora onde o segundo ia nascer.
    O clique fechava tudo sem fazer nada.

    E escolher não refaz o bloco, senão a engrenagem fecharia na cara de quem
    acabou de clicar.
    """
    js = _onda_js()
    trecho = js[js.index("function botaoDaEscala(painel)"):]
    trecho = trecho[:trecho.index("const explicacaoDaEscala")]
    assert "menuSuspenso(" not in trecho
    assert "lista.hidden" in trecho           # as opções abrem ali mesmo
    assert 'criar("div", "opcoes-do-ajuste")' in trecho
    escolher = js[js.index("function escolherEscala("):]
    escolher = escolher[:escolher.index("function alternarCursorDoPainel(")]
    assert "repintarAgora();" in escolher
    assert "mostrarBasesDoPu();" in escolher
    assert "desenharTudo();" not in escolher


def test_o_PAR_do_fasorial_e_um_mais_na_DIREITA():
    """Ele não ajusta este gráfico — cria outro, como o × tira. Criar e tirar
    moram no mesmo canto; a engrenagem é para ajuste."""
    js = _onda_js()
    trecho = js[js.index("function blocoFasorial(painel)"):]
    trecho = trecho[:trecho.index("const corpo = criar(\"div\", \"corpo-fasorial\")")]
    assert 'criar("button", "mexer", "+")' in trecho
    assert "criarParFasorial(painel.id)" in trecho
    assert "cabecalhoDoPainel(painel, botoes, null, direita)" in trecho


def test_os_controles_do_CABECALHO_tem_a_mesma_altura_e_o_mesmo_vao():
    """Medido antes de mexer: botões de texto 18 px, engrenagem 16, ▲▼× 20. E
    o vão não era um só — depois de um botão com menu vinha a âncora dele, um
    elemento de largura zero que, por ser item do flex, cobrava o `gap` duas
    vezes: 20 px onde os outros têm 10."""
    css = _osclab_css()
    trecho = css[css.index(".grafico-titulo {\n  --gap-do-titulo"):]
    trecho = trecho[:trecho.index(".grafico-titulo .medida,\n.novo-painel .medida")]
    assert "--alto-do-controle: 20px;" in trecho
    assert "height: var(--alto-do-controle);" in trecho
    assert "margin-left: calc(-1 * var(--gap-do-titulo));" in trecho


def test_o_PAR_de_fasoriais_tem_UMA_moldura_de_cada_lado():
    """Cada painel traz as suas molduras de nascença. Num par elas viravam
    quatro riscos curtos, cortados no vão entre os dois quadros — uma régua
    partida bem no meio, justamente onde ela existe para dizer que o cursor é o
    MESMO nos dois diagramas.

    Então o par devolve as molduras dos filhos e fica com duas, uma de cada
    lado, atravessando os dois. A de cima sai do FLUXO: nele ela só poderia
    nascer antes dos dois painéis — acima dos botões, porque o cabeçalho é de
    cada painel, um em cada coluna —, e ali ela não é moldura de nada. Fora do
    fluxo ela cai rente ao topo dos dois desenhos, por medida.

    Os dois quadros continuam sendo dois quadros: é o que dá a cada um a sua
    borda, o seu «escolhido» e o seu arrasto.
    """
    js = _onda_js()
    assert "comMolduraDoPar(linha, lista[i], lista[i + 1])" in js
    trecho = js[js.index("function comMolduraDoPar("):]
    trecho = trecho[:trecho.index("/** Os botões que criam um painel novo")]
    assert "b._molduras = [];" in trecho          # os filhos devolvem as suas
    assert "topo.flutua = true;" in trecho
    assert "esquerdo._molduras = [topo, rodape];" in trecho
    assert "cursorArrastavelNaMoldura(m)" in trecho

    # A medida é pelo CANVAS: a faixa reservada é um `padding` da caixa que o
    # contém, e medir a caixa punha a moldura em cima dos botões.
    pintar = js[js.index("function pintarMolduras(bloco)"):]
    pintar = pintar[:pintar.index("function cursorArrastavelNaMoldura(")]
    assert 'pai.querySelectorAll(".grafico canvas")' in pintar
    assert "desenho - base - alto - FOLGA_DA_MOLDURA" in pintar
    # E o sulco encosta no desenho dos dois lados, com a etiqueta por fora.
    assert 'const y0 = m.onde === "acima" ? alto - SULCO : 0;' in pintar
    assert 'const topoDaEtiqueta = m.onde === "acima" ? 0 : SULCO;' in pintar

    # E o par é UM painel (J1): quem tem borda e fundo é ele, os dois de dentro
    # perdem os seus, e o que separa é uma linha de 1 px do topo ao rodapé.
    css = _osclab_css()
    bloco = css[css.index(".par-com-moldura {"):css.index(".lado-fasorial {")]
    assert "border: 1px solid var(--linha);" in bloco
    assert "border: 0;" in bloco
    assert ".par-com-moldura::after" in bloco     # a divisória
    assert "position: absolute;" in bloco
    assert "padding-top: 26px;" in bloco          # o espaço da moldura de cima
    # O «escolhido» é a MESMA marca dos outros gráficos — a moldura azul em
    # volta do painel inteiro. Desenhada pelo PAR, e não pela coluna: a coluna
    # acaba onde o desenho acaba, e a marca tem de pegar a metade inteira,
    # inclusive as faixas das molduras do cursor, que são do par.
    assert "border: 1px solid var(--destaque);" in bloco
    assert ".grafico:first-child.painel-escolhido)::before" in bloco
    assert ".grafico:last-child.painel-escolhido)::before" in bloco
    # E a divisória começa na moldura de cima e termina na de baixo, em vez de
    # passar por cima delas.
    assert "top: var(--divisoria-topo, 0px);" in bloco
    assert "bottom: var(--divisoria-base, 0px);" in bloco
    # A divisória para nas molduras: quem para é a MOLDURA, que tem o fundo do
    # painel e passa por cima da linha.
    assert "background: var(--superficie);" in bloco
    # E num par o nome fica sozinho na primeira linha: a coluna tem metade da
    # largura, e numa delas o ▲▼× cabia ao lado dos botões e na outra não.
    assert ".par-com-moldura .grafico-titulo .nome-painel" in bloco
    assert "flex: 0 0 100%;" in bloco


def test_a_janelinha_SOBRE_diz_licenca_e_titularidade():
    """A versão no canto respondia «qual», e a pergunta de quem olha para ela é
    «que programa é este, e de quem».

    As três coisas que ninguém adivinha estão aqui: a licença (AGPL, e o que
    ela exige de quem SERVE o programa pela rede, que é o caso de uma
    ferramenta web na subestação), a titularidade e os formatos que esta
    instalação lê. O texto mora no HTML, com o resto das palavras da página —
    quem vier pôr a razão social procura por ela ali.
    """
    #: Sem a fixture `cliente`: o `tudo.py` PULA toda função que peça uma, e
    #: um teste que nunca roda é pior que nenhum — ele dá a impressão de
    #: cobertura que não existe.
    from osclab.web.server import create_app
    app = create_app()
    app.config.update(TESTING=True)
    #: Na TELA INICIAL, que é onde o «sobre» mora: a tela de arquivos é de um
    #: módulo, e a licença é do programa.
    pagina = app.test_client().get("/").get_data(as_text=True)
    assert 'id="janela-sobre"' in pagina
    assert 'class="versao" id="sobre"' in pagina
    assert "AGPL-3.0-or-later" in pagina
    assert "servi-lo pela rede" in pagina
    assert "direitos patrimoniais" in pagina

    from osclab import paths
    js = (paths.STATIC_DIR / "js" / "menu.js").read_text(encoding="utf-8")
    assert "sobre.showModal()" in js
    # Clique no escuro em volta fecha: o `<dialog>` entrega o clique do fundo
    # como se fosse dele, então quem decide é a POSIÇÃO.
    assert "janela.getBoundingClientRect()" in js


def test_a_setinha_da_escala_aponta_para_BAIXO():
    """Fechada ela aponta para onde as opções vão aparecer; aberta, para o
    botão que as recolhe. É a mesma setinha dos outros botões que abrem coisa
    nesta tela."""
    js = _onda_js()
    trecho = js[js.index("function botaoDaEscala(painel)"):]
    trecho = trecho[:trecho.index("const explicacaoDaEscala")]
    assert 'criar("span", "seta-do-menu", "▾")' in trecho
    # A MESMA seta virada, e não outro caractere: `▴` e `▾` são dois desenhos
    # de tamanhos diferentes na fonte monoespaçada, e a troca não se lia.
    assert 'seta.classList.toggle("virada", abrir);' in trecho
    assert ".seta-do-menu.virada { display: inline-block; transform: scaleY(-1); }" \
        in _osclab_css()


def test_os_HARMONICOS_tambem_tem_engrenagem():
    """O lugar dos ajustes é o mesmo em todo gráfico: procurar a engrenagem num
    painel e não achar é pior que achá-la com pouco dentro.

    Hoje ela tem pouco — a janela e a ordem máxima moram nas tarjas do rodapé,
    e tarja é informação, não controle. Então ela DIZ isso, em vez de abrir
    vazia: caixa vazia é a tela discutindo com quem clicou.
    """
    js = _onda_js()
    trecho = js[js.index("function blocoHarmonicos(painel)"):]
    trecho = trecho[:trecho.index("el._canvas = canvas;")]
    assert "engrenagemDoPainel(painel," in trecho
    assert '"nada-a-ajustar"' in trecho
    assert "tarjas do " in trecho
    assert ".menu-suspenso .nada-a-ajustar {" in _osclab_css()


def test_os_TRES_catalogos_de_sinal_tem_a_mesma_cara():
    """O canal analógico é o sinal inteiro; o fasor e o espectro são recortes
    dele — um tópico e dois subtópicos. As três janelas que escolhem sinal
    passaram a dizer isso: mesmos títulos de grupo, mesma regra de cor (branco
    para canal do relé, rosa para conta do OscLab), a unidade colada no nome e
    a faixa alternada no lugar do cartão.

    O «60 Hz» sobrescrito é a única coisa que só existe no fasorial: lá o que
    entra no diagrama é a componente de 60 Hz do canal. Nos harmônicos seria
    mentira — o assunto é o espectro inteiro.
    """
    js = _onda_js()
    css = _osclab_css()

    # Os mesmos títulos de bloco nos dois catálogos.
    assert '["senoidais", "Senoides", "seno"' in js
    assert '["calculados", "Calculados pelo OscLab", "calculado"' in js

    # A marca só no fasorial, e dentro do invólucro do nome (é ele que tem o
    # `flex: 1`; fora dele a unidade era empurrada para a borda da janela).
    fasorial = js[js.index("function abrirCatalogoFasorial(painel)"):]
    fasorial = fasorial[:fasorial.index("function abrirCatalogoDeSinais(")]
    assert "marca60: true," in fasorial
    assert 'if (opcoes.marca60 && x.canal >= 0)' in js
    assert 'const marca = criar("sub", "marca-do-nome", "60Hz");' in js
    # DENTRO do `.nome`: `.nome-da-linha` é flex com `gap`, e pendurada ao
    # lado a marca virava um item separado, com respiro, em vez de colada no
    # nome como na legenda do gráfico.
    assert '(nome.querySelector(".nome") || nome).append(marca);' in js
    assert 'nome.append(criar("span", "unidade-da-linha",' in js
    assert ".busca .marca-de-60 {" not in css
    assert ".marca-do-nome.marca-hz { color: var(--energia-60); }" in css

    # Faixa alternada nos dois, contada por BLOCO.
    assert "const emFaixa = (el, i) => {" in js
    assert "emFaixa(desenhar(x, false), i)" in js
    assert "emFaixa(cartao, i);" in js
    assert ".cartao-do-sinal.faixa { background: var(--faixa-da-lista); }" in css
    assert ".busca .achado.faixa" in css
    assert "--faixa-da-lista:" in css

    # O pé «já no gráfico» é o mesmo nos três: as mesmas palavras e a mesma
    # régua. Era «já na tela» e sem régua no fasorial — a mesma ideia escrita
    # de dois jeitos em duas janelas que fazem a mesma coisa.
    assert js.count('criar("div", "divisor-da-tela")') == 2
    assert js.count("já no gráfico (${naTela.length}) — desmarque ") == 2

    # A bolinha de procedência saiu: a família é a COR DO NOME, nos dois.
    assert "bolinha-de-procedencia" not in js
    assert "bolinha-de-procedencia" not in css
    assert ".nome-do-cartao.calculado .nome { color: var(--calculado-2); }" in css


def test_a_TELA_INICIAL_e_a_raiz_e_o_acervo_mudou_de_lugar():
    """A oscilografia é o PRIMEIRO módulo, e não a ferramenta toda. Sem uma
    tela inicial, os outros três nasceriam escondidos dentro da tela de
    arquivos de um deles.

    Os futuros aparecem apagados e CLICÁVEIS: o clique diz o que o módulo vai
    fazer. Botão apagado que não responde a nada é a tela discutindo com quem
    clicou — foi o argumento dele, e vale aqui.
    """
    from osclab.web.server import create_app
    app = create_app()
    app.config.update(TESTING=True)
    cli = app.test_client()

    menu = cli.get("/").get_data(as_text=True)
    assert "mosaico" in menu
    assert "Oscilografia" in menu and "Ondas viajantes" in menu
    assert 'class="modulo pronto" href="/arquivos"' in menu
    assert menu.count("modulo futuro") == 3

    acervo = cli.get("/arquivos")
    assert acervo.status_code == 200
    assert "Arquivos do projeto" in acervo.get_data(as_text=True)

    from osclab import paths
    js = (paths.STATIC_DIR / "js" / "menu.js").read_text(encoding="utf-8")
    assert "nota.showModal();" in js
    # O texto da nota sai do próprio cartão: duas cópias da mesma frase seriam
    # duas para corrigir no dia em que ela mudar.
    assert 'cartao.querySelector(".dizer-do-modulo").textContent' in js


def test_as_DICAS_sairam_do_RODAPE_e_viraram_a_janela_de_ajuda():
    """Elas ocupavam tela em toda rolagem e ninguém as lia depois da primeira
    semana. Em abas, cada assunto cabe inteiro numa tela e quem procura uma
    tecla acha pelo título."""
    from osclab.web import server
    from osclab import paths
    onda = (paths.TEMPLATES_DIR / "onda.html").read_text(encoding="utf-8")
    assert '<ul class="gestos">' not in onda
    assert 'id="janela-de-ajuda"' in onda
    assert 'class="chave com-icone" id="ajuda"' in onda
    # Oito assuntos, cada um com a sua folha.
    assert onda.count('class="aba"') + onda.count('class="aba escolhida"') == 8
    assert onda.count('class="folha-da-ajuda"') == 8

    js = _onda_js()
    assert 'document.getElementById("janela-de-ajuda")' in js
    assert "f.hidden = f.dataset.folha !== qual;" in js


def test_os_ICONES_do_mosaico_sao_os_do_estudo_I1():
    """Ele escolheu os quatro ícones do estudo I1 e a tela tinha outros —
    parecidos, mas não os mesmos. Aqui ficam as marcas de cada um daqueles
    desenhos, que é o que distingue um do outro.

    E a cor vem do CARTÃO (`currentColor`), não escrita no desenho: escrita,
    ela ficaria presa a um tema e o módulo pronto não acenderia o ícone dele.
    """
    from osclab import paths
    menu = (paths.TEMPLATES_DIR / "menu.html").read_text(encoding="utf-8")

    # Os quatro no mesmo quadro de 48 e na mesma espessura: é o que faz os
    # quatro cartões parecerem do mesmo conjunto.
    assert menu.count('viewBox="0 0 48 48" width="40" height="40"') == 4
    assert menu.count('stroke-width="2.2"') == 4

    # Os quatro são, exatamente, 1.1, 2.1, 3.3 e 4.1 do estudo de estética.
    assert menu.count("escolheu no estudo de estetica") == 1
    assert "2.1 «Dois vaos e o condutor»" in menu
    # 1 — a onda longa com o risco do disparo.
    assert 'stroke-dasharray="4 3"' in menu
    # 2 — duas torres e o condutor, SEM a falta marcada: a escolha dele foi o
    # 2.1, e o 2.2 (com o círculo vermelho) entrou aqui por engano uma vez.
    assert '<path d="M11 18 Q24 28 37 18"/>' in menu
    assert 'stroke="var(--ruim)"' not in menu
    # 3 — o trafo de dois enrolamentos, a barra e três alimentadores.
    assert '<circle cx="24" cy="13" r="6.5"/>' in menu
    assert menu.count('<rect x="9" y="38" width="6" height="4" rx="1"/>') == 1
    # 4 — o zigue-zague de Bewley entre os dois terminais.
    assert '<line x1="10" y1="9" x2="38" y2="19" stroke="currentColor"/>' in menu

    # Nenhuma cor presa no desenho.
    assert "#98a8aa" not in menu and "#58c6d6" not in menu and "#d45560" not in menu


def test_o_botao_do_TEMA_e_uma_chave_nas_TRES_telas():
    """Na tela inicial e na de arquivos ele era um `<button class="tema">`
    solto: herdava só o `min-width` do `#tema` e saía um retângulo sem moldura
    nem ícone, mais alto que o vizinho. Chave igual às outras nas três."""
    from osclab import paths
    for nome in ("menu.html", "index.html", "onda.html"):
        tela = (paths.TEMPLATES_DIR / nome).read_text(encoding="utf-8")
        assert 'class="chave tema com-icone" id="tema"' in tela, nome
        assert "--ic: var(--ic-tema)" in tela, nome
        assert '<button type="button" class="tema"' not in tela, nome


def test_a_chave_do_MENU_tem_a_seta_para_a_esquerda_nas_duas_telas():
    """«Voltar à tela anterior» é o gesto, e a seta é o que o diz. A pasta
    ficou com o «arquivos» — duas chaves com a mesma seta não diriam qual
    delas sobe mais."""
    from osclab import paths
    css = _osclab_css()
    assert "--ic-arquivos: url(" in css

    arquivos = (paths.TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
    assert ('<a class="chave voltar com-icone" style="--ic: var(--ic-voltar)"'
            in arquivos)
    assert 'href="/" title="Voltar à tela inicial">menu</a>' in arquivos

    onda = (paths.TEMPLATES_DIR / "onda.html").read_text(encoding="utf-8")
    # Na tela da onda são DUAS navegações, na barra do aplicativo, e desde
    # 22/10/2026 a seta é do «arquivos» (voltar à tela anterior) e a casa é
    # do «menu» (o começo de tudo).
    barra = onda[onda.index('<nav class="barra-do-app"'):onda.index("</nav>")]
    assert ('<a class="chave com-icone" style="--ic: var(--ic-voltar)"\n'
            '       href="/arquivos" target="_top"') in barra
    assert 'style="--ic: var(--ic-casa)"' in barra
    assert 'href="/" target="_top" title="Voltar à tela inicial">menu</a>' in barra
    assert "--ic-casa: url(" in css


def test_a_chave_AJUDA_e_a_ULTIMA_e_nao_herda_a_margem_do_paragrafo():
    """Ela tinha `class="chave ajuda"`, e a folha já tinha uma regra `.ajuda`
    para o PARÁGRAFO de explicação da tela de arquivos — com `margin: 0 0 16px`.
    O botão herdava os 16 px e ficava fora da fileira. A regra passou a valer
    só para o parágrafo, e a chave ficou em penúltimo, antes do «menu»."""
    from osclab import paths
    onda = (paths.TEMPLATES_DIR / "onda.html").read_text(encoding="utf-8")
    css = _osclab_css()

    assert "p.ajuda { margin: 0 0 16px;" in css
    assert "\n.ajuda { margin:" not in css
    assert 'class="chave ajuda' not in onda

    # A ORDEM da fileira, ditada por ele em 22/10/2026: depois do par
    # secundário/primário vêm lógica, (eventos), dicionário, ajuda e, por
    # último, o tema. Exportar, arquivos e menu subiram para a barra do
    # aplicativo, ACIMA do cabeçalho.
    acoes = onda[onda.index('<div class="acoes">'):onda.index("</header>")]
    assert acoes.index('data-lado="primario"') < acoes.index('id="logica"')
    assert acoes.index('id="logica"') < acoes.index('id="dicionario"')
    assert acoes.index('id="dicionario"') < acoes.index('id="ajuda"')
    for fora in ('id="exportar"', ">arquivos</a>", ">menu</a>"):
        assert fora not in acoes
        assert onda.index('<nav class="barra-do-app"') < onda.index(fora) \
            < onda.index("</nav>")
    # O tema voltou para o fim da fileira em 19/10/2026; quem foi para a linha
    # do título foi a BASE DE DADOS, que vale para o programa inteiro.
    assert acoes.rindex('id="ajuda"') < acoes.rindex('id="tema"')


def test_o_RODAPE_da_tela_da_onda_virou_aviso_e_so_aparece_quando_tem_o_que_dizer():
    """A tela acaba no «+ adicionar gráfico» (escolha dele). O placar de
    amostras na janela saiu — ele já está nas tarjas de cada painel —, mas o
    que era AVISO não pode sumir com ele: o servidor noutra versão, uma
    gravação que falhou, um sinal que ficou no lado errado por falta de relação
    de TC/TP no arquivo."""
    from osclab import paths
    onda = (paths.TEMPLATES_DIR / "onda.html").read_text(encoding="utf-8")
    js = _onda_js()
    css = _osclab_css()

    assert "<footer>" not in onda
    assert "voltar ao acervo" not in onda
    assert '<p id="rodape" class="aviso-do-pe" hidden></p>' in onda
    assert ".aviso-do-pe {" in css

    # Vazio ESCONDE: faixa vazia é tela ocupada dizendo nada.
    assert "function avisarNoPe(texto) {" in js
    assert "rodape.hidden = !texto;" in js
    # E ninguém mais escreve no rodapé por fora do aviso.
    assert "rodape.textContent" not in js.split("function avisarNoPe")[1].split("\n  }")[1]
    # O placar saiu; o aviso da relação de TC/TP ficou.
    assert "amostras · ${duracao(" not in js
    assert 'avisarNoPe(semRelacao().replace(/^ · /, ""))' in js


def test_o_catalogo_divide_por_PROCEDENCIA_na_ordem_que_ele_pediu():
    """«Canais do relé» virou «Senoides»: o bloco seguinte — «Outros sinais» —
    também é feito de canais do relé, e os dois títulos juntos diziam que um
    era do relé e o outro não. O que separa os dois é a FORMA da onda.

    E a ordem é a da procedência: o que o relé gravou (alternado e não
    alternado), depois o que o OscLab deduziu, por último o que o usuário
    escreveu."""
    js = _onda_js()
    assert 'titulo: "Senoides"' in js
    assert 'titulo: "Canais do relé"' not in js

    # Em «lista», «Outros sinais» entra no MEIO — e uma vez só.
    lista = js[js.index("function blocosDoCatalogo("):]
    lista = lista[:lista.index("function blocoDosOutros(")] if "function blocoDosOutros(" in lista[1:] else lista
    corpo = js[js.index("function blocosDoCatalogo("):]
    corpo = corpo[:corpo.index("\n  //: Os blocos que o usuário recolheu")]
    assert corpo.index('titulo: "Senoides"') < corpo.index("blocoDosOutros(outros)")
    assert (corpo.index("blocoDosOutros(outros)")
            < corpo.index('titulo: "Calculados pelo OscLab"'))
    assert (corpo.index('titulo: "Calculados pelo OscLab"')
            < corpo.index('titulo: "Suas contas"'))
    # A marca é o que impede de entrar duas vezes — e não esvaziar a lista, que
    # é a MESMA que o bloco guarda.
    assert "outrosJaEntrou = true;" in corpo
    assert "if (outros.length && !outrosJaEntrou)" in corpo
    assert "outros.length = 0" not in corpo


def test_o_MOTIVO_de_um_canal_nao_virar_fasor_sai_da_faixa():
    """Em «Outros sinais» ele aparecia em toda linha, empurrava a barra de
    energia para dentro e deixava aquele bloco com outra cara que os de cima.
    Continua existindo — no `title` do nome e por extenso no cartão aberto."""
    js = _onda_js()
    css = _osclab_css()
    assert 'criar("span", "motivo-da-linha"' not in js
    assert ".busca .motivo-da-linha {" not in css
    assert "nome.title = nome.title ? `${nome.title} — ${l.motivo}` : l.motivo;" in js
    # O motivo por extenso continua dentro do cartão aberto.
    assert 'diz("por quê", l.motivo || l.aviso)' in js


def test_o_cartao_ABERTO_mantem_a_cor_da_faixa_dele():
    """Escurecer era o padrão antigo, do tempo em que cada linha era um quadro:
    num fundo próprio, a linha aberta saía da lista em vez de continuar nela. E
    pintar toda linha aberta com a cor da faixa escura tinha o mesmo defeito do
    outro lado — uma linha da faixa CLARA escurecia ao abrir. Abrir não repinta
    nada: nenhum `background` nesta regra."""
    css = _osclab_css()
    bloco = css[css.index(".cartao-do-sinal.aberto {"):]
    bloco = bloco[:bloco.index("}")]
    assert "background" not in bloco
    assert "border-color: var(--cartao-borda);" in bloco


def test_os_dois_fasores_do_PAR_ficam_centrados_na_metade_deles():
    """Com os 22 px de respiro todos do lado da divisória, o centro da coluna
    não era o centro do desenho: os dois diagramas ficavam 11 px à esquerda do
    meio da metade deles. 11 px de cada lado mantêm o mesmo vão de 22 px entre
    os dois e deixam cada metade simétrica."""
    css = _osclab_css()
    assert ".par-com-moldura > .par-fasorial > .grafico { padding: 0 11px; }" in css
    assert (".par-com-moldura > .par-fasorial > .grafico:first-child { padding-right: 22px; }"
            not in css)
    centro = css[css.index(".par-com-moldura > .par-fasorial > .grafico > .corpo-fasorial {"):]
    assert "justify-content: center;" in centro[:centro.index("}")]


def test_o_cabecalho_do_GRUPO_nao_mente_a_unidade():
    """Ela era a do PRIMEIRO canal. Numa trinca de potências — W, VA e var — o
    cabeçalho dizia «grupo · W» e as outras duas ficavam desmentidas pela
    unidade que cada linha mostra ao lado do nome. Ou é de todos, ou aparecem
    todas, na ordem dos canais (a mesma dos vínculos)."""
    js = _onda_js()
    corpo = js[js.index("function tipoDoGrupo(linhas) {"):]
    corpo = corpo[:corpo.index("\n  }")]
    assert "if (u && !unidades.includes(u)) unidades.push(u);" in corpo
    assert 'const unidade = unidades.join(" · ");' in corpo
    assert "canal.unidade_mostrada || canal.unidade" not in corpo
    # As calculadas CONTAM: num vínculo de potência todas as linhas são
    # calculadas (P, Q, S, FP), e pular as calculadas deixava o cabeçalho sem
    # unidade nenhuma.
    assert "if (l.canal < 0) continue;" not in corpo


def test_o_cabecalho_do_VINCULO_de_potencia_diz_potencias():
    """O par `G1↔G3` não tem grandeza de canal — ele não é canal, é o que SAI
    de dois grupos. Sem este caso o título caía em «grupo», que não diz nada:
    a caixinha ao lado já mostra quais dois vãos são, e o título tem de dizer
    o QUE são. A seta é a marca do par (`SETA_DO_VINCULO`, no Python)."""
    from osclab.plot import catalogo
    assert catalogo.SETA_DO_VINCULO == "↔"

    js = _onda_js()
    corpo = js[js.index("function tipoDoGrupo(linhas) {"):]
    corpo = corpo[:corpo.index("\n  }")]
    assert 'doVinculo.includes("↔") ? "potências" : ""' in corpo


def test_o_mosaico_fica_CENTRADO_na_tela_inicial():
    """O miolo tinha 980 px de largura e o mosaico 760: os cartões ficavam
    encostados à esquerda e sobravam 180 px à direita. A largura do miolo passa
    a ser a do mosaico mais os dois respiros — assim o conjunto centra e a
    chamada continua alinhada com a primeira coluna."""
    css = _osclab_css()
    assert "main.menu { max-width: 800px; margin: 0 auto;" in css
    assert "main.menu { max-width: 980px" not in css


def test_a_CONTINUA_e_a_barra_de_ordem_ZERO_do_espectro():
    """Ele reviu a decisão de setembro: a DC passou a ser a primeira barra, à
    esquerda da fundamental — é o que a SEL faz. Ela entra sem empurrar o
    desenho: a última ordem sai para ela caber, e a contagem de barras não
    muda. Com 33,3 amostras por ciclo a última é a 16ª, que é justamente a que
    tem só uma amostra por período — trocar a mais frágil pela contínua é
    trocar uma barra que quase não mede por uma que mede."""
    js = _onda_js()
    from osclab import paths
    leitura = (paths.PACKAGE_DIR / "plot" / "leitura.py").read_text(encoding="utf-8")

    # O servidor manda a contínua separada das raias: são duas contas da mesma
    # janela, e juntá-las no Python esconderia qual é qual.
    assert '"continua": _num(abs(continua) * fator),' in leitura
    assert "continua = float(np.dot(pesos, janela) / float(pesos.sum()))" in leitura

    # Na tela, as raias passam a ser indexadas pela ORDEM: 0 é a contínua.
    assert "const raias = [v.continua === null || v.continua === undefined" in js
    assert "for (const x of v.harmonicos) raias.push(x === null ? 0 : x);" in js
    # O rótulo da barra é a ordem, e o 0 sai na cor da contínua.
    assert 'ctx.fillStyle = token(h === 0 ? "--energia-dc" : "--suave");' in js
    # No espectro em linha (22/10/2026) o 0 é «0» e o resto é «2ª», «3ª»;
    # nas barras, a primeira se chama «DC».
    assert 'ctx.fillText(h === 0 ? "0" : `${h}ª`, X(h), y0 + 14);' in js
    assert 'ctx.fillText(h === 0 ? "DC" : String(h),' in js
    # O eixo não se estica por causa dela: a contínua de um inrush passa dos
    # 100 % com facilidade e achataria todo o resto.
    assert "for (let h = 2; h < x.raias.length && h < ordens; h += 1) {" in js
    # O rodapé diz até onde se mede com precisão; a ressalva da barra DC
    # (média de um ciclo, que decai) está no hover dela, não numa tarja.
    assert 'ficha("barra 0"' not in js
    assert "decai com a constante X/R" in js
    assert "o Nyquist da janela, e é esse o limite da medida com precisão" in js


def test_a_tabela_dos_HARMONICOS_tem_a_bolinha_como_as_outras():
    """A cor estava na LETRA, e letra colorida no meio de nomes brancos se lê
    como «este está selecionado». As três janelas que escolhem sinal já são
    irmãs; a tabela, que é o que se compara, faltava."""
    js = _onda_js()
    corpo = js[js.index("function tabelaHarmonicos(painel) {"):]
    corpo = corpo[:corpo.index("/** As duas células")]
    assert "rotulo.append(bolinhaDoSinal(painel, sinal));" in corpo
    assert "nome.style.color = corDoSinal(sinal, painel);" not in corpo


def test_o_VINCULO_do_triangulo_sai_da_engrenagem():
    """Ele decide DE ONDE o triângulo inteiro sai, e sem ele o painel não
    desenha nada. Um botão que o painel não dispensa não é ajuste — é o
    painel. Pedido dele."""
    js = _onda_js()
    corpo = js[js.index("function blocoTriangulo(painel) {"):]
    corpo = corpo[:corpo.index("\n  /** Qual seta foi clicada")]
    assert "botaoCursor, botaoDoVinculoDoTriangulo(painel)," in corpo
    assert 'engrenagemDoPainel(painel, () => [botaoDoVinculoDoTriangulo' not in corpo
    assert 'criar("p", "nada-a-ajustar"' in corpo


def test_o_triangulo_mostra_3V0_e_nao_os_DOIS():
    """Eram duas linhas — `V0` e `3V0`, a mesma grandeza a um fator de três —,
    e «qual destes dois eu uso?» é o que uma tela de proteção não deve criar.
    A 3V0 é a útil: é o que o delta aberto entrega e é nela que o ajuste do
    59N está escrito. A V0 continua à vista como a seta verde do desenho."""
    js = _onda_js()
    assert 'derivada("3V0", token("--bom"), "de-neutro")' in js
    assert 'derivada("V0", token("--bom"), "de-neutro")' not in js
    assert "seta verde do desenho é V0 = 3V0 / 3" in js


def test_o_TRIANGULO_e_o_FASORIAL_formam_par():
    """Os dois têm o mesmo corpo, o mesmo quadro quadrado e a mesma tabela ao
    lado — são as duas leituras angulares do mesmo instante. «O triângulo da
    falta ao lado dos fasores da falta» só existe se os dois couberem na mesma
    linha."""
    js = _onda_js()
    assert 'const DIAGRAMAS_QUE_PAREIAM = new Set(["fasorial", "triangulo"]);' in js
    assert "!DIAGRAMAS_QUE_PAREIAM.has(a.tipo)" in js
    assert 'a.tipo !== "fasorial" || b.tipo !== "fasorial"' not in js
    # E os dois lados do par aceitam os dois tipos.
    assert js.count("DIAGRAMAS_QUE_PAREIAM.has(paineis[i") == 2


def test_o_filtro_de_OUTROS_SINAIS_fica_apagado_e_preso():
    """Eles estão naquele bloco porque a onda não passou no teste de alternado.
    Filtrar 60 Hz de um sinal que não é alternado mede uma componente que não
    existe — e entregava um traço quase reto com cara de medida. Antes o
    interruptor ficava aceso e preso, junto com o resto da tela. Pedido dele."""
    js = _onda_js()
    inicial = js[js.index("const filtroInicial = (l) => {"):]
    inicial = inicial[:inicial.index("\n    };")]
    assert 'if (l.bloco === "outros") return false;' in inicial

    livre = js[js.index("const filtroLivre = (l) => {"):]
    livre = livre[:livre.index("\n    };")]
    assert 'if (l.bloco === "outros") return false;' in livre
    # E preso ANTES da regra do modo tradicional: lá ele ficaria aceso.
    assert (livre.index('l.bloco === "outros"') < livre.index("soFiltrado()"))

    assert "não passou no teste de alternado: filtrar 60 Hz " in js


def test_um_dialogo_FECHADO_fica_escondido():
    """Regra nossa com `display` no próprio `<dialog>` ganha do `display: none`
    que o navegador põe no fechado — e o diálogo nunca fecha. Era o que
    acontecia com a janela de ajuda: ficava colada no fim da página, embaixo do
    «+ adicionar gráfico», e o × não fazia nada visível. Todo `display` que
    valha para o elemento `<dialog>` tem de estar preso ao `[open]`."""
    import re
    css = _osclab_css()
    for m in re.finditer(r'([^{}\n]+)\{([^}]*)\}', css):
        sel = m.group(1).strip().split("\n")[-1].strip()
        corpo = m.group(2)
        if "display" not in corpo:
            continue
        # seletores que terminam no PRÓPRIO elemento do diálogo
        if re.fullmatch(r'\.(janela-[\w-]+|busca(\.[\w-]+)?)', sel):
            raise AssertionError(
                f"{sel} declara `display` sem [open]: o diálogo fechado "
                "continuaria visível")
    assert ".janela-de-ajuda[open] {" in css
    assert ".busca.fasorial[open] {" in css
    assert ".busca.calculadora[open] {" in css


def test_o_TRIANGULO_vazio_nao_mostra_tabela_nenhuma():
    """Sem vínculo escolhido o diagrama está vazio, e cinco linhas de travessão
    — VAB, VBC, VCA e a residual — não são tabela: são a promessa de uma medida
    que não existe. Vazio, o painel diz uma coisa só: escolha o vínculo."""
    js = _onda_js()
    assert ('if (painel.tipo === "triangulo" && (painel.sinais || []).length) {'
            in js)
    # E sem nenhuma linha some a tabela inteira, cabeçalho incluído — vale
    # também para o fasorial recém-criado.
    assert "tabela.hidden = !tbody.children.length;" in js


def test_as_BARRAS_de_energia_saem_todas_na_mesma_grossura():
    """Medido em 15/10 com o navegador a 110 %: a barra de 4 px vira 4,4
    pixels de tela e o passo de 32 px vira 35,2 — cada linha começa numa
    fração diferente de pixel e a MESMA barra sai com cinco fileiras pintadas
    numa linha e quatro na seguinte. Em zoom redondo (100, 125, 150 %) nada
    disso aparece, e foi por isso que a primeira correção pareceu bastar.

    Duas peças: as medidas da grade arredondadas para pixel de tela, e cada
    barra encostada na grade com um `translateY` de menos de um pixel — porque
    o navegador guarda cada medida de layout num múltiplo de 1/64 px, e os
    restos se acumulam linha a linha."""
    js = _onda_js()
    assert "function ajustarGradeDaLista() {" in js
    assert 'raiz.setProperty("--alto-da-barra"' in js
    assert 'window.addEventListener("resize", ajustarGradeDaLista);' in js

    assert "function alinharBarras(raiz) {" in js
    assert "const topo = b.getBoundingClientRect().top * dpr;" in js
    assert "return (Math.round(topo) - topo) / dpr;" in js
    # Num quadro à parte: dentro do mesmo, o layout ainda não assentou.
    assert "requestAnimationFrame(() => alinharBarras(lista));" in js
    # E a rolagem muda a fração de todas elas ao mesmo tempo.
    assert "function seguirRolagemDasBarras(raiz) {" in js
    assert 'raiz.addEventListener("scroll", refazer, true);' in js


def test_as_duas_colunas_de_um_PAR_ficam_sempre_alinhadas():
    """Elas se desencontravam por dois motivos, e os dois aparecem em registro
    de verdade: o cabeçalho de um lado quebra numa linha a mais (nome de
    referência comprido, o ▲▼× desce) e o corpo de um lado ganha as notas de
    rodapé que o outro não tem. Qualquer um dos dois empurra desenho, tabela e
    rodapé daquele lado para baixo."""
    js = _onda_js()
    css = _osclab_css()
    assert "function alinharPares() {" in js
    # Mede e iguala — nada de altura fixa escrita à mão.
    assert 'for (const classe of ["grafico-titulo", "corpo-fasorial"]) {' in js
    assert "el.style.minHeight = `${alto}px`;" in js
    # O ▲▼× desce nos DOIS, ou em nenhum.
    assert 't.classList.add("arranjo-embaixo")' in js
    assert ".par-com-moldura .grafico-titulo.arranjo-embaixo .arranjo {" in css
    # E antes das molduras, que são posicionadas por medida sobre essa altura.
    corpo = js[js.index("function repintarAgora() {"):]
    corpo = corpo[:corpo.index("atualizarBarra();")]
    assert corpo.index("alinharPares();") < corpo.index("pintarMolduras(b)")


def test_so_as_CORRENTES_do_triangulo_tem_comprimento_minimo():
    """Numa falta monofásica a corrente da fase sã é 3 A ao lado de 101 A da
    fase em curto: proporcional, ela vira um ponto no centro e o ÂNGULO dela
    some junto — e é do ângulo das três que sai a classificação da falta.

    Nas TENSÕES não: ali o comprimento É a leitura (vértice caído é falta à
    terra, lado achatado é bifásica), e um mínimo mentiria sobre a forma do
    triângulo. Mesma regra do fasorial, e o trecho inventado sai apagado."""
    js = _onda_js()
    corpo = js[js.index('if (acesas.has("corrente")) {'):]
    corpo = corpo[:corpo.index('if (acesas.has("fase")) {')]
    assert "const util = raio * 0.88;" in corpo
    assert "const minimo = util * MINIMO_DA_SETA;" in corpo
    assert "curta ? real : 0" in corpo

    # O piso de ruído vem ANTES do mínimo: uma corrente de 0,001 % da régua
    # não tem ângulo, tem ruído de quantização — e o mínimo existe justamente
    # para tornar o ângulo legível.
    assert "if (f.sinal.sem_sinal || emPu < RUIDO_DA_SETA) continue;" in corpo
    assert corpo.index("RUIDO_DA_SETA") < corpo.index("const curta")

    # A camada das tensões de FASE continua proporcional: nada de mínimo lá.
    fase = js[js.index('if (acesas.has("fase")) {'):]
    fase = fase[:fase.index("\n    }")]
    assert "MINIMO_DA_SETA" not in fase

    # E a seta sabe desenhar o trecho inventado apagado.
    assert ("function setaDoTriangulo(ctx, x0, y0, x1, y1, cor, grossura, tracejada,"
            in js)
    assert "solidoAte = 0) {" in js
    assert "ctx.globalAlpha = 0.3;" in js


def test_o_desenho_que_ficou_ESTREITO_se_conserta_sozinho():
    """Os painéis escrevem a largura do canvas em pixels, medida do pai na hora
    de pintar. Se a medida saiu antes de o navegador acomodar o que aquela
    mesma passagem mudou — um cabeçalho que ganhou uma linha por causa de um
    nome comprido, uma tabela que apareceu —, o canvas fica mais estreito que o
    painel e assim permanece: pixel escrito não acompanha o pai. A moldura do
    cursor copia essa largura e acompanha o erro, e foi isso que ele viu como
    «a barra da moldura deslocada para a esquerda». Mexer no cursor consertava
    por acidente, porque repintava.

    Medido nas fotos dele: o desenho ocupava 919 px de um painel de ~1700, e a
    moldura saía com os mesmos 944 px — fiel ao desenho, e os dois estreitos.
    """
    js = _onda_js()
    assert "function confereLarguras() {" in js
    assert "if (confereLarguras()) return;   // repintou: as molduras vão junto" in js
    # O fasorial e o triângulo têm lado fixo: não entram na conferência.
    corpo = js[js.index("function confereLarguras() {"):]
    corpo = corpo[:corpo.index("\n  }")]
    # O plano complexo e o alfa também: o quadro deles tem lado fixo.
    assert ('if (b._painel.tipo === "fasorial" || b._painel.tipo === "triangulo"\n'
            '          || b._painel.tipo === "complexo" || b._painel.tipo === "alfa")'
            ' continue;') in corpo
    assert "Math.abs(pai - tem) > 1" in corpo
    # UMA correção, nunca um laço de repinturas.
    assert "if (tentouLargura >= 1) { tentouLargura = 0; return false; }" in corpo

    # E a largura da área também muda sem `resize` de janela: barra de rolagem,
    # tabela que aparece. Aí se repinta e se repede, pelo mesmo atraso.
    assert "new ResizeObserver(() => {" in js
    assert "if (larga === larguraDaArea) return;" in js
    assert "pendente = setTimeout(carregar, 200);" in js



def test_a_regua_das_correntes_do_triangulo_sai_do_REGISTRO():
    """Era a do instante: a maior corrente daquele instante recebia 88 % do
    raio, fosse ela qual fosse. Na pré-falta, com as três entradas lendo o
    ruído do conversor (0,0011 A, 0,0009 A e 0,0058 A no registro dele), a
    maior delas virava uma seta gigante atravessando o círculo, com um ângulo
    que é ruído puro.

    É a mesma régua do diagrama fasorial, e pela mesma razão já decidida lá: a
    mesma corrente não pode mudar de tamanho sem nada ter acontecido com ela.
    Nas TENSÕES a régua continua a do instante — ali o que se lê é a forma do
    triângulo, que é relativa entre as três por natureza."""
    js = _onda_js()
    corpo = js[js.index("function pintarTriangulo(canvas, painel) {"):]
    corpo = corpo[:corpo.index("function preencherTensoesDeLinha")]

    assert "const reguas = reguasDoPainel(fasores);" in corpo
    assert 'const limiteI = ((reguas.get("A") || {}).limite) || 1;' in corpo
    assert "const emPu = Math.abs(f.pu || 0) / limiteI;" in corpo
    # A régua do instante das correntes sumiu; a das tensões ficou.
    assert "const escalaI = " not in corpo
    assert "const escalaV = (raio * 0.72) / maiorDe(tensoes);" in corpo


def test_a_MOLDURA_nao_muda_de_largura_quando_o_cursor_aparece():
    """Sem cursor a tabelinha não existe e a onda ocupa 282 px a mais (268 da
    tabela e 14 do vão, medido). A moldura copia a largura da onda, então ela
    nascia larga — quase na borda do cartão — e encolhia de uma vez no instante
    do primeiro cursor. Era o «fica torta, deslocada para a direita, e ao pôr o
    cursor ela se corrige».

    A moldura passa a usar a largura que a onda terá COM a tabelinha, mesmo
    antes de haver cursor: sem cursor ela não tem nada para alinhar — é só um
    detalhe do cartão —, e quando passa a ter, já está no lugar.

    Medido depois: 85..1133 (1048 px) nos dois estados, sem cursor e com.
    """
    js = _onda_js()
    css = _osclab_css()

    assert "function reservaDaTabelinha() {" in js
    assert 'if (area.classList.contains("com-cursores")) return 0;' in js
    assert 'ler("--lado-da-tabelinha") + ler("--vao-da-tabelinha")' in js

    corpo = js[js.index("function refDoDesenho() {"):]
    corpo = corpo[:corpo.index("\n  function ")]
    assert "r.width - reservaDaTabelinha()" in corpo

    # Os dois números moram no CSS, que é quem desenha a grade — e o JS lê.
    assert "--lado-da-tabelinha: 268px;" in css
    assert "--vao-da-tabelinha: 14px;" in css
    assert ("grid-template-columns: minmax(0, 1fr) var(--lado-da-tabelinha);"
            in css)
    assert "grid-template-columns: minmax(0, 1fr) 268px;" not in css


# ---------------------------------------------------------------------------
# A base de dados na tela
# ---------------------------------------------------------------------------

def _base_js() -> str:
    return (paths.STATIC_DIR / "js" / "base.js").read_text(encoding="utf-8")


def _template(nome: str) -> str:
    return (paths.TEMPLATES_DIR / nome).read_text(encoding="utf-8")


def test_o_ICONE_da_base_e_a_pilha_de_discos_que_ele_escolheu():
    """Escolhido entre oito, na maquete. O desenho mora numa variável só, para
    a chave de 14 px, o aviso da tela inicial e a tela da base mudarem juntos
    no dia em que ele trocar de ideia."""
    css = _osclab_css()
    assert "--ic-base:" in css
    # A linha inteira: o próprio `data:` tem ponto-e-vírgula dentro
    # (`image/svg+xml;utf8`), então cortar no primeiro `;` cortaria o desenho.
    pilha = next(l for l in css.splitlines() if l.strip().startswith("--ic-base:"))
    assert "ellipse" in pilha                 # o disco de cima
    assert pilha.count("<path") == 2          # as duas paredes da pilha
    assert "viewBox='0 0 48 48'" in pilha     # o mesmo quadro dos ícones do mosaico


def test_cada_GAVETA_tem_o_desenho_de_quem_vai_usa_la():
    """Três pilhas de disco iguais não diriam qual é qual. A grade é o
    dicionário, as torres são o módulo de linhas, a pasta é o acervo."""
    css = _osclab_css()
    js = _base_js()
    for variavel in ("--ic-digitais", "--ic-linhas"):
        assert f"{variavel}:" in css, f"{variavel} usada e não declarada"
        assert f"var({variavel})" in js
    assert 'var(--ic-base)' in js


def test_a_tela_inicial_tem_os_DOIS_momentos_da_base_no_mesmo_lugar():
    """Enquanto não há base, a tarja âmbar chama; havendo, o mesmo lugar vira
    linha de estado. Um botão fixo no mosaico competiria com os quatro
    módulos, e a base não é um modo de análise."""
    menu = _template("menu.html")
    assert "{% if base.tem %}" in menu
    assert 'class="linha-da-base"' in menu
    assert 'class="aviso-da-base"' in menu
    # e o aviso diz, na mesma frase, que o programa funciona sem ela
    assert "funciona igual" in menu


def test_a_gaveta_DESLIGADA_fica_riscada_e_nao_some_da_linha():
    """Sumir faria o número do vizinho trocar de lugar, e a pessoa procuraria
    o que não saiu do lugar."""
    menu = _template("menu.html")
    assert "' if g.ligada else ' apagada'" in menu
    css = _osclab_css()
    assert ".linha-da-base .cont.apagada" in css
    assert "line-through" in css.split(".linha-da-base .cont.apagada")[1][:120]


def test_a_tela_da_base_leva_o_estado_DENTRO_do_html():
    """Sem isso a tela pisca vazia antes de saber se existe base — justamente
    a tela em que o «ainda não tem» é o assunto."""
    html = _template("base.html")
    assert 'id="estado-da-base"' in html
    assert 'type="application/json"' in html
    assert "{{ base|tojson }}" in html
    assert 'id="tela"' in html


def test_o_INTERRUPTOR_da_gaveta_diz_por_escrito_de_que_lado_esta_ligado():
    """Interruptor mudo deixa dúvida de qual lado é o ligado — e esta tela é
    a que decide se o programa vai ou não consultar a base."""
    js = _base_js()
    assert 'g.ligada ? "habilitada" : "desabilitada"' in js
    assert 'sw.setAttribute("aria-pressed", g.ligada ? "true" : "false")' in js


def test_a_tela_da_base_repete_que_NADA_ali_e_obrigatorio():
    """É o contrato do módulo inteiro: a base acelera, nunca destrava."""
    js = _base_js()
    assert "Nenhuma delas é necessária para o leitor funcionar." in js
    assert "Usar uma base é opcional" in js
    assert "abre e analisa oscilografia sem ela" in js


def test_o_sinal_SEM_descricao_aparece_dizendo_o_que_vai_acontecer():
    """A regra conservadora virada em tela: vazio não é defeito, e quem olha
    a tabela precisa saber o que o leitor fará com aquela linha."""
    js = _base_js()
    assert '"sem descrição — aparece com o nome cru"' in js
    assert '"deixe vazio se não tiver certeza"' in js
    assert "só classifique o que tiver certeza" in js


def test_a_estrutura_aparece_ANTES_de_criar_a_base():
    """Criar com o nome errado e ter que recomeçar é o que ela evita. E só
    aparece DEPOIS de haver caminho: antes dele não há o que desenhar."""
    js = _base_js()
    assert "estrutura-da-base" in js
    assert "if (!mae()) {" in js
    assert "Escolha a pasta para ver como a base vai ficar." in js
    css = _osclab_css()
    assert ".estrutura-da-base" in css
    assert ".espera-do-caminho" in css


def test_a_base_que_SUMIU_continua_na_lista_e_explica_o_motivo():
    """O pen-drive pode voltar amanhã: esquecer sozinho seria decidir pelo dono."""
    js = _base_js()
    assert '"pasta não encontrada"' in js
    assert "linha.disabled = true;" in js
    assert "O caminho não existe nesta máquina agora." in js
    css = _osclab_css()
    assert ".base-achada.sumiu" in css


def test_os_NOMES_das_gavetas_sao_os_que_ele_escolheu_na_maquete():
    from osclab.basedados import pasta as base_mod
    assert [g.nome for g in base_mod.GAVETAS] == ["Dicionário", "Linhas e estruturas"]
    # E o nome da PASTA é curto, minúsculo e sem acento: é esse que o programa
    # procura sozinho numa base que veio de outra pessoa.
    for g in base_mod.GAVETAS:
        assert g.id.isascii() and g.id.islower() and g.id.isalpha()


def test_a_ESTRUTURA_e_seca_e_a_pasta_da_base_acompanha_o_nome():
    """Comentário ao lado de cada linha foi o que a tornou ilegível — ele
    pediu só ícone e nome, 19/10/2026. E a pasta da base muda na mesma tecla
    em que ele digita o nome: é a linha que responde «o que é esse nome»."""
    js = _base_js()
    assert 'linha(1, "pasta", "viva", pasta() + sep());' in js
    assert 'linha(2, "arquivo", "arq", "base.json");' in js
    # seca: nenhuma nota ao lado das linhas
    assert '"nome fixo"' not in js
    assert "a pasta que você escolher" not in js
    css = _osclab_css()
    for classe in (".estrutura-da-base .viva", ".estrutura-da-base .fixo",
                   ".estrutura-da-base .arq"):
        assert classe in css
    # o recuo é padding, e não espaço no texto: espaço o navegador colapsa
    assert '(nivel * 22) + "px"' in js


def test_a_base_tem_o_DICIONARIO_e_as_linhas():
    """«Dicionário» é o nome oficial, escolhido por ele em 19/10/2026 — e é
    uma tela de consulta: procura-se um nome e lê-se o que ele quer dizer."""
    from osclab.basedados import pasta as base_mod
    assert [g.id for g in base_mod.GAVETAS] == ["dicionario", "linhas"]
    js = _base_js()
    assert "o histórico de registros" not in js
    assert '"SE Barro Duro"' not in js


def test_a_barra_MEDE_o_caminho_contra_o_teto_do_windows():
    """260 caracteres, e estourar não dá erro claro: o arquivo simplesmente
    «não existe». Medir antes é mais barato do que descobrir na análise. E
    avisa, nunca bloqueia — o botão «criar» continua valendo."""
    js = _base_js()
    assert "const TETO = 260;" in js
    assert "if (n >= TETO)" in js
    assert "else if (n > 200)" in js
    assert "ok.disabled = true" in js          # só enquanto o pedido roda
    css = _osclab_css()
    assert ".barra-da-qualidade i.atencao" in css
    assert ".barra-da-qualidade i.ruim" in css


def test_a_barra_diz_POR_QUE_o_caminho_e_ruim_e_so_quando_e():
    """Um aviso que está sempre na tela deixa de ser aviso. Caminho limpo
    mostra a barra verde e mais nada."""
    js = _base_js()
    assert "if (achados.length) {" in js
    for pedaco in ("pasta do programa", "fundo demais", "nuvem",
                   "pasta do sistema", "comprimento"):
        assert pedaco in js
    assert "escolha um caminho mais próximo da raiz" in js
    assert "pode perder a base numa atualização do OscLab" in js
    css = _osclab_css()
    assert ".porque.ruim" in css
    assert ".porque.atencao" in css



def test_o_NOME_vem_antes_do_caminho_e_e_o_nome_da_pasta():
    """Ele soltou o nome em 19/10/2026 — era travado em «database» — para
    caber mais de uma base na mesma pasta mãe. O nome vem PRIMEIRO porque é
    dele que sai o resto do desenho."""
    from osclab.basedados import pasta as base_mod
    assert base_mod.NOME_PADRAO == "database"
    js = _base_js()
    assert 'const NOME_PADRAO = (E.nome_padrao || "database");' in js
    assert js.index('"nome da base"') < js.index('"onde ela vai ficar"')
    assert "forma.append(c1, c2, palco);" in js
    assert "Em branco, fica «" in js
    # e o que é do programa continua travado
    assert "como chamar na lista (opcional" not in js


def test_o_BOTAO_DE_PROCURAR_abre_o_navegador_de_pastas_do_servidor():
    """O navegador não entrega caminho absoluto de pasta — proteção dele, e
    é certa. Como o OscLab roda na máquina do usuário, quem lista é o
    servidor: a tela mostra o que ele já veria no Explorer."""
    js = _base_js()
    assert "/api/base/pastas?onde=" in js
    assert "function botaoDeProcurar(" in js
    assert '"procurar a pasta no computador"' in js
    html = _template("base.html")
    assert 'id="janela-do-navegador"' in html
    assert 'id="usar-pasta"' in html
    assert 'id="lista-de-pastas"' in html


def test_SUBIR_UM_NIVEL_e_um_item_da_lista_e_nao_uma_seta_escondida():
    """A mão já está na lista, e subir é o movimento mais repetido de todos."""
    js = _base_js()
    assert '"..  subir um nível"' in js
    assert ".pasta-item.subir" in _osclab_css()


def test_VOLTAR_mora_no_cabecalho_ao_lado_de_MENU():
    """Escolha dele, 19/10/2026. As duas chaves fazem a mesma coisa — sair de
    onde se está — e ficam juntas; botão de sair que muda de lugar conforme a
    tela é botão que se procura."""
    html = _template("base.html")
    assert 'id="voltar-passo"' in html
    # nasce escondido: só há o que voltar quando há painel aberto
    assert "hidden" in html.split('id="voltar-passo"')[1].split(">")[0]
    assert html.index('id="voltar-passo"') < html.index('href="/" title="Voltar à tela inicial"')

    js = _base_js()
    assert 'document.getElementById("voltar-passo")' in js
    assert "chaveDeVoltar.hidden = !aba;" in js
    # e o pé do painel ficou limpo
    assert "voltaDoPainel" not in js
    assert ".volta-do-painel" not in _osclab_css()


def test_o_botao_de_procurar_tenta_primeiro_a_janela_DO_SISTEMA():
    """É a janela de «salvar em…» que a pessoa já sabe usar — com barra de
    endereço e «nova pasta». A lista desenhada na página fica como plano B,
    para a máquina em que aquela não abre."""
    js = _base_js()
    assert '"/api/base/pasta-nativa"' in js
    assert "if (dados.disponivel)" in js
    assert "await abrirNavegador(inicial, aoTerminar);" in js
    # e fechar a janela sem escolher NÃO abre a lista atrás dela
    assert "return;                      // fechou sem escolher" in js


def test_cada_CATEGORIA_tem_a_sua_cor_e_a_auxiliar_e_discreta():
    """Bloqueio em roxo, e não em laranja: laranja ficaria a um passo do âmbar
    da partida, e são justamente essas duas que não podem ser confundidas
    quando se pergunta por que um elemento não atuou. A auxiliar fica no tom
    apagado — é o que quase nunca se quer ver —, e o que a separa do «sem
    categoria» é a borda inteira: tracejado quer dizer buraco."""
    from osclab.basedados import digitais
    css = _osclab_css()
    for categoria in digitais.CATEGORIAS:
        if not categoria:
            continue
        assert f".tipinho.{categoria} {{" in css, f"categoria {categoria} sem cor"
    assert ".tipinho.sem-categoria" in css
    trecho = css.split(".tipinho.sem-categoria")[1][:120]
    assert "dashed" in trecho
    auxiliar = css.split(".tipinho.auxiliar {")[1][:120]
    assert "dashed" not in auxiliar


def _dicionario_js() -> str:
    return (paths.STATIC_DIR / "js" / "dicionario.js").read_text(encoding="utf-8")


def test_a_chave_do_DICIONARIO_fica_antes_da_ajuda():
    """Desde 21/10/2026 o dicionário fica logo antes da ajuda: as duas são
    consulta."""
    onda = _template("onda.html")
    assert 'id="dicionario"' in onda
    assert "--ic-dicionario" in onda
    assert "--ic-dicionario:" in _osclab_css()
    depois_do_par = onda.split('data-lado="primario"')[1]
    assert depois_do_par.index('id="logica"') < depois_do_par.index('id="dicionario"')
    assert depois_do_par.index('id="dicionario"') < depois_do_par.index('id="ajuda"')
    assert "js/dicionario.js" in onda


def test_sem_dicionario_a_chave_fica_CINZA_e_continua_clicavel():
    """Chave que some deixa quem a procurou achando que a tela mudou de forma;
    chave que não responde é a tela discutindo com quem clicou. Cinza e
    clicável: o clique explica o que falta."""
    js = _dicionario_js()
    assert 'chave.classList.add("sem-dicionario")' in js       # nasce cinza
    assert 'chave.classList.toggle("sem-dicionario", !tem)' in js
    assert "chave.disabled" not in js                          # nunca desabilitada
    assert "Nenhum dicionário para consultar" in js
    css = _osclab_css()
    assert ".chave.sem-dicionario" in css


def test_a_consulta_SO_procura_e_nao_escreve_em_lugar_nenhum():
    """Decisão dele, 19/10/2026: a descrição não vai para as tiras nem para as
    equações. Quem quer saber o que um sinal é, pergunta no dicionário."""
    js = _dicionario_js()
    assert "/api/dicionario/" in js
    assert "busca-do-dicionario" in js
    # nada de mexer no desenho: este arquivo não toca em canvas nem em tiras
    for proibido in ("canvas", ".tira", "getContext", "repintar"):
        assert proibido not in js, f"a consulta não devia tocar em {proibido}"


def test_a_consulta_diz_em_que_DEGRAU_o_verbete_venceu():
    """Regra invisível vira mágica: quem cadastrou um verbete genérico precisa
    ver que é ele que está respondendo."""
    js = _dicionario_js()
    assert 'criar("div", "origem"' in js
    assert ".achado-do-dicionario .origem" in _osclab_css()


# ---------------------------------------------------------------------------
# O painel de lógica e ajustes
# ---------------------------------------------------------------------------

def _logica_js() -> str:
    return (paths.STATIC_DIR / "js" / "logica.js").read_text(encoding="utf-8")


def test_a_chave_da_LOGICA_vem_antes_do_dicionario_e_depois_do_par():
    """Ordem ditada por ele em 21/10/2026: lógica, eventos, exportar,
    arquivos, menu, dicionário, ajuda e tema."""
    onda = _template("onda.html")
    assert 'id="logica"' in onda
    assert "--ic-logica:" in _osclab_css()
    depois_do_par = onda.split('data-lado="primario"')[1]
    assert depois_do_par.index('id="logica"') < depois_do_par.index('id="dicionario"')
    assert "js/logica.js" in onda


def test_o_painel_da_logica_mostra_os_AJUSTES_primeiro():
    """Escolha dele: antes de entender a equação se quer saber com que número
    ela foi comparada."""
    js = _logica_js()
    assert js.index('grupo("Ajustes"') < js.index('grupo("Lógica"')


def test_o_painel_da_logica_e_SECO():
    """Nada de dicionário, nada de descrição, nada de conversão: o que está na
    tela é o que está dentro do arquivo — decisão dele, 19/10/2026."""
    js = _logica_js()
    assert "/api/dicionario/" not in js
    assert "janela-do-dicionario" not in js
    assert "verbete" not in js
    assert "descricao" not in js
    # e o valor sai letra por letra: a única coisa que o painel faz com ele é
    # dar cor a operador e grifar o que foi procurado
    assert "white-space: pre-wrap" in _osclab_css().split(".linha-da-logica .valor")[1]


def test_o_painel_da_logica_FLUTUA_e_nao_e_modal():
    """O pedido era ver a lógica ao mesmo tempo que os sinais; janela modal
    apaga a tela atrás, e a tela atrás é metade do assunto."""
    onda = _template("onda.html")
    assert 'id="painel-da-logica"' in onda
    assert "<dialog" not in onda.split('id="painel-da-logica"')[1].split("</div>")[0]
    js = _logica_js()
    assert "showModal" not in js
    css = _osclab_css().split(".painel-flutuante {")[1].split("}")[0]
    assert "position: fixed" in css
    assert "resize: both" in css              # estica pelo canto


def test_o_painel_da_logica_ARRASTA_pela_barra_e_lembra_onde_ficou():
    """Painel que volta ao mesmo canto a cada abertura obriga a arrastá-lo de
    novo toda vez."""
    js = _logica_js()
    assert 'barra.addEventListener("pointerdown"' in js
    # os ouvintes do arrasto ficam na JANELA: com captura na barra o Chrome
    # devolvia o ponteiro depois de dois movimentos e o painel andava 25 dos
    # 300 pixels pedidos (medido em 19/10/2026).
    assert 'window.addEventListener("pointermove", arrastar)' in js
    assert "barra.setPointerCapture" not in js
    assert 'localStorage.setItem(LEMBRANCA' in js
    assert "function dentroDaTela" in js      # e nunca some da tela


def test_o_painel_da_logica_tem_BUSCADOR():
    """Pedido dele. Um relé traz centenas de ajustes; sem busca o painel é uma
    parede de texto."""
    onda = _template("onda.html")
    assert 'id="busca-da-logica"' in onda
    js = _logica_js()
    assert 'campo.addEventListener("input", pintar)' in js
    assert '(n + " " + v).toLowerCase().includes(alvo)' in js
    assert 'criar("mark"' in js               # e grifa o que achou


def test_sem_ajustes_a_chave_da_logica_fica_CINZA_e_explica():
    """Mesma regra do dicionário: o clique diz por que está vazio — e «por que
    está vazio» é informação técnica aqui, porque o COMTRADE puro não prevê
    ajuste nenhum."""
    js = _logica_js()
    assert 'chave.classList.add("sem-logica")' in js
    assert 'chave.classList.toggle("sem-logica", !tem)' in js
    assert "chave.disabled" not in js
    assert "SETTINGS" in js                   # e diz onde eles moram
    assert ".chave.sem-logica" in _osclab_css()


def test_sem_ajustes_o_painel_nao_mostra_campo_de_busca():
    """Campo de busca sem nada para buscar é um convite a digitar e não achar
    nada."""
    js = _logica_js()
    assert "campo.hidden = !(estado && estado.tem);" in js
    assert "if (!campo.hidden) { campo.focus(); campo.select(); }" in js


def test_a_BASE_DE_DADOS_fica_na_barra_do_aplicativo_e_nao_na_fileira():
    """A fileira é do REGISTRO — modo, filtro, ímã, lado, lógica, dicionário.
    A base vale para o programa inteiro: subiu para a linha do título em
    19/10/2026 e, em 22/10/2026, para a barra do aplicativo, à direita, junto
    do exportar."""
    onda = _template("onda.html")
    assert 'id="base-de-dados"' in onda
    assert "--ic-base" in onda
    barra = onda[onda.index('<nav class="barra-do-app"'):onda.index("</nav>")]
    assert 'id="base-de-dados"' in barra
    assert barra.index('id="exportar"') < barra.index('id="base-de-dados"')
    assert onda.index("</nav>") < onda.index('<header class="topo registro">')
    assert 'href="/base"' in onda


def test_a_tela_de_arquivos_diz_o_MINIMO_e_o_que_traz_a_logica():
    """O .cfg e o .dat fazem o leitor funcionar; o .hdr é o que traz lógica e
    ajuste. Escolha dele, 19/10/2026."""
    html = _template("index.html")
    assert "<strong>mínimo</strong>" in html
    assert "<strong>lógica e os ajustes</strong>" in html
    assert html.index("<code>.cfg</code>") < html.index("<code>.hdr</code>")


def test_o_registro_SEM_hdr_avisa_que_nao_tem_logica():
    """Dito na hora do envio ainda dá para arrastar o arquivo que falta; no
    painel vazio lá dentro, já não."""
    js = (paths.STATIC_DIR / "js" / "acervo.js").read_text(encoding="utf-8")
    assert "sem lógica/ajustes" in js
    assert '.endsWith(".hdr")' in js
    assert '.endsWith(".cev")' in js
    assert ".sem-logica" in _osclab_css()


def test_os_botoes_da_base_dizem_DATABASE():
    """«usar esta» não diz o quê. Escolha dele, 19/10/2026."""
    assert '"usar esta database"' in _base_js()
    assert "editar database" in _template("menu.html")


def test_as_fileiras_de_chaves_nao_quebram_linha_nem_rolam_a_pagina():
    """Ampliar a página (Ctrl +) fazia os botões saírem da tela e a página
    ganhar barra horizontal: eles mudavam de lugar conforme o zoom. Medido e
    corrigido em 19/10/2026 — duas fileiras, cada uma rolando dentro de si."""
    onda = _template("onda.html")
    assert onda.count('<div class="acoes">') == 2
    css = _osclab_css()
    trecho = css[css.index(".topo.registro {"):]
    trecho = trecho[:trecho.index(".topo h1")]
    # num flex de COLUNA, `wrap` quebra em COLUNAS e a largura vem do conteúdo
    assert "flex-wrap: nowrap;" in trecho
    acoes = css[css.index(".topo.registro .acoes {"):]
    acoes = acoes[:acoes.index("}")]
    assert "flex-wrap: nowrap" in acoes
    assert "overflow-x: auto" in acoes
    assert "min-width: 0" in acoes
    # e o nome do registro, que é uma palavra só, quebra onde precisar
    assert "overflow-wrap: anywhere" in css[css.index(".topo h1 {"):][:300]


def test_a_paleta_das_tiras_tem_VERMELHO():
    """Pedido dele, 19/10/2026. É o `--ruim`, o mesmo tom do trip no resto do
    programa: uma coisa, uma cor."""
    js = _onda_js()
    trecho = js[js.index("const CORES_DAS_TIRAS = ["):]
    trecho = trecho[:trecho.index("];")]
    assert '"--ruim"' in trecho
    assert '"--fase-c"' not in trecho      # duas vermelhas ninguém distingue
