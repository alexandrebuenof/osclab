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
POST   /api/acervo/<sha>/nome     renomeia o registro DENTRO do OscLab
GET    /api/acervo/<sha>/exportar baixa os arquivos com o nome escolhido
GET    /onda/<sha>                a tela de formas de onda
GET    /api/onda/<sha>            uma janela do registro, pronta para desenhar
POST   /api/onda/<sha>            a mesma janela, com o arranjo de painéis
GET    /api/onda/<sha>/leitura    o valor de cada sinal onde os cursores estão
POST   /api/onda/<sha>/leitura    a mesma leitura, com o arranjo de painéis
POST   /api/onda/<sha>/vinculos   corrige a fase de um canal, e guarda
GET    /base                      a base de dados: gavetas e chaves
GET    /api/base                  o estado da base, em JSON
GET    /api/base/pastas           as subpastas de um caminho, para escolher onde
POST   /api/base/pasta-nativa     abre o diálogo de pasta do próprio sistema
POST   /api/base/criar            cria uma base nova e a deixa ativa
POST   /api/base/escolher         passa a usar uma base que já existe
POST   /api/base/gaveta           liga e desliga uma gaveta
GET    /api/base/dicionario       o dicionário dos sinais digitais
GET    /api/dicionario/<sha>      o que o dicionário sabe sobre ESTE registro
GET    /api/logica/<sha>          os ajustes e a lógica que vieram no arquivo
POST   /api/eventos/<sha>         a lista de eventos do relé, de cada registro da aba
POST   /api/eventos/<sha>/trilha  quantos eventos caem em cada intervalo, para a trilha
POST   /api/base/dicionario         cria ou corrige um verbete
POST   /api/base/dicionario/importar junta um CSV de fora ao que já existe
GET    /saude                     diagnóstico
```

A rota da janela aceita `de`, `ate`, `colunas` e `lado` — e mais `zoom`, `foco`,
`andar` e `tudo`, que são os gestos do mouse. É ela que sustenta o zoom sem o
navegador nunca segurar o registro inteiro: ampliar é pedir outra janela.

## Por que as duas rotas também atendem em POST

Porque o arranjo dos gráficos é ESTRUTURA — uma lista de painéis, cada um com
os seus sinais — e estrutura não cabe em `query string` sem inventar um formato
para depois ter que desfazê-lo do outro lado. Um nome de gráfico escolhido pelo
usuário pode ter vírgula, ponto-e-vírgula e acento; a URL ainda tem teto de
tamanho, e um registro com trinta painéis o estoura.

O GET continua valendo, e é ele que a tela usa na PRIMEIRA janela: ali ela
ainda não tem arranjo nenhum, e quem monta o padrão é o servidor.
"""

from __future__ import annotations

import functools
import io
import zipfile
from pathlib import Path

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_file,
    send_from_directory,
)

from osclab import paths, version
from osclab.analysis import falta as falta_mod
from osclab.basedados import digitais as digitais_mod
from osclab.basedados import linhas as linhas_mod
from osclab.basedados import navegar as navegar_mod
from osclab.basedados import pasta as base_mod
from osclab.basedados import tres_terminais as tres_terminais_mod
from osclab.dsp import fasor as fasor_mod
from osclab.faultloc import ldl as ldl_mod
from osclab.faultloc import parametros as parametros_mod
from osclab.faultloc import refino as refino_conta
from osclab.faultloc import rele as rele_mod
from osclab.faultloc import seqneg as seqneg_mod
from osclab.formats import ajustes as ajustes_mod
from osclab.formats import eventos as eventos_mod
from osclab.formats import registry
from osclab.formats import relacoes as relacoes_mod
from osclab.formats.base import FormatError
from osclab.library import acervo
from osclab.plot import alinhamento as alinhamento_mod
from osclab.plot import calculadora as calculadora_mod
from osclab.plot import contas as contas_mod
from osclab.plot import eventos as eventos_plot
from osclab.plot import impedancia as impedancia_mod
from osclab.plot import janela, leitura, navegacao, paineis
from osclab.plot import localizador as localizador_mod
from osclab.plot import refino as refino_mod
from osclab.plot import varios as varios_mod

#: Teto do envio. Um `.dat` de SEL-487E tem 4,7 MB; alguém vai arrastar a pasta
#: inteira de uma vez, e recusar por tamanho no meio disso seria irritante.
TAMANHO_MAXIMO = 512 * 1024 * 1024

#: Como o rodapé e o «sobre» escrevem cada leitor. O nome interno (`cev`) é
#: identificador; quem lê a tela quer saber que arquivo abre.
NOME_DO_FORMATO = {
    "comtrade": "COMTRADE (.cfg + .dat, .cff)",
    "cev": "SEL .CEV (relatório de evento)",
    "sel-texto": "SEL, relatório em texto",
}


def create_app() -> Flask:
    """Monta a aplicação Flask. Não sobe servidor."""
    paths.ensure_runtime_dirs()

    app = Flask(
        __name__,
        template_folder=str(paths.TEMPLATES_DIR),
        static_folder=str(paths.STATIC_DIR),
    )
    app.config["MAX_CONTENT_LENGTH"] = TAMANHO_MAXIMO

    @app.url_defaults
    def _versao_do_estatico(endpoint, valores):
        """Todo `.js` e `.css` sai com `?v=<instante em que mudou>` no link.

        Sem isto o navegador podia continuar rodando o `onda.js` de antes de
        uma correção: o Flask não manda prazo de validade, e aí vale o palpite
        do navegador, que guarda o arquivo por um tempo proporcional à idade
        dele. Já custou rodadas de "ainda está com o bug" sobre um conserto que
        estava no disco e não na tela. Com o instante no link, arquivo novo é
        endereço novo, e o Ctrl+F5 deixa de ser parte do procedimento.
        """
        if endpoint != "static" or "filename" not in valores:
            return
        try:
            arquivo = Path(app.static_folder) / valores["filename"]
            valores["v"] = int(arquivo.stat().st_mtime)
        except OSError:
            pass

    # -----------------------------------------------------------------------
    # Páginas
    # -----------------------------------------------------------------------

    @app.context_processor
    def _o_que_a_moldura_le():
        """O que a barra de cima e o rodapé leem em TODA página.

        Num lugar só para a moldura não depender de cada rota lembrar de
        mandar. A contagem do acervo é uma FUNÇÃO, e não um número: a página
        da onda dentro de uma aba não desenha a barra, e não há por que ler o
        acervo inteiro para ela. Valor passado pela rota vence este (é a regra
        do Flask), então `versao=` explícito continua valendo.
        """
        return {
            "versao": version.read(),
            "contar_acervo": lambda: len(acervo.listar()),
            "formatos_lidos": [NOME_DO_FORMATO.get(r.name, r.name)
                               for r in registry.readers()],
            # O `accept` de todo campo de envio sai da MESMA lista que o
            # acervo usa para separar o que é oscilografia: página Arquivos e
            # menus da tela de oscilografia não podem aceitar coisas diferentes.
            "aceita_no_acervo": ",".join(
                f"{e},{e.upper()}" for e in sorted(acervo.EXTENSOES)),
        }

    @app.template_filter("milhar")
    def _milhar(v) -> str:
        """`9600` -> `9.600`. O ponto e' o separador de milhar em pt-BR, e
        quatro digitos colados num numero de amostras se leem errado."""
        try:
            return f"{int(v):,}".replace(",", ".")
        except (TypeError, ValueError):
            return str(v)

    @app.get("/")
    def menu():
        """A tela inicial: escolher o modulo.

        O acervo saiu da raiz e foi para `/arquivos`. A raiz passou a ser a
        porta da ferramenta inteira -- hoje com um modulo pronto e tres
        anunciados -- porque a oscilografia e' o PRIMEIRO modulo, e nao a
        ferramenta toda; sem essa tela, os outros tres nasceriam escondidos
        dentro da tela de arquivos de um deles.
        """
        return render_template("menu.html", versao=version.read(),
                               base=base_mod.estado())

    @app.get("/arquivos")
    def home():
        return render_template(
            "index.html",
            versao=version.read(),
            formatos=[r.name for r in registry.readers()],
        )

    @app.get("/abas")
    def abas():
        """As abas de oscilografia, como as de um navegador. Cada aba é a
        página `/onda/<sha>` num quadro próprio, independente das outras; a
        lista das abertas mora na sessão do navegador. Ver `static/js/abas.js`.
        """
        return render_template("abas.html", versao=version.read())

    @app.get("/onda/<sha>")
    def onda(sha: str):
        item = acervo.obter(sha)
        if item is None:
            return render_template("nao-achei.html", versao=version.read()), 404
        dados = item.como_dicionario()
        # TC e TP por EQUIPAMENTO, só quando há mais de uma relação
        # (o «vários» da tira). Lê o registro, e por isso só nesse caso; os
        # vínculos do usuário entram aqui, então não dá para guardar no resumo.
        relacoes = []
        if "vários" in (dados.get("relacao_tc"), dados.get("relacao_tp")):
            try:
                relacoes = acervo.relacoes_por_equipamento(acervo.ler(sha))
            except FormatError:
                relacoes = []
        return render_template(
            "onda.html", versao=version.read(), item=dados, relacoes=relacoes,
            # Dentro de uma aba (`/abas` abre `?aba=<id>`) a barra de cima já
            # está na janela de fora: repeti-la no quadro poria duas barras.
            em_aba="aba" in request.args,
            # Quem compara é o servidor, não o Jinja: `AB` × `AB T` precisa de
            # normalização, e normalizar sigla dentro de template é o tipo de
            # regra que ninguém acha depois. Ver `analysis/falta.mesmo_tipo`.
            conflita_a_falta=not falta_mod.rele_concorda(
                dados.get("falta_tipo", ""), dados.get("falta_inicial", ""),
                dados.get("classificacao_do_rele", "")),
            # `TRIP`, `ER` no lugar da sigla: não concorda nem discorda, e o
            # «✓ relé» afirmaria «o mesmo tipo» de um tipo que não existe.
            rele_tem_tipo=falta_mod.e_tipo_de_falta(
                dados.get("classificacao_do_rele", "")),
        )

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

    @app.route("/api/onda/<sha>", methods=["GET", "POST"])
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
        arranjo = _layout()
        outros = _outros_registros(sha)
        # O ESTIMADOR do fasor (Fourier ou cosseno) vale para tudo que este
        # pedido calcula. Ver `dsp/fasor.usando`.
        with fasor_mod.usando(request.args.get("estimador")):
            if outros:
                # Mais de um registro na aba: o A como sempre, os outros na
                # janela deslocada de cada um. Ver `plot/varios.py`.
                return jsonify(varios_mod.montar_janela(
                    registro, outros, alinhar=_alinhar(), montar=janela.montar,
                    apelido_a=acervo.apelido(sha), sha_a=sha,
                    de=de, ate=ate,
                    colunas=int(_numero(request.args.get("colunas")) or 900),
                    lado=request.args.get("lado", "arquivo"),
                    filtro=request.args.get("filtro") in ("1", "sim", "true"),
                    layout=arranjo, contas=_contas(),
                    ajustes=_ajustes_do_registro(sha, registro, arranjo)))
            return jsonify(janela.montar(
                registro,
                de=de,
                ate=ate,
                colunas=int(_numero(request.args.get("colunas")) or 900),
                lado=request.args.get("lado", "arquivo"),
                filtro=request.args.get("filtro") in ("1", "sim", "true"),
                layout=arranjo,
                contas=_contas(),
                # Os ajustes do relé só são lidos quando há um painel que precisa
                # deles. Ler o `.hdr` a cada arrasto de janela seria um arquivo a
                # mais aberto em todo gesto, para nada na maioria das telas.
                ajustes=_ajustes_do_registro(sha, registro, arranjo),
            ))

    @app.route("/api/onda/<sha>/leitura", methods=["GET", "POST"])
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
        outros = _outros_registros(sha)
        with fasor_mod.usando(request.args.get("estimador")):
            if outros:
                return jsonify(varios_mod.ler(
                    registro, outros, pedidos, alinhar=_alinhar(), ler=leitura.em,
                    layout=_layout(),
                    lado=request.args.get("lado", "arquivo"),
                    refere=int(refere) if refere is not None else None,
                    filtro=request.args.get("filtro") in ("1", "sim", "true"),
                    contas=_contas()))
            return jsonify(leitura.em(
                registro, pedidos,
                lado=request.args.get("lado", "arquivo"),
                refere=int(refere) if refere is not None else None,
                # O MESMO arranjo do gráfico: a tabelinha mostra o que está
                # desenhado, nunca outra coisa.
                filtro=request.args.get("filtro") in ("1", "sim", "true"),
                layout=_layout(),
                contas=_contas(),
            ))

    # --- a calculadora (variante 10, 11/11/2026): `plot/calculadora.py` -----
    #
    # As contas são da TELA e viajam no corpo de todo pedido, como os painéis
    # (`_contas()`); o servidor não guarda nenhuma. O que ele guarda é só o
    # MODELO que o usuário pediu para guardar («guardar como modelo»), fora do
    # registro, em `paths.MODELOS_DA_CALCULADORA`.

    @app.post("/api/onda/<sha>/calculadora/conferir")
    def calculadora_conferir(sha: str):
        """Lê a conta que está no visor: o erro, a unidade, a prévia da curva
        no registro inteiro e o valor nos dois cursores.

        Existe para a tela poder dizer tudo isso ENQUANTO o usuário digita, sem
        uma segunda implementação da gramática no navegador."""
        try:
            registro = acervo.ler(sha)
        except FormatError as exc:
            return jsonify(erro=str(exc)), 404
        corpo = request.get_json(silent=True) or {}
        cru = dict(corpo.get("conta") or {})
        cru["id"] = cru.get("id") or "x9999"
        cru["nome"] = cru.get("nome") or "nova"
        if not str(cru.get("expressao") or "").strip():
            return jsonify(vale=False, erro="")
        lida = contas_mod.de_json([cru])
        if not lida:
            return jsonify(vale=False, erro="a conta é longa demais")
        lado = str(corpo.get("lado") or "arquivo")
        # O alcance: em edição, só as contas ANTERIORES a ela; nova, todas.
        todas = _contas()
        ids = [c.id for c in todas]
        antes = todas[:ids.index(lida[0].id)] if lida[0].id in ids else todas
        instantes = [_numero(str(corpo.get(k))) if corpo.get(k) is not None else None
                     for k in ("t1", "t2")]
        with fasor_mod.usando(corpo.get("estimador")):
            resposta = calculadora_mod.previa(
                registro, lida[0], antes + [lida[0]], lado,
                int(_numero(str(corpo.get("colunas") or "")) or 320))
            resposta["valores"] = calculadora_mod.valores(
                registro, antes + [lida[0]], lado, instantes)[-1]
        return jsonify(resposta)

    @app.post("/api/onda/<sha>/calculadora/valores")
    def calculadora_valores(sha: str):
        """Cada conta da tela nos dois cursores — a aba «minhas contas»."""
        try:
            registro = acervo.ler(sha)
        except FormatError as exc:
            return jsonify(erro=str(exc)), 404
        corpo = request.get_json(silent=True) or {}
        instantes = [_numero(str(corpo.get(k))) if corpo.get(k) is not None else None
                     for k in ("t1", "t2")]
        with fasor_mod.usando(corpo.get("estimador")):
            return jsonify(linhas=calculadora_mod.valores(
                registro, _contas(), str(corpo.get("lado") or "arquivo"), instantes))

    @app.get("/api/onda/<sha>/calculadora/modelos")
    def calculadora_modelos(sha: str):
        """Os modelos (cada um dizendo se cabe AQUI), os nomes que a gaveta
        oferece e os ajustes que o relé traz (o k0, com a origem)."""
        try:
            registro = acervo.ler(sha)
        except FormatError as exc:
            return jsonify(erro=str(exc)), 404
        saida = calculadora_mod.modelos(registro, request.args.get("lado", "arquivo"))
        item = acervo.obter(sha)
        ajustes = None
        if item is not None:
            ajustes = ajustes_mod.do_registro(
                acervo.pasta_do_registro(sha),
                item.como_dicionario().get("arquivos") or (),
                [c.name for c in registro.status_channels])
        saida["sugeridos"] = calculadora_mod.ajustes_sugeridos(ajustes)
        saida["nomes"] = calculadora_mod.nomes(registro)
        return jsonify(saida)

    @app.post("/api/onda/<sha>/calculadora/modelos")
    def calculadora_guardar_modelo(sha: str):
        """«guardar como modelo»: a conta generalizada, FORA do registro."""
        corpo = request.get_json(silent=True) or {}
        m = {k: corpo.get(k) for k in ("id", "nome", "categoria", "dominio", "expressao",
                                        "parametros", "descricao")}
        if not m["nome"] or not m["expressao"]:
            return jsonify(erro="falta nome ou expressão"), 400
        m["id"] = m["id"] or calculadora_mod.id_de_modelo(m["nome"], m["expressao"])
        m["categoria"] = m["categoria"] or "Seus modelos"
        m["dominio"] = "fasor" if m["dominio"] == "fasor" else "onda"
        m["parametros"] = [str(x) for x in (m["parametros"] or [])]
        m["descricao"] = m["descricao"] or ""
        return jsonify(modelos=calculadora_mod.guardar_modelo(m))

    @app.delete("/api/onda/<sha>/calculadora/modelos/<ident>")
    def calculadora_apagar_modelo(sha: str, ident: str):
        return jsonify(modelos=calculadora_mod.apagar_modelo(ident))

    @app.post("/api/onda/<sha>/calculadora/generalizar")
    def calculadora_generalizar(sha: str):
        """`[Current IA]` → `[IA]`: o que o modelo guardado vai escrever."""
        try:
            registro = acervo.ler(sha)
        except FormatError as exc:
            return jsonify(erro=str(exc)), 404
        corpo = request.get_json(silent=True) or {}
        return jsonify(calculadora_mod.generalizar(str(corpo.get("expressao") or ""), registro))

    @app.post("/api/acervo/<sha>/nome")
    def renomear(sha: str):
        """O usuário dá ao registro um nome que diga que evento é aquele.

        **O arquivo no disco não muda.** O acervo guarda os arquivos com o nome
        original de propósito — é assim que o leitor acha o `.dat` a partir do
        `.cfg`. O nome novo é uma camada por cima, e quem quiser o arquivo com
        ele exporta. Ver `library/acervo.py`.
        """
        pedido = request.get_json(silent=True) or {}
        try:
            nome = acervo.gravar_apelido(sha, pedido.get("nome", ""))
        except FormatError as exc:
            return jsonify(erro=str(exc)), 404
        item = acervo.obter(sha)
        return jsonify(nome=nome,
                       nome_do_arquivo=item.nome_do_arquivo if item else nome)

    @app.get("/api/acervo/<sha>/exportar")
    def exportar(sha: str):
        """Os arquivos do registro, com o nome escolhido na tela.

        Um registro COMTRADE são dois arquivos (ou três, com o `.hdr`), e o
        leitor acha um a partir do outro pelo **nome base** — então renomear um
        sem renomear os outros entrega um par que não abre. Por isso a
        exportação sai em `.zip` quando há mais de um arquivo: ali os três saem
        com o mesmo nome base, de uma vez, e a extensão de cada um se mantém.
        """
        item = acervo.obter(sha)
        if item is None:
            return jsonify(erro="Este registro não está no acervo."), 404
        pasta = acervo.pasta_do_registro(sha)
        arquivos = [(nome, pasta / nome) for nome in item.arquivos
                    if (pasta / nome).is_file()]
        if not arquivos:
            return jsonify(erro="Os arquivos deste registro sumiram do disco."), 404

        base = item.nome
        if len(arquivos) == 1:
            nome, caminho = arquivos[0]
            return send_from_directory(
                pasta, nome, as_attachment=True,
                download_name=f"{base}{Path(nome).suffix}")

        saco = io.BytesIO()
        with zipfile.ZipFile(saco, "w", zipfile.ZIP_DEFLATED) as zip_:
            for nome, caminho in arquivos:
                zip_.write(caminho, f"{base}{Path(nome).suffix}")
        saco.seek(0)
        return send_file(saco, mimetype="application/zip", as_attachment=True,
                         download_name=f"{base}.zip")

    @app.post("/api/onda/<sha>/vinculos")
    def corrigir_vinculos(sha: str):
        """O usuário corrige a fase que o programa deduziu errado.

        Fica gravado ao lado do registro, e não na tela: quem corrigiu uma fase
        corrigiu para sempre. Ver `library/acervo.py`.
        """
        try:
            escolhas = acervo.gravar_vinculos(sha, request.get_json(silent=True) or {})
        except FormatError as exc:
            return jsonify(erro=str(exc)), 404
        return jsonify(vinculos={str(k): v for k, v in escolhas.items()})

    @app.post("/api/onda/<sha>/relacoes")
    def digitar_relacoes(sha: str):
        """O usuário digita a relação de TC/TP de um grupo ou de um canal.

        `{"grupos": {"I*W": "600/5"}, "canais": {"3": "120"}}`; vazio apaga.
        Fica gravada ao lado do registro e vale em tudo que usa o registro.
        Ver `formats/relacoes.py`.
        """
        try:
            acervo.gravar_relacoes(sha, request.get_json(silent=True) or {})
            registro = acervo.ler(sha)
        except FormatError as exc:
            return jsonify(erro=str(exc)), 404
        return jsonify(relacoes=relacoes_mod.resumo(registro))

    @app.post("/api/onda/<sha>/trincas")
    def corrigir_trincas(sha: str):
        """O usuário diz QUAIS TRÊS CANAIS formam uma trinca.

        Quais três formam um conjunto sai do nome deles, e nome de canal cada
        fabricante escreve como quer. Quando erra, 3I0, I1 e I2 erram junto e
        saem na unidade certa, sem nada na tela denunciando. A correção fica
        gravada ao lado do registro. Ver `library/acervo.py`.
        """
        try:
            escolhas = acervo.gravar_trincas(sha,
                                             request.get_json(silent=True) or {})
        except FormatError as exc:
            return jsonify(erro=str(exc)), 404
        return jsonify(trincas=escolhas)

    @app.post("/api/onda/<sha>/potencia")
    def vincular_potencia(sha: str):
        """O usuário diz QUAL trinca de corrente casa com QUAL de tensão.

        O programa não deduz isso: dois vãos de uma subestação têm nomes
        parecidos, e o par errado produz uma potência na unidade certa, na
        ordem de grandeza certa, e errada — o tipo de erro que não aparece no
        gráfico. Ver `Record.vinculos_de_potencia`.
        """
        try:
            atuais = acervo.gravar_vinculo_de_potencia(
                sha, request.get_json(silent=True) or {})
        except FormatError as exc:
            return jsonify(erro=str(exc)), 404
        return jsonify(vinculos_de_potencia=atuais)

    @app.get("/refino/<sha>")
    def refino(sha: str):
        """A janela «refinar» da seq. negativa de dois terminais, como página
        própria: a oscilografia a abre num quadro por cima de si (o `onda.js`
        tem teclas globais — 1, 2, setas, Esc — que dentro dela têm outro
        sentido). `?com=<sha>` é o IED B."""
        item = acervo.obter(sha)
        outro = acervo.obter(request.args.get("com") or "")
        if item is None or outro is None:
            return render_template("nao-achei.html", versao=version.read()), 404
        # O alinhamento manual GRAVADO do par: a janela abre já nele.
        gravado = acervo.refino_gravado(item.sha, outro.sha)
        return render_template("refino.html", versao=version.read(),
                               a=item.como_dicionario(), b=outro.como_dicionario(),
                               manual="" if gravado is None else repr(gravado))

    @app.post("/api/onda/<sha>/refino-alinhamento")
    def refino_alinhamento(sha: str):
        """Grava (`d` em s) ou apaga (`d` nulo) o alinhamento MANUAL do par
        `sha` × `b`, ao lado do registro (`acervo.gravar_refino`). É dado
        gravado, como a correção de fase: o Ctrl+Z não o desfaz, e quem o
        apaga é voltar ao automático no «refinar»."""
        corpo = request.get_json(silent=True) or {}
        d = corpo.get("d")
        if d is not None and (isinstance(d, bool) or not isinstance(d, (int, float))):
            return jsonify(erro="o deslocamento tem que ser um número (s)"), 400
        try:
            valor = acervo.gravar_refino(sha, str(corpo.get("b") or ""), d)
        except FormatError as exc:
            return jsonify(erro=str(exc)), 404
        except ValueError as exc:
            return jsonify(erro=str(exc)), 400
        return jsonify(d=valor)

    @app.post("/api/onda/<sha>/refino")
    def refino_api(sha: str):
        """Os números da janela «refinar» (`plot/refino.py`, em cima de
        `faultloc/refino.py`). O corpo traz o IED B (`b`), o alinhamento, a
        vista, os cursores, a linha do painel e o que se digitou."""
        corpo = request.get_json(silent=True) or {}
        sha_b = str(corpo.get("b") or "")
        try:
            reg_a, reg_b = acervo.ler(sha), acervo.ler(sha_b)
        except FormatError as exc:
            return jsonify(erro=str(exc)), 404
        nome_a = _nome_do_terminal(sha, reg_a, acervo.apelido(sha))
        nome_b = _nome_do_terminal(sha_b, reg_b, acervo.apelido(sha_b))
        return jsonify(refino_mod.montar(reg_a, nome_a, reg_b, nome_b, corpo))

    @app.post("/api/onda/<sha>/localizar")
    def localizar_falta(sha: str):
        """O painel «localizar falta»: a LDL no tempo do IED A e do IED B.

        O corpo traz o que a tela sabe: os outros registros e o alinhamento
        (como em toda rota da aba), o cursor 1 no eixo da aba — que pode faltar:
        aí vale o meio do platô —, a fonte da linha pedida, o que se digitou e
        quantas colunas de pixel tem o gráfico. A conta é toda de
        `faultloc/ldl.py`; aqui só se junta o que ela precisa.
        """
        try:
            registro = acervo.ler(sha)
        except FormatError as exc:
            return jsonify(erro=str(exc)), 404
        corpo = request.get_json(silent=True) or {}
        t = _numero(str(corpo.get("t"))) if corpo.get("t") is not None else None
        outros = _outros_registros(sha)
        modo = _alinhar()

        nome_a = _nome_do_terminal(sha, registro, acervo.apelido(sha))
        terminais = [{"letra": "A", "nome": nome_a, "registro": registro, "sha": sha, "d": 0.0}]
        # O deslocamento MANUAL escolhido no «refinar» (decidido em 11/11/2026),
        # GRAVADO ao lado do registro: vale só para o B do par. Um `refino`
        # no corpo vence o gravado (a tela de hoje não o manda mais).
        pedido_refino = corpo.get("refino") if isinstance(corpo.get("refino"), dict) else None
        alinhado_a_mao = None
        for letra, (outro, apelido, sha_outro) in zip("B", outros, strict=False):
            desl = alinhamento_mod.deslocamento(registro, outro, modo)
            d = desl["d"]
            if pedido_refino is not None and pedido_refino.get("b") == sha_outro:
                pedido_d = pedido_refino.get("d")
            else:
                pedido_d = acervo.refino_gravado(sha, sha_outro)
            if pedido_d is not None:
                escolha = refino_conta.deslocamento_do_painel(outro, d, pedido_d)
                if escolha["manual"]:
                    d = escolha["d"]
                    alinhado_a_mao = {
                        "d": d, "auto": escolha["auto"],
                        "gravado": pedido_refino is None or pedido_refino.get("b") != sha_outro,
                        "txt": {"d": refino_mod.txt(d * 1000.0, 2),
                                "auto": refino_mod.txt(escolha["auto"] * 1000.0, 2)}}
            terminais.append({"letra": letra,
                              "nome": _nome_do_terminal(sha_outro, outro, apelido),
                              "registro": outro, "sha": sha_outro, "d": d,
                              "alinhamento": desl})

        def ajustes_de(term) -> dict:
            item = acervo.obter(term["sha"])
            if item is None:
                return {}
            lidos = ajustes_mod.do_registro(
                acervo.pasta_do_registro(term["sha"]),
                item.como_dicionario().get("arquivos") or (),
                [c.name for c in term["registro"].status_channels])
            return impedancia_mod.como_dicionario(lidos.get("ajustes"))

        fontes: dict = {}
        base = base_mod.ativa()
        tem_base = base is not None and base.existe and base_mod.usa("linhas")
        # A linha ESCOLHIDA pelo nome (janela «parâmetros») vence a dedução
        # pelos terminais — e vale com um terminal só, que é justamente o caso
        # em que a dedução não roda.
        # Nome E terminais: a base repete o nome nos trechos de uma derivação.
        pedida_base = corpo.get("linha_base") or {}
        if isinstance(pedida_base, str):
            pedida_base = {"nome": pedida_base}
        escolhida = str(pedida_base.get("nome") or "").strip()

        def fonte_da_entrada(pedido: dict, escolha: bool) -> dict:
            """Uma entrada da base (`linhas.entradas`) como fonte da conta: o
            trecho, o circuito de três terminais (caminho A–B) ou os trechos
            somados."""
            nome = str(pedido.get("nome") or "").strip()
            tipo = pedido.get("tipo") or "linha"
            nao_esta = {"ok": False, "motivo": f"a linha «{nome}» não está na base"}
            if tipo == "3t":
                c = tres_terminais_mod.de_nome(base, nome)
                fonte = tres_terminais_mod.caminho_de_circuito(c) if c else nao_esta
            elif tipo == "trechos":
                trechos = tres_terminais_mod.trechos_de(base, nome)
                registro_3t = tres_terminais_mod.de_nome(base, nome)
                conferido = bool(registro_3t and registro_3t.situacao == "sem-tap")
                fonte = (tres_terminais_mod.caminho_de_trechos(trechos, conferido)
                         if len(trechos) > 1 else nao_esta)
            else:
                achada = linhas_mod.escolhida(base, nome, pedido.get("terminal_s"),
                                              pedido.get("terminal_r"))
                fonte = (dict(seqneg_mod.linha_da_base(achada),
                              terminais=[achada.terminal_s, achada.terminal_r])
                         if achada else nao_esta)
            if fonte.get("ok"):
                fonte = dict(fonte, escolhida=escolha)
            return fonte

        if escolhida and tem_base:
            fontes["base"] = fonte_da_entrada(pedida_base, True)
        elif tem_base:
            # A linha é SEMPRE escolhida pelo usuário (decidido em 10/11/2026).
            # Havia uma casagem automática pelo nome da estação gravado nos
            # registros: ela errava com acento («GUIMARÃES» × «GUIMARAES») e
            # com nome dentro de nome («SINOP» em «SINOP CENTRO») — e, quando
            # acertava o texto e errava a linha, o km saía da linha errada com
            # cara de certo. Escolher custa um clique; o palpite não se confere.
            fontes["base"] = {"ok": False,
                              "motivo": "escolha a linha da base em «parâmetros»"}
        else:
            fontes["base"] = {"ok": False, "motivo": "sem base de dados ativa"}
        ajustes_por = {term["letra"]: ajustes_de(term) for term in terminais[:2]}
        for term in terminais[:2]:
            ajustes = ajustes_por[term["letra"]]
            fontes[term["letra"]] = seqneg_mod.linha_dos_ajustes(
                ajustes, impedancia_mod.relacao_rtp_rtc(term["registro"], ajustes))
        fontes.setdefault("B", {"ok": False, "motivo": "a aba não tem IED B"})
        # O secundário do que se digita é o do relé A: dos ajustes dele
        # primeiro (num `.CEV` a relação só está ali), do cabeçalho depois.
        rtp_rtc_a = impedancia_mod.relacao_rtp_rtc(registro, ajustes_por["A"])
        fontes["manual"] = seqneg_mod.linha_digitada(corpo.get("manual"), rtp_rtc_a)

        pedida = str(corpo.get("fonte") or "auto")
        usada = None
        if pedida in seqneg_mod.FONTES and fontes.get(pedida, {}).get("ok"):
            usada = pedida
        elif pedida == "auto":
            usada = next((f for f in seqneg_mod.FONTES if fontes.get(f, {}).get("ok")), None)
        linha = ldl_mod.linha_com_z0(fontes.get(usada)) if usada else None
        # O Z0 pode morar noutra fonte (a base sem Z0, os ajustes com): só o
        # laço de terra o usa, e a tela diz de onde ele veio.
        z0_de = usada if linha and linha.get("r0") is not None else None
        if linha and z0_de is None:
            for f in seqneg_mod.FONTES:
                info = fontes.get(f) or {}
                if info.get("ok") and info.get("r0") is not None:
                    linha.update(r0=info["r0"], x0=info["x0"])
                    z0_de = f
                    break

        def colunas_de(nome: str) -> int:
            # Pixel de VERDADE (a tela já multiplicou pelo devicePixelRatio).
            try:
                return max(100, min(6000, int(corpo.get(nome) or 800)))
            except (TypeError, ValueError):
                return 800
        colunas, colunas_ondas = colunas_de("colunas"), colunas_de("colunas_ondas")
        estimador = corpo.get("estimador")
        b = terminais[1] if len(terminais) > 1 else None
        chave = (sha, b and b["sha"], _versao_do_registro(sha),
                 b and _versao_do_registro(b["sha"]),
                 modo, b and round(b["d"], 9), repr(sorted((linha or {}).items())),
                 str(estimador), colunas, colunas_ondas)
        with fasor_mod.usando(estimador):
            pacote = ldl_mod.montar(registro, b and b["registro"], b["d"] if b else 0.0,
                                    linha, t, colunas, chave, colunas_ondas)
        pacote.update(fontes=fontes, fonte=usada, pedida=pedida, z0_de=z0_de,
                      linha=linha, nomes={x["letra"]: x["nome"] for x in terminais},
                      alinhamento=b["alinhamento"] if b else None,
                      alinhado_a_mao=alinhado_a_mao,
                      # O aviso da derivação (TAP) ou dos trechos sem TAP
                      # confirmado: a tela o mostra enquanto essa linha vale.
                      aviso_linha=(fontes.get(usada) or {}).get("aviso", "") if usada else "")
        # A janela «parâmetros» (as colunas Relé · Base · Digitado, nas quatro
        # vistas, e quem difere da coluna em uso) e o selo «⚠ relé ≠ base» do
        # cabeçalho do painel. Conta em `faultloc/parametros.py`. O k0 que o
        # relé GRAVA (k0M1/k0A1 na SEL) vence o calculado na coluna dele.
        k0s = {}
        for letra, ajustes in ajustes_por.items():
            k0_lido = impedancia_mod.k0_de(ajustes)
            if k0_lido is not None and k0_lido[1] == "lido":
                k0s[letra] = k0_lido[0]
        pacote.update(
            parametros=parametros_mod.montar(fontes, usada, [x["letra"] for x in terminais[:2]],
                                             rtp_rtc_a, corpo.get("manual"), k0s),
            n_ieds=len(terminais),
            # O rodapé diz «a partir de SE X» só quando o arquivo (ou o apelido)
            # diz a estação; sem ela, «a partir deste terminal».
            estacao_conhecida={x["letra"]: bool((acervo.apelido(x["sha"]) or "").strip()
                                                or (x["registro"].station or "").strip())
                               for x in terminais},
            sobre_o_resultado=ldl_mod.sobre_o_resultado())
        if corpo.get("painel"):
            # O painel «localizador de faltas» lê os DOIS cursores e o número
            # do relé. O cursor 2 é a mesma conta guardada, lida noutro
            # instante; sem cursor na tela não se lê nada — o meio do platô
            # que a tela de localizar usa seria um número que ninguém pediu.
            t2 = _numero(str(corpo.get("t2"))) if corpo.get("t2") is not None else None
            with fasor_mod.usando(estimador):
                cursor2 = (ldl_mod.montar(registro, b and b["registro"], b["d"] if b else 0.0,
                                          linha, t2, colunas, chave, colunas_ondas)["cursor"]
                           if t2 is not None else None)
            item = acervo.obter(sha)
            lido = rele_mod.do_registro(
                acervo.pasta_do_registro(sha),
                (item.como_dicionario().get("arquivos") or ()) if item else ())
            pacote["painel"] = localizador_mod.montar(
                pacote, pacote.get("cursor") if t is not None else None, cursor2,
                lido, _numero(str(corpo.get("rele_manual")))
                if corpo.get("rele_manual") is not None else None)
        return jsonify(pacote)

    @app.get("/api/onda/<sha>/linhas-da-base")
    def linhas_da_base(sha: str):
        """A busca da janela «parâmetros» do localizador (`linhas.buscar`)."""
        base = base_mod.ativa()
        if base is None or not base.existe or not base_mod.usa("linhas"):
            return jsonify(base=False, linhas=[], total=0)
        try:
            registro = acervo.ler(sha)
        except FormatError as exc:
            return jsonify(erro=str(exc)), 404
        return jsonify(base=True, nome_da_base=base.nome,
                       total=len(linhas_mod.entradas(base)), estacao=registro.station,
                       linhas=linhas_mod.buscar(base, request.args.get("q") or ""),
                       resumo_3t=tres_terminais_mod.resumo(base))

    @app.post("/api/base/linhas")
    def guardar_linha():
        """Guarda na base a linha digitada na localização de falta."""
        base = base_mod.ativa()
        if base is None or not base.existe:
            return jsonify(erro="Não há base de dados ativa."), 400
        corpo = request.get_json(silent=True) or {}

        def opcional(chave: str) -> float | None:
            try:
                return float(corpo[chave]) if corpo.get(chave) is not None else None
            except (TypeError, ValueError):
                return None
        try:
            r0, x0 = opcional("r0"), opcional("x0")
            if r0 is None or x0 is None:
                r0 = x0 = None
            linha = linhas_mod.Linha(
                str(corpo.get("nome") or "").strip(),
                str(corpo.get("terminal_s") or "").strip(),
                str(corpo.get("terminal_r") or "").strip(),
                float(corpo["r"]), float(corpo["x"]), float(corpo["km"]), r0, x0,
                opcional("b1"), opcional("b0"))
        except (KeyError, TypeError, ValueError):
            return jsonify(erro="faltam R, X ou o comprimento"), 400
        if not linha.nome or linha.comprimento_km <= 0:
            return jsonify(erro="dê um nome à linha"), 400
        linhas_mod.gravar(base, linha)
        return jsonify(linha=linha.como_dicionario())

    @app.post("/api/base/linhas-3t")
    def linhas_de_tres_terminais():
        """O que se edita das linhas de três terminais, na janela «parâmetros».

        `{acao: "papeis", nome, papeis: [p1, p2, p3]}` grava qual perna é A, B
        e TAP; `{acao: "cadastrar", nome, ponto, tap, tap_km}` marca à mão o
        TAP que o OnLiner não deixou reconhecer; `{acao: "remover", nome}` tira
        um cadastro feito à mão. Tudo vai para o `linhas-3t.csv`; o `linhas.csv`
        não é tocado.
        """
        base = base_mod.ativa()
        if base is None or not base.existe:
            return jsonify(erro="Não há base de dados ativa."), 400
        corpo = request.get_json(silent=True) or {}
        nome, acao = str(corpo.get("nome") or ""), corpo.get("acao")
        try:
            if acao == "papeis":
                tres_terminais_mod.marcar(base, nome, list(corpo.get("papeis") or []))
            elif acao == "cadastrar":
                bruto = corpo.get("tap_km")
                km = _numero(str(bruto)) if bruto not in (None, "") else None
                tres_terminais_mod.cadastrar(base, nome, int(corpo.get("ponto") or 0),
                                             str(corpo.get("tap") or ""), km)
            elif acao == "conferir":
                tres_terminais_mod.conferir_trechos(
                    base, nome, str(corpo.get("situacao") or ""), str(corpo.get("nota") or ""))
            elif acao == "remover":
                if not tres_terminais_mod.remover_manual(base, nome):
                    return jsonify(erro="só se remove o que foi cadastrado à mão"), 400
            else:
                return jsonify(erro="ação desconhecida"), 400
        except (TypeError, ValueError) as exc:
            return jsonify(erro=str(exc)), 400
        return jsonify(ok=True, resumo=tres_terminais_mod.resumo(base))

    @app.delete("/api/aguardando")
    def esquecer_aguardando():
        return jsonify(removidos=acervo.esquecer_aguardando())

    @app.delete("/api/acervo/<sha>")
    def remover_do_acervo(sha: str):
        if not acervo.remover(sha):
            return jsonify(erro="Este registro nao esta' no acervo."), 404
        return jsonify(removido=sha)

    # -----------------------------------------------------------------------
    # A base de dados
    # -----------------------------------------------------------------------

    @app.get("/base")
    def base_de_dados():
        """A tela da base: as três gavetas, ou o convite a criar a primeira.

        A MESMA tela serve os dois momentos. Duas páginas — uma de boas-vindas
        e outra de gerência — seriam duas para manter e, pior, a pessoa que
        acabou de criar a base cairia numa tela que nunca viu.
        """
        return render_template("base.html", versao=version.read(),
                               base=base_mod.estado())

    @app.get("/api/base")
    def estado_da_base():
        return jsonify(base_mod.estado())

    @app.get("/api/base/pastas")
    def pastas_para_escolher():
        """Lista pastas para a tela deixar o usuário escolher ONDE.

        O navegador não entrega caminho absoluto de pasta — é proteção dele, e
        é certa. Como o OscLab roda na máquina do usuário e só em 127.0.0.1,
        quem lista é o servidor: a tela mostra o que ele já veria no Explorer.
        """
        return jsonify(navegar_mod.listar(request.args.get("onde") or None))

    @app.post("/api/base/pasta-nativa")
    def pasta_pelo_sistema():
        """Abre a janela de «salvar em…» do próprio sistema.

        É a janela que a pessoa já sabe usar — barra de endereço, favoritos,
        «nova pasta». Quando ela não abre (sem `tkinter`, sem ambiente
        gráfico), a resposta diz `disponivel: false` e a tela cai no navegador
        desenhado na página, que faz o mesmo trabalho.
        """
        corpo = request.get_json(silent=True) or {}
        return jsonify(navegar_mod.nativo(
            corpo.get("inicial") or "",
            "Escolha a pasta onde o OscLab vai criar a base",
        ))

    @app.post("/api/base/criar")
    def criar_a_base():
        corpo = request.get_json(silent=True) or {}
        try:
            base_mod.criar(corpo.get("nome") or "", corpo.get("onde") or None)
        except base_mod.ErroDaBase as erro:
            return jsonify(erro=str(erro)), 400
        return jsonify(base_mod.estado())

    @app.post("/api/base/escolher")
    def escolher_a_base():
        corpo = request.get_json(silent=True) or {}
        try:
            base_mod.escolher(corpo.get("pasta") or "")
        except base_mod.ErroDaBase as erro:
            return jsonify(erro=str(erro)), 400
        return jsonify(base_mod.estado())

    @app.post("/api/base/gaveta")
    def ligar_a_gaveta():
        corpo = request.get_json(silent=True) or {}
        try:
            base_mod.habilitar(corpo.get("gaveta") or "",
                               bool(corpo.get("ligada")))
        except base_mod.ErroDaBase as erro:
            return jsonify(erro=str(erro)), 400
        return jsonify(base_mod.estado())

    @app.get("/api/base/dicionario")
    def listar_o_dicionario():
        base = base_mod.ativa()
        if base is None or not base.existe:
            return jsonify(verbetes=[], categorias=list(digitais_mod.CATEGORIAS))
        return jsonify(
            verbetes=[v.como_dicionario() for v in digitais_mod.listar(base)],
            categorias=list(digitais_mod.CATEGORIAS),
        )

    @app.post("/api/base/dicionario")
    def anotar_no_dicionario():
        base = base_mod.ativa()
        if base is None or not base.existe:
            return jsonify(erro="Não há base de dados ativa."), 400
        corpo = request.get_json(silent=True) or {}
        campos = {c: corpo.get(c) for c in digitais_mod.EDITAVEIS if c in corpo}
        # Quem escreveu pela tela é a fonte, a menos que a tela diga outra:
        # uma dedução corrigida à mão deixa de ser dedução. APAGAR também é
        # escrever — senão a próxima importação da dedução traria de volta o
        # valor que o usuário tirou.
        if "fonte" not in corpo and campos:
            campos["fonte"] = "digitado"
        try:
            verbete = digitais_mod.anotar(
                base,
                corpo.get("fabricante") or "",
                corpo.get("modelo") or "",
                corpo.get("sinal") or "",
                instalacao=corpo.get("instalacao") or "",
                **campos,
            )
        except ValueError as erro:
            return jsonify(erro=str(erro)), 400
        return jsonify(verbete=verbete.como_dicionario(),
                       itens=len(digitais_mod.listar(base)))

    @app.delete("/api/base/dicionario")
    def apagar_do_dicionario():
        base = base_mod.ativa()
        if base is None or not base.existe:
            return jsonify(erro="Não há base de dados ativa."), 400
        corpo = request.get_json(silent=True) or {}
        apagou = digitais_mod.remover(base, corpo.get("fabricante") or "",
                                      corpo.get("modelo") or "", corpo.get("sinal") or "",
                                      corpo.get("instalacao") or "")
        if not apagou:
            return jsonify(erro="Este verbete não está no dicionário."), 404
        return jsonify(apagado=True, itens=len(digitais_mod.listar(base)))

    @app.get("/api/base/dicionario/exportar")
    def exportar_o_dicionario():
        """O CSV inteiro, para editar no Excel e importar de volta."""
        base = base_mod.ativa()
        if base is None or not base.existe:
            return jsonify(erro="Não há base de dados ativa."), 400
        texto = "﻿" + digitais_mod.como_csv(digitais_mod.listar(base))
        return Response(texto.encode("utf-8"), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=dicionario.csv"})

    @app.post("/api/base/dicionario/importar")
    def importar_para_o_dicionario():
        base = base_mod.ativa()
        if base is None or not base.existe:
            return jsonify(erro="Não há base de dados ativa."), 400
        enviado = request.files.get("arquivo")
        if enviado is not None and enviado.filename:
            # `utf-8-sig` porque o arquivo quase sempre volta do Excel, e o
            # Excel grava o BOM. Com `utf-8` puro, o primeiro cabeçalho vem
            # com três bytes invisíveis grudados e a coluna não casa.
            texto = enviado.read().decode("utf-8-sig", errors="replace")
        else:
            texto = (request.get_json(silent=True) or {}).get("texto") or ""
        if not texto.strip():
            return jsonify(erro="Nada para importar."), 400
        return jsonify(digitais_mod.importar(base, texto))

    @app.get("/api/logica/<sha>")
    def logica_do_registro(sha: str):
        """Os ajustes e as equações que vieram DENTRO do arquivo.

        Não passa pelo dicionário: este painel é seco. O que está na tela é o
        que está no arquivo — decisão dele, 19/10/2026.
        """
        item = acervo.obter(sha)
        if item is None:
            return jsonify(tem=False, motivo="registro não está no acervo",
                           ajustes=[], logica=[]), 404
        dados = item.como_dicionario()
        # Os nomes dos digitais DESTE registro desempatam a equação de um
        # termo só: `OUT101 := TRIP` só é lógica porque TRIP é um canal daqui.
        nomes = []
        try:
            registro = acervo.ler(sha)
            nomes = [c.name for c in registro.status_channels]
        except FormatError:
            pass
        saida = ajustes_mod.do_registro(
            acervo.pasta_do_registro(sha), dados.get("arquivos") or (), nomes)
        saida["equipamento"] = dados.get("equipamento") or ""
        return jsonify(saida)

    @app.route("/api/eventos/<sha>", methods=["GET", "POST"])
    def eventos_do_registro(sha: str):
        """A lista de eventos do relé, de cada registro da aba, no tempo da aba.

        O corpo é o mesmo da janela (os outros registros e o alinhamento): o
        deslocamento de cada um tem de ser o MESMO que desloca as ondas. Ver
        `plot/eventos.py`.
        """
        item = acervo.obter(sha)
        if item is None:
            return jsonify(tem=False, listas=[]), 404
        try:
            base = acervo.ler(sha)
        except FormatError:
            base = None
        fontes = [("A", sha, acervo.apelido(sha), base, 0.0)]
        for letra, (outro, apelido, sha_outro) in zip("BC", _outros_registros(sha),
                                                       strict=False):
            d = (alinhamento_mod.deslocamento(base, outro, _alinhar())["d"]
                 if base is not None else 0.0)
            fontes.append((letra, sha_outro, apelido, outro, d))
        # Cada registro dá a lista que veio com ele (o `.hdr` da Schneider) MAIS
        # as que a tela importou pelo «+ arquivo» da janela. As importadas NÃO
        # são gravadas (decisão de 11/11/2026): a tela as guarda enquanto a
        # aba estiver aberta e as manda aqui, no corpo, com as escolhas (fuso,
        # relé, ordem da data). A conta do tempo é toda daqui
        # (`plot/eventos.pacote`); a tela só junta e ordena.
        corpo = request.get_json(silent=True) or {}
        importados = corpo.get("importados") if isinstance(corpo, dict) else None
        importados = [x for x in (importados or []) if isinstance(x, dict)]
        listas = []
        for letra, s, apelido, registro, d in fontes:
            dados = (acervo.obter(s) or item).como_dicionario()
            textos = (registro.station if registro is not None else "",
                      registro.device_id if registro is not None else "",
                      apelido or "", *(dados.get("arquivos") or ()))
            achada = eventos_mod.do_registro(acervo.pasta_do_registro(s),
                                             dados.get("arquivos") or ())
            deste = [x for x in importados if x.get("sha") == s]
            if achada is not None or not deste:
                listas.append(eventos_plot.pacote(letra, s, apelido, achada, registro, d,
                                                  textos_do_registro=textos))
            referencia = (registro.start_time.date()
                          if registro is not None and registro.start_time else None)
            for x in deste:
                escolhas = x.get("escolhas") if isinstance(x.get("escolhas"), dict) else {}
                nome = str(x.get("nome") or "eventos.txt")
                ordem = str(escolhas.get("ordem") or "")
                lida = eventos_mod.ler_texto_de_eventos(str(x.get("texto") or ""), nome,
                                                        referencia, ordem)
                listas.append(eventos_plot.pacote(letra, s, apelido, lida, registro, d,
                                                  escolhas, importado=True,
                                                  textos_do_registro=textos))
        return jsonify(tem=any(x["tem"] for x in listas), listas=listas)

    @app.post("/api/eventos/<sha>/trilha")
    def trilha_dos_eventos(sha: str):
        """A DISTRIBUIÇÃO dos eventos no tempo, para a trilha da janela.

        O corpo é o mesmo da lista (registros da aba e importadas) mais
        `largura` (px da trilha) e `escondidos` (os relés desligados nos
        chips). A contagem é conta, por isso mora aqui; a tela só pinta. Ver
        `plot/eventos.distribuicao`.
        """
        resposta = eventos_do_registro(sha)
        if isinstance(resposta, tuple):
            return resposta
        pacotes = resposta.get_json().get("listas", [])
        corpo = request.get_json(silent=True) or {}
        largura = float(corpo.get("largura") or 600)
        escondidos = [str(x) for x in (corpo.get("escondidos") or [])]
        return jsonify(geral=eventos_plot.distribuicao(pacotes, largura, escondidos))

    @app.get("/api/dicionario/<sha>")
    def dicionario_do_registro(sha: str):
        """O que o dicionário sabe sobre o relé DESTE registro.

        A tela da onda não precisa saber de degraus nem de fabricante: ela
        pergunta pelo registro e recebe a lista já resolvida, um verbete por
        sinal, com a origem escrita por extenso.
        """
        item = acervo.obter(sha)
        equipamento = (item.como_dicionario().get("equipamento") or "") if item else ""
        if base_mod.da_gaveta(base_mod.PASTA_DO_DICIONARIO).futura:
            return jsonify(tem=False, futura=True,
                           motivo="o dicionário é uma implementação futura",
                           equipamento=equipamento, verbetes=[])
        base = base_mod.ativa()
        ligada = base_mod.usa(base_mod.PASTA_DO_DICIONARIO)
        if base is None or not base.existe or not ligada:
            return jsonify(tem=False, motivo=(
                "nenhuma base de dados ativa" if base is None or not base.existe
                else "o dicionário está desligado nesta base"),
                equipamento=equipamento, verbetes=[])
        textos = _textos_da_instalacao(sha, item)
        fabricante, modelo = digitais_mod.identificar(equipamento, *textos)
        verbetes = digitais_mod.aplicaveis(base, equipamento, textos)
        return jsonify(
            tem=bool(verbetes),
            motivo="" if verbetes else "o dicionário está vazio",
            equipamento=equipamento,
            fabricante=fabricante,
            modelo=modelo,
            verbetes=verbetes,
        )

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
            base=(base_mod.estado()["base"] or {}).get("pasta", ""),
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


def _ajustes_do_registro(sha: str, registro, arranjo) -> dict | None:
    """Os ajustes do relé, SÓ quando algum painel do arranjo precisa deles.

    Quem precisa é o plano de impedância, que desenha as zonas, e o
    diferencial, que lê os ajustes do 87T. Para todo o
    resto da tela isto seria um arquivo aberto a cada arrasto, sem nenhum
    efeito no que aparece.
    """
    if not arranjo or not any(p.tipo in (paineis.IMPEDANCIA, paineis.DIFERENCIAL,
                                         paineis.ALFA)
                              for p in arranjo):
        return None
    item = acervo.obter(sha)
    if item is None:
        return None
    nomes = [c.name for c in registro.status_channels]
    return ajustes_mod.do_registro(
        acervo.pasta_do_registro(sha),
        (item.como_dicionario().get("arquivos") or ()), nomes)


def _layout() -> list | None:
    """O arranjo de painéis que a tela mandou no corpo, ou `None`.

    Vem no CORPO e não na URL porque é uma estrutura: painéis, com listas de
    sinais dentro. Espremer isso numa query string daria um formato próprio
    para escrever e para ler — dois lugares a mais para errar — e estouraria o
    limite de tamanho num registro com muitos sinais na tela.

    Sem corpo (um GET simples), devolve `None`, e o servidor monta o arranjo
    padrão. É o que a primeira carga faz, e o que mantém a URL de uma janela
    abrível à mão.
    """
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        return None
    return paineis.de_json(corpo.get("paineis"))


def _outros_registros(sha: str) -> list:
    """Os OUTROS registros da aba, que a tela mandou no corpo, já abertos.

    `[(registro, apelido, sha)]`, na ordem B, C. Vêm no corpo junto com o
    arranjo, pela mesma razão: são estrutura da TELA, e o servidor não guarda
    aba nenhuma. Cada um é lido do acervo neste pedido e solto no fim dele —
    nada de cache: o servidor já caiu por falta de memória no Windows.
    Registro que sumiu do acervo é pulado, em vez de derrubar a tela.
    """
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict) or not isinstance(corpo.get("registros"), list):
        return []
    saida = []
    for item in corpo["registros"][:varios_mod.MAXIMO_DE_REGISTROS - 1]:
        outro = str((item or {}).get("sha") or "") if isinstance(item, dict) else ""
        if not outro or outro == sha:
            continue
        try:
            saida.append((acervo.ler(outro), acervo.apelido(outro), outro))
        except FormatError:
            continue
    return saida


def _versao_do_registro(sha: str) -> tuple:
    """A impressão da pasta do registro: cada arquivo, com hora e tamanho.

    Corrigir uma fase ou uma trinca grava um arquivo ao lado do registro; com
    isto na chave, a conta guardada da localização não sobrevive à correção.
    Não basta a hora MAIS NOVA da pasta: limpar a correção APAGA o
    `vinculos.json`, e se havia um arquivo mais novo (o apelido) o máximo não
    mudava — a localização continuava com a fase antiga.
    """
    try:
        pasta = acervo.pasta_do_registro(sha)
        return tuple(sorted((p.name, p.stat().st_mtime_ns, p.stat().st_size)
                            for p in Path(pasta).iterdir()))
    except (OSError, TypeError):
        return ()


def _textos_da_instalacao(sha: str, item) -> tuple[str, ...]:
    """O que o registro diz de si — estação, equipamento, apelido, nomes dos
    arquivos —, para casar o verbete de UMA instalação do dicionário.

    O nome do arquivo entra porque é muitas vezes o único lugar com o vão: a
    SEL batiza o COMTRADE com o `RID` (`RME_320_TR_TR01_UPC2`), e a estação
    gravada no cabeçalho diz só a SE.
    """
    if item is None:
        return ()
    dados = item.como_dicionario()
    # O `modelo` é o que o acervo DEDUZIU, com prova (o «SIPROTEC 5 · nº de
    # série» sai de lá): é ele que deixa o dicionário reconhecer a família.
    textos = [dados.get("estacao") or "", dados.get("equipamento") or "",
              dados.get("modelo") or "", dados.get("nome") or "", acervo.apelido(sha)]
    textos += [str(a) for a in (dados.get("arquivos") or ())]
    textos += list(_identidade_nos_ajustes(sha, tuple(dados.get("arquivos") or ())))
    return tuple(t for t in textos if t)


@functools.lru_cache(maxsize=256)
def _identidade_nos_ajustes(sha: str, arquivos: tuple[str, ...]) -> tuple[str, ...]:
    """RID, TID e SID dos ajustes que vêm dentro do registro.

    O `.CEV` da SEL grava a estação VAZIA: quem diz qual relé é são o RID e o
    TID. Guardado por `sha` — o acervo é endereçado por conteúdo, então o que
    está naquela pasta não muda —, porque ler e separar o bloco de ajustes de
    um `.CEV` de vários MB a cada abertura da tela é custo à toa.
    """
    try:
        lidos = ajustes_mod.do_registro(acervo.pasta_do_registro(sha), arquivos, ())
    except (OSError, ValueError):
        return ()
    pares = list(lidos.get("ajustes") or []) + list(lidos.get("logica") or [])
    return tuple(str(par[1]) for par in pares
                 if len(par) > 1 and str(par[0]).upper() in ("RID", "TID", "SID"))


def _nome_do_terminal(sha: str, registro, apelido: str) -> str:
    """O nome que a localização dá a um IED: apelido, estação ou arquivo."""
    if apelido or registro.station:
        return apelido or registro.station
    item = acervo.obter(sha)
    return item.nome if item is not None else sha[:8]


def _alinhar() -> str:
    """Como os registros da aba se alinham no tempo. Padrão: início da falta."""
    corpo = request.get_json(silent=True)
    modo = str((corpo or {}).get("alinhar") or "") if isinstance(corpo, dict) else ""
    from osclab.plot import alinhamento
    return modo if modo in alinhamento.MODOS else alinhamento.MODOS[0]


def _contas() -> list:
    """As contas do usuário que a tela mandou no corpo.

    Vêm junto com o arranjo e pelo mesmo motivo: são estrutura, e são da TELA.
    O servidor não guarda nenhuma — cada pedido traz as que valem agora, como
    já acontece com os painéis. Ver `plot/contas.py`.
    """
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        return []
    return contas_mod.de_json(corpo.get("contas"))


def _inteiros(texto: str | None) -> list[int] | None:
    """`3,17,42` — quais digitais a tela quer ver. `None` = ainda não escolheu.

    Lista vazia é escolha legítima (o usuário tirou todos da tela) e precisa se
    distinguir de "não mandou nada", que é quando o servidor decide.
    """
    if texto is None:
        return None
    return [int(p) for p in texto.split(",") if p.strip().lstrip("-").isdigit()]


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
