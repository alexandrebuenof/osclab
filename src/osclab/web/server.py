"""O servidor web do OscLab.

Uma regra vale para tudo que entrar aqui: **esta camada não calcula.** Ela
recebe um pedido, chama quem sabe fazer a conta e devolve o resultado. Ler
formato, processar sinal e localizar falta ficam inteiros fora de `web/` — é o
que permite rodar em lote, testar sem navegador e gerar o relatório sem abrir
uma tela.

`create_app()` devolve a aplicação sem subir servidor nenhum, o que é o que
torna o teste possível: o pytest usa o cliente de teste do Flask e nunca abre
uma porta.

## As rotas

```
GET    /                          o acervo: arrastar arquivos e ver o que entrou
GET    /api/acervo                a lista, em JSON
POST   /api/acervo                envio de arquivos (multipart)
DELETE /api/acervo/<sha>          tira um registro do acervo
GET    /onda/<sha>                a tela de formas de onda
GET    /api/onda/<sha>            uma janela do registro, pronta para desenhar
GET    /api/onda/<sha>/leitura    o valor de cada canal onde os cursores estão
GET    /saude                     diagnóstico
```

A rota da janela aceita `de`, `ate`, `colunas` e `lado` — e mais `zoom`, `foco`,
`andar` e `tudo`, que são os gestos do mouse. É ela que sustenta o zoom sem o
navegador nunca segurar o registro inteiro: ampliar é pedir outra janela.
"""

from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from osclab import paths, version
from osclab.formats import registry
from osclab.formats.base import FormatError
from osclab.library import acervo
from osclab.plot import janela, leitura, navegacao

#: Teto do envio. Um `.dat` de SEL-487E tem 4,7 MB; alguém vai arrastar a pasta
#: inteira de uma vez, e recusar por tamanho no meio disso seria irritante.
TAMANHO_MAXIMO = 512 * 1024 * 1024


def create_app() -> Flask:
    """Monta a aplicação Flask. Não sobe servidor."""
    paths.ensure_runtime_dirs()

    app = Flask(
        __name__,
        template_folder=str(paths.TEMPLATES_DIR),
        static_folder=str(paths.STATIC_DIR),
    )
    app.config["MAX_CONTENT_LENGTH"] = TAMANHO_MAXIMO

    # -----------------------------------------------------------------------
    # Páginas
    # -----------------------------------------------------------------------

    @app.get("/")
    def home():
        return render_template(
            "index.html",
            versao=version.read(),
            formatos=[r.name for r in registry.readers()],
        )

    @app.get("/onda/<sha>")
    def onda(sha: str):
        item = acervo.obter(sha)
        if item is None:
            return render_template("nao-achei.html", versao=version.read()), 404
        return render_template("onda.html", versao=version.read(),
                               item=item.como_dicionario())

    # -----------------------------------------------------------------------
    # API do acervo
    # -----------------------------------------------------------------------

    @app.get("/api/acervo")
    def listar_acervo():
        return jsonify(
            itens=[i.como_dicionario() for i in acervo.listar()],
            aguardando=_antessala_em_json(),
        )

    @app.post("/api/acervo")
    def enviar_para_acervo():
        enviados = [
            (f.filename or "", f.read())
            for f in request.files.getlist("arquivos")
            if f and f.filename
        ]
        resultado = acervo.guardar(enviados)
        return jsonify(
            aceitos=[i.como_dicionario() for i in resultado.aceitos],
            repetidos=[i.como_dicionario() for i in resultado.repetidos],
            problemas=resultado.problemas,
            aguardando=resultado.aguardando,
            na_antessala=_antessala_em_json(),
        )

    @app.get("/api/onda/<sha>")
    def janela_da_onda(sha: str):
        try:
            registro = acervo.ler(sha)
        except FormatError as exc:
            return jsonify(erro=str(exc)), 404
        # A tela manda o GESTO (ampliar tanto em torno deste instante, andar
        # tantos segundos) e a janela em que ela estava. Quem decide a janela
        # resultante é `plot/navegacao`, que conhece as bordas do registro e o
        # piso de amostras — nada disso é decidido no navegador.
        de, ate = navegacao.resolver(
            registro,
            de=_numero(request.args.get("de")),
            ate=_numero(request.args.get("ate")),
            zoom=_numero(request.args.get("zoom")),
            foco=_numero(request.args.get("foco")),
            andar=_numero(request.args.get("andar")),
            tudo=request.args.get("tudo") in ("1", "sim", "true"),
        )
        return jsonify(janela.montar(
            registro,
            de=de,
            ate=ate,
            colunas=int(_numero(request.args.get("colunas")) or 900),
            lado=request.args.get("lado", "arquivo"),
        ))

    @app.get("/api/onda/<sha>/leitura")
    def leitura_dos_cursores(sha: str):
        try:
            registro = acervo.ler(sha)
        except FormatError as exc:
            return jsonify(erro=str(exc)), 404

        # O valor NUNCA sai do traço desenhado: o desenho é mínimo e máximo por
        # coluna de pixel, não a amostra. Quem lê é o servidor, na amostra.
        pedidos = [
            (_numero(request.args.get(f"t{k}")),
             int(_numero(request.args.get(f"passo{k}")) or 0),
             _numero(request.args.get(f"ciclos{k}")) or 0.0)
            for k in (1, 2)
        ]
        # `refere` é o canal que o usuário clicou para virar o zero dos
        # ângulos. A subtração é feita no servidor, como todo número.
        refere = _numero(request.args.get("refere"))
        return jsonify(leitura.em(
            registro, pedidos,
            lado=request.args.get("lado", "arquivo"),
            refere=int(refere) if refere is not None else None,
        ))

    @app.delete("/api/aguardando")
    def esquecer_aguardando():
        return jsonify(removidos=acervo.esquecer_aguardando())

    @app.delete("/api/acervo/<sha>")
    def remover_do_acervo(sha: str):
        if not acervo.remover(sha):
            return jsonify(erro="Este registro nao esta' no acervo."), 404
        return jsonify(removido=sha)

    # -----------------------------------------------------------------------
    # Diagnóstico
    # -----------------------------------------------------------------------

    @app.get("/saude")
    def saude():
        return jsonify(
            versao=version.read(),
            raiz=str(paths.PROJECT_ROOT),
            dados=str(paths.DATA_DIR),
            formatos=[r.name for r in registry.readers()],
            registros_no_acervo=len(acervo.listar()),
            arquivos_aguardando=len(_antessala_em_json()),
        )

    @app.errorhandler(413)
    def grande_demais(_):
        limite = TAMANHO_MAXIMO // (1024 * 1024)
        return jsonify(
            problemas=[f"O envio passou de {limite} MB. Mande menos arquivos "
                       f"de uma vez."]
        ), 413

    return app


def _antessala_em_json() -> list[dict]:
    """Quem está esperando o par, em forma de lista para a tela."""
    return [
        {"nome": base, "tem": sorted(por_extensao), "arquivos":
            sorted(por_extensao.values())}
        for base, por_extensao in sorted(acervo.aguardando().items())
    ]


def _numero(texto: str | None) -> float | None:
    """Um parâmetro numérico da URL, ou `None` quando ausente ou sem sentido.

    Nunca levanta: quem manda a URL é o navegador, e um valor estranho tem que
    virar "sem filtro", não erro 500.
    """
    if texto is None or not texto.strip():
        return None
    try:
        valor = float(texto)
    except ValueError:
        return None
    return valor if valor == valor else None      # NaN vira None


def serve(port: int = 8770, host: str = "127.0.0.1") -> None:
    """Sobe o servidor.

    `host` é o laço local de propósito: a ferramenta é de uso pessoal na máquina
    de quem analisa. Expor para a rede é uma decisão consciente, não um padrão.
    """
    create_app().run(host=host, port=port, debug=False)
