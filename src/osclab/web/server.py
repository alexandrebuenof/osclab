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

import io
import zipfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory

from osclab import paths, version
from osclab.analysis import falta as falta_mod
from osclab.basedados import digitais as digitais_mod
from osclab.basedados import linhas as linhas_mod
from osclab.basedados import navegar as navegar_mod
from osclab.basedados import pasta as base_mod
from osclab.dsp import fasor as fasor_mod
from osclab.faultloc import ldl as ldl_mod
from osclab.faultloc import seqneg as seqneg_mod
from osclab.formats import ajustes as ajustes_mod
from osclab.formats import registry
from osclab.formats.base import FormatError
from osclab.library import acervo
from osclab.plot import alinhamento as alinhamento_mod
from osclab.plot import contas as contas_mod
from osclab.plot import impedancia as impedancia_mod
from osclab.plot import janela, leitura, navegacao, paineis, unidades
from osclab.plot import varios as varios_mod

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
            # Quem compara é o servidor, não o Jinja: `AB` × `AB T` precisa de
            # normalização, e normalizar sigla dentro de template é o tipo de
            # regra que ninguém acha depois. Ver `analysis/falta.mesmo_tipo`.
            conflita_a_falta=not falta_mod.rele_concorda(
                dados.get("falta_tipo", ""), dados.get("falta_inicial", ""),
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

    @app.post("/api/onda/<sha>/conta")
    def conferir_conta(sha: str):
        """Lê uma expressão da calculadora e diz se ela vale, e em que unidade.

        Existe para a tela poder dizer o erro ENQUANTO o usuário digita, sem
        uma segunda implementação da gramática no navegador. Uma gramática em
        dois lugares é duas gramáticas, e elas divergem no primeiro caso
        esquisito — que numa calculadora de laudo é o caso que importa.
        """
        try:
            registro = acervo.ler(sha)
        except FormatError as exc:
            return jsonify(erro=str(exc)), 404
        pedido = request.get_json(silent=True) or {}
        lado = str(pedido.get("lado") or "arquivo")
        escalas = unidades.por_unidade(registro, lado)
        # As contas JÁ criadas são o alcance desta: ver `plot/contas.analisar`.
        # Em edição, a própria conta e as posteriores ficam de fora — senão a
        # tela diria que vale uma referência que o catálogo vai recusar.
        editando = str(pedido.get("editando") or "")
        antes = []
        for conta in _contas():
            if conta.id == editando:
                break
            antes.append(conta)
        analise = contas_mod.analisar(str(pedido.get("expressao") or ""),
                                      registro, escalas, tuple(antes))
        nomes = list(analise.fontes)
        return jsonify(
            vale=analise.vale,
            unidade=escalas.get(analise.unidade_escrita,
                                (1.0, analise.unidade_escrita))[1],
            alternado=analise.alternado,
            canais=nomes,
            erro=analise.erro,
            # Se sobra 60 Hz nela. A tela usa para avisar que, no modo
            # tradicional, esta conta não teria coluna nenhuma — e para
            # trocar de modo ao criar. Ver `contas.tem_60hz`.
            tem_60hz=bool(contas_mod.tem_60hz(
                contas_mod.serie(registro, analise, lado, 1.0), registro))
            if analise.vale else True,
            # O DOMÍNIO da conta, que é o que diz se ela tem onda e contínua
            # ou só o eficaz. `componente`, `modulo` ou `misto` — e o `misto`
            # é o «não sei», que a tela não barra. Ver `contas.Analise`.
            dominio=("" if not analise.vale
                     else "misto" if analise.tem_onda is None
                     else "componente" if analise.tem_onda else "modulo"),
            # Os avisos são a conta que PASSA com ressalva — a tela escreve no
            # ⓘ azul e deixa aplicar. Ver `plot/contas.py`.
            avisos=list(analise.avisos),
        )

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
        for letra, (outro, apelido, sha_outro) in zip("B", outros, strict=False):
            desl = alinhamento_mod.deslocamento(registro, outro, modo)
            terminais.append({"letra": letra,
                              "nome": _nome_do_terminal(sha_outro, outro, apelido),
                              "registro": outro, "sha": sha_outro, "d": desl["d"],
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

        def textos(term) -> list[str]:
            r = term["registro"]
            return [term["nome"], r.station, r.device_id,
                    str(getattr(r.source, "name", "") or "")]

        fontes: dict = {}
        base = base_mod.ativa()
        if base is not None and base.existe and base_mod.usa("linhas") and len(terminais) > 1:
            achadas = linhas_mod.procurar(base, textos(terminais[0]), textos(terminais[1]))
            if len(achadas) == 1:
                linha = achadas[0]
                fontes["base"] = {"ok": True, "r": linha.r1_ohm, "x": linha.x1_ohm,
                                  "km": linha.comprimento_km, "como": linha.nome}
                if linha.r0_ohm is not None:
                    fontes["base"].update(r0=linha.r0_ohm, x0=linha.x0_ohm)
            else:
                fontes["base"] = {"ok": False, "motivo": (
                    "mais de uma linha da base casa com estes terminais"
                    if achadas else "nenhuma linha da base casa com estes terminais")}
        else:
            fontes["base"] = {"ok": False, "motivo": "sem base de dados ativa"}
        for term in terminais[:2]:
            ajustes = ajustes_de(term)
            fontes[term["letra"]] = seqneg_mod.linha_dos_ajustes(
                ajustes, impedancia_mod.relacao_rtp_rtc(term["registro"], ajustes))
        fontes.setdefault("B", {"ok": False, "motivo": "a aba não tem IED B"})
        fontes["manual"] = seqneg_mod.linha_digitada(
            corpo.get("manual"), impedancia_mod.relacao_rtp_rtc(registro, {}))

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
                      alinhamento=b["alinhamento"] if b else None)
        return jsonify(pacote)

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
                float(corpo["r"]), float(corpo["x"]), float(corpo["km"]), r0, x0)
        except (KeyError, TypeError, ValueError):
            return jsonify(erro="faltam R, X ou o comprimento"), 400
        if not linha.nome or linha.comprimento_km <= 0:
            return jsonify(erro="dê um nome à linha"), 400
        linhas_mod.gravar(base, linha)
        return jsonify(linha=linha.como_dicionario())

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
        try:
            verbete = digitais_mod.anotar(
                base,
                corpo.get("fabricante") or "",
                corpo.get("modelo") or "",
                corpo.get("sinal") or "",
                corpo.get("descricao"),
                corpo.get("categoria"),
            )
        except ValueError as erro:
            return jsonify(erro=str(erro)), 400
        return jsonify(verbete=verbete.como_dicionario(),
                       itens=len(digitais_mod.listar(base)))

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

    @app.get("/api/dicionario/<sha>")
    def dicionario_do_registro(sha: str):
        """O que o dicionário sabe sobre o relé DESTE registro.

        A tela da onda não precisa saber de degraus nem de fabricante: ela
        pergunta pelo registro e recebe a lista já resolvida, um verbete por
        sinal, com a origem escrita por extenso.
        """
        item = acervo.obter(sha)
        equipamento = (item.como_dicionario().get("equipamento") or "") if item else ""
        base = base_mod.ativa()
        ligada = base_mod.usa(base_mod.PASTA_DO_DICIONARIO)
        if base is None or not base.existe or not ligada:
            return jsonify(tem=False, motivo=(
                "nenhuma base de dados ativa" if base is None or not base.existe
                else "o dicionário está desligado nesta base"),
                equipamento=equipamento, verbetes=[])
        fabricante, modelo = digitais_mod.identificar(equipamento)
        verbetes = digitais_mod.aplicaveis(base, equipamento)
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
    if not arranjo or not any(p.tipo in (paineis.IMPEDANCIA, paineis.DIFERENCIAL)
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
