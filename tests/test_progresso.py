"""O progresso da ABERTURA de um registro (14/11/2026).

A barra da tela só pinta o que o servidor diz; estes testes prendem o que
ele diz: as etapas saem NA ORDEM (ler · bruto × filtrado · canais · contas ·
desenho), a fração só cresce e vai de 0 a 1, o erro vira estado de erro, o
registro já aberto não abre abertura nenhuma (gesto não tem barra), e dois
pedidos que abrem o mesmo registro ao mesmo tempo o leem UMA vez.
"""

from __future__ import annotations

import threading
import time

import pytest

from osclab import paths, progresso
from osclab.formats import registry
from osclab.library import acervo
from tests.fabrica import escrever_comtrade


@pytest.fixture
def acervo_temporario(tmp_path, monkeypatch):
    for nome in ("LIBRARY_DIR", "CACHE_DIR", "CONFIG_DIR"):
        monkeypatch.setattr(paths, nome, tmp_path / nome.lower())
    acervo._abertos.clear()
    yield tmp_path
    acervo._abertos.clear()


def _guardar(pasta, nome="REG", **kw):
    kw.setdefault("na", 6)
    kw.setdefault("nd", 8)
    kw.setdefault("n", 4000)
    kw.setdefault("taxa", 2000.0)
    cfg = escrever_comtrade(pasta / nome, nome=nome, degraus=True, **kw)
    r = acervo.guardar([(p.name, p.read_bytes()) for p in (cfg, cfg.with_suffix(".dat"))])
    assert len(r.aceitos) == 1, r.problemas
    acervo._abertos.clear()
    return r.aceitos[0].sha


def _espiar(monkeypatch, token):
    """Fotografa `estado(token)` a cada passo que o trabalho anuncia."""
    fotos = []

    def foto():
        e = progresso.estado(token)
        if e is not None:
            fotos.append(e)

    for nome in ("etapa", "avancar", "lido"):
        original = getattr(progresso, nome)

        def embrulho(*a, _o=original, **k):
            r = _o(*a, **k)
            foto()
            return r
        monkeypatch.setattr(progresso, nome, embrulho)
    conta_original = progresso.conta

    from contextlib import contextmanager

    @contextmanager
    def conta(nome):
        with conta_original(nome):
            foto()
            yield
        foto()
    monkeypatch.setattr(progresso, "conta", conta)
    return fotos


def _confere_ordem_e_fracoes(fotos):
    etapas = [f["etapa"] for f in fotos]
    vistas = list(dict.fromkeys(etapas))
    # Nenhuma etapa volta depois de a seguinte ter começado.
    assert vistas == sorted(vistas, key=progresso.ORDEM.index), vistas
    fr = [f["fracao"] for f in fotos]
    assert all(0.0 <= x <= 1.0 for x in fr)
    assert fr == sorted(fr), "a fração andou para trás"
    return vistas


def test_a_abertura_anda_pelas_etapas_em_ordem(acervo_temporario, cliente, monkeypatch):
    sha = _guardar(acervo_temporario)
    fotos = _espiar(monkeypatch, "T1")
    r = cliente.get(f"/api/onda/{sha}?abertura=T1&colunas=600")
    assert r.status_code == 200
    vistas = _confere_ordem_e_fracoes(fotos)
    assert vistas == list(progresso.ORDEM), vistas
    # Dentro do diagnóstico e das contas a fração anda canal a canal: há
    # mais de um valor distinto em cada uma.
    for etapa in ("diagnostico", "contas"):
        assert len({f["fracao"] for f in fotos if f["etapa"] == etapa}) > 2, etapa
    assert fotos[0]["fracao"] < 0.05
    fim = cliente.get("/api/abertura/T1").get_json()
    assert fim["pronto"] and fim["erro"] is None and fim["fracao"] == 1.0
    # A etapa das contas diz QUAL conta está andando.
    rotulos = {f["rotulo"] for f in fotos}
    assert "presença de sinal" in rotulos
    # A energia do catálogo não é mais feita ao abrir (14/11/2026).
    assert "energia dos sinais" not in rotulos


def test_a_energia_do_catalogo_tem_barra_so_dela(acervo_temporario, cliente, monkeypatch):
    """O «+ sinal» de um registro gigante pede a energia com um token: a barra
    é SÓ dela, de 0 a 100 %, dita «energia dos sinais», e anda linha a linha."""
    sha = _guardar(acervo_temporario)
    assert cliente.get(f"/api/onda/{sha}?colunas=600").status_code == 200
    fotos = _espiar(monkeypatch, "TE")
    r = cliente.post(f"/api/onda/{sha}/energia?abertura=TE", json={})
    assert r.status_code == 200 and r.get_json()["energia"]
    assert fotos and {f["etapa"] for f in fotos} == {"contas"}
    assert {f["rotulo"] for f in fotos} == {"energia dos sinais"}
    fr = [f["fracao"] for f in fotos]
    assert fr == sorted(fr) and fr[0] < 0.2 and len(set(fr)) > 2
    fim = cliente.get("/api/abertura/TE").get_json()
    assert fim["pronto"] and fim["erro"] is None and fim["fracao"] == 1.0
    # A rota dá o mesmo número da conta, com o lado e as contas do pedido.
    from osclab.plot import contas as contas_mod
    from osclab.plot import janela
    registro = acervo.ler(sha)
    assert r.get_json()["energia"] == janela.energia(registro)
    contas = [{"id": "x1", "nome": "SOMA", "expressao": "[IAW] + [IBW]"}]
    r2 = cliente.post(f"/api/onda/{sha}/energia?lado=primario", json={"contas": contas})
    assert r2.get_json()["energia"] == janela.energia(
        registro, lado="primario", contas=contas_mod.de_json(contas))
    assert "SOMA" in r2.get_json()["energia"]


def test_registro_ja_aberto_nao_abre_abertura(acervo_temporario, cliente):
    sha = _guardar(acervo_temporario)
    assert cliente.get(f"/api/onda/{sha}?colunas=600").status_code == 200
    assert acervo.esta_aberto(sha)
    assert cliente.get(f"/api/onda/{sha}?abertura=T2&colunas=600").status_code == 200
    assert cliente.get("/api/abertura/T2").get_json() == {"ativa": False}


def test_sem_token_o_pedido_e_o_de_sempre(acervo_temporario, cliente):
    sha = _guardar(acervo_temporario)
    assert cliente.get(f"/api/onda/{sha}?colunas=600").status_code == 200
    assert cliente.get("/api/abertura/qualquer").get_json() == {"ativa": False}


def test_o_segundo_registro_da_aba_tambem_e_acompanhado(acervo_temporario, cliente,
                                                        monkeypatch):
    a = _guardar(acervo_temporario, "A")
    assert cliente.get(f"/api/onda/{a}?colunas=600").status_code == 200
    b = _guardar(acervo_temporario, "B", n=3000)
    assert cliente.get(f"/api/onda/{a}?colunas=600").status_code == 200   # A de novo aberto
    fotos = _espiar(monkeypatch, "T3")
    r = cliente.post(f"/api/onda/{a}?abertura=T3&colunas=600",
                     json={"registros": [{"sha": b}]})
    assert r.status_code == 200
    _confere_ordem_e_fracoes(fotos)
    assert fotos and fotos[-1]["registros"] == 1     # só B era novo
    assert cliente.get("/api/abertura/T3").get_json()["fracao"] == 1.0


def test_erro_na_abertura_vira_estado_de_erro(acervo_temporario, cliente):
    sha = _guardar(acervo_temporario)
    # O `.dat` some: o leitor não consegue abrir o registro.
    pasta = acervo.pasta_do_registro(sha)
    for p in pasta.iterdir():
        if p.suffix.lower() == ".dat":
            p.unlink()
    r = cliente.get(f"/api/onda/{sha}?abertura=T4&colunas=600")
    assert r.status_code == 404
    e = cliente.get("/api/abertura/T4").get_json()
    assert e["pronto"] and e["erro"] and e["fracao"] < 1.0


def test_excecao_inesperada_tambem_vira_erro():
    with pytest.raises(RuntimeError), progresso.abrindo("T5", ["x"]):
        progresso.etapa("contas")
        raise RuntimeError("quebrou no meio")
    e = progresso.estado("T5")
    assert e["pronto"] and e["erro"] == "quebrou no meio" and e["etapa"] == "contas"


def test_fora_de_uma_abertura_nada_acontece(tmp_path):
    # O leitor chamado pelo teste, pelo modo lote ou pelo cursor não paga nada.
    progresso.etapa("ler")
    progresso.avancar(1, 2)
    with progresso.conta("catalogo.energia"):
        pass
    assert registry.read(escrever_comtrade(tmp_path, n=600)) is not None


def test_a_fracao_nunca_passa_de_1_antes_do_fim():
    with progresso.abrindo("T6", ["a", "b"]):
        with progresso.lendo("a"):
            progresso.etapa("canais")
            progresso.avancar(5, 1)          # 500 %: preso em 100 % da etapa
        progresso.lido("b")
        progresso.etapa("contas")
        for _ in range(40):                  # conta a mais do que o previsto
            with progresso.conta("catalogo.energia"):
                pass
        e = progresso.estado("T6")
        assert e["etapa"] == "contas" and e["fracao"] < 1.0
        progresso.etapa("desenho")
        assert progresso.estado("T6")["fracao"] < 1.0
    assert progresso.estado("T6")["fracao"] == 1.0


def test_dois_pedidos_abrem_o_mesmo_registro_uma_vez(acervo_temporario, monkeypatch):
    sha = _guardar(acervo_temporario)
    leituras = {"n": 0}
    original = registry.read

    def lento(caminho):
        leituras["n"] += 1
        time.sleep(0.2)
        return original(caminho)
    monkeypatch.setattr(registry, "read", lento)
    saida = []
    fios = [threading.Thread(target=lambda: saida.append(acervo.ler(sha))) for _ in range(3)]
    for f in fios:
        f.start()
    for f in fios:
        f.join()
    assert leituras["n"] == 1
    assert len(saida) == 3 and all(r is saida[0] for r in saida)


def test_quem_espera_acompanha_a_leitura_do_outro(acervo_temporario, monkeypatch):
    """O pedido que espera a trava vê a leitura do outro andar (é do sha)."""
    sha = _guardar(acervo_temporario)
    original = registry.read
    pode = threading.Event()

    def lento(caminho):
        progresso.etapa("ler")
        progresso.avancar(1, 2)
        pode.wait(5)
        return original(caminho)
    monkeypatch.setattr(registry, "read", lento)
    primeiro = threading.Thread(target=lambda: acervo.ler(sha))
    primeiro.start()
    time.sleep(0.1)

    vistos = []

    def segundo():
        with progresso.abrindo("T7", [sha]):
            acervo.ler(sha)
    fio = threading.Thread(target=segundo)
    fio.start()
    time.sleep(0.1)
    vistos.append(progresso.estado("T7"))
    pode.set()
    primeiro.join()
    fio.join()
    assert vistos[0]["etapa"] == "ler" and vistos[0]["fracao"] > 0
    assert progresso.estado("T7")["fracao"] == 1.0
