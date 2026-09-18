"""Todos os caminhos saem de `paths.py`. Se isso quebrar, quebra em silêncio —
o programa passa a gravar dados do usuário dentro da pasta da versão, e a
próxima atualização os apaga."""

from pathlib import Path

from osclab import paths


def test_a_raiz_contem_o_app():
    assert (paths.PROJECT_ROOT / "app.py").is_file()


def test_o_pacote_esta_onde_paths_diz():
    assert (paths.PACKAGE_DIR / "__init__.py").is_file()


def test_os_recursos_da_web_viajam_com_o_pacote():
    """Templates e estáticos ficam DENTRO do pacote — é o que os mantém juntos
    quando um dia o programa for empacotado num executável."""
    assert (paths.TEMPLATES_DIR / "index.html").is_file()
    assert paths.STATIC_DIR.is_dir()


def test_o_modelo_de_configuracao_e_versionado():
    assert paths.CONFIG_EXAMPLE.is_file()


def test_ensure_runtime_dirs_e_idempotente(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(paths, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(paths, "LIBRARY_DIR", tmp_path / "library")
    paths.ensure_runtime_dirs()
    paths.ensure_runtime_dirs()          # de novo: não pode explodir
    assert (tmp_path / "config").is_dir()
    assert (tmp_path / "cache").is_dir()
    assert (tmp_path / "library").is_dir()


def test_is_within_barra_fuga_de_pasta(tmp_path):
    """É o que impede um `../../` vindo do navegador de escapar da pasta."""
    dentro = tmp_path / "sub" / "arquivo.cfg"
    assert paths.is_within(dentro, tmp_path)
    assert not paths.is_within(Path(tmp_path).parent / "outro.cfg", tmp_path)
    assert not paths.is_within(tmp_path / ".." / "fora.cfg", tmp_path)
