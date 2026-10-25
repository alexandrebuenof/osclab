"""O triângulo de tensões: o diagrama fasorial lido pela FORMA.

O que é
=======

Os três fasores de tensão fase-neutro saem da mesma origem — o neutro — e as
**pontas** deles formam um triângulo. Os **lados** desse triângulo são as
tensões de linha: o lado que liga a ponta de A à ponta de B *é* V_AB.
Equilibrado, ele é equilátero com o neutro no centro.

Por que vale um painel próprio
==============================

Porque a deformação identifica a falta sem número nenhum:

===================================  ==========================
o que se vê                          o que é
===================================  ==========================
um VÉRTICE cai na direção do neutro  falta monofásica naquela fase
um LADO achata, pontas se aproximam  falta bifásica entre aquelas duas
encolhe INTEIRO, segue equilátero    falta trifásica
===================================  ==========================

E o baricentro do triângulo é **V₀**: como `V0 = (Va+Vb+Vc)/3`, o centro de
massa das três pontas é literalmente a componente de sequência zero. Num
sistema equilibrado ele cai sobre a origem; numa falta à terra ele se
desloca, e esse deslocamento é o que separa `BC` de `BC-T` — dois eventos que
nas ondas se parecem muito mais do que aqui.

Só com tensão de FASE
=====================

Com tensão de linha o triângulo ainda sai, e sai exato: `VAB+VBC+VCA ≡ 0`, os
três fasores fecham sozinhos. O que não sai é **onde fica o neutro** — V₀ é
irrecuperável de tensão de linha (três incógnitas, duas equações).

E a armadilha é que desenhar a cruz no baricentro seria fácil, porque o
baricentro sempre existe. Só que pôr a cruz ali afirma `V0 = 0`, e apagaria em
silêncio a única diferença entre `BC` e `BC-T`: os dois ficariam idênticos na
tela.

Por isso **este painel só aceita vínculo com tensão de fase**. Escolha do
Alexandre, entre as duas saídas possíveis: metade do gráfico com uma ausência
explicada, ou gráfico nenhum. Ele preferiu gráfico nenhum — e a porta continua
aberta pelo canal de tensão residual MEDIDO, que daria o neutro de volta.

De onde vêm os seis sinais
==========================

Do **vínculo de potência**, não de uma lista de sinais que o usuário monta. O
vínculo já diz qual trinca de tensão pertence ao mesmo vão de qual trinca de
corrente — que é exatamente o que este gráfico precisa saber, e é informação
que o programa não deduz sozinho. Ver `Record.vinculos_de_potencia`.

Consequência: o painel se descreve por UM campo (`vinculo`), e não por seis
ids. Trocar a trinca no editor de grupos conserta o triângulo junto, sem
ninguém ter que refazer o painel.

Os fasores vêm da leitura do cursor, como no fasorial — este módulo não
calcula fasor nenhum, só diz QUAIS sinais o diagrama quer e como lê-los.
"""

from __future__ import annotations

from osclab.formats import conjuntos
from osclab.formats.base import Record
from osclab.plot.paineis import TRIANGULO

#: As três camadas que o botão do painel acende e apaga.
#:
#: Independentes, e não um seletor de três estados: dá para querer as tensões
#: sem as correntes, ou as correntes sozinhas. E existem porque as duas
#: grandezas se cruzam — num `BC-T` a corrente da fase C cai praticamente em
#: cima da tensão da fase A, e com tudo aceso não se lê nenhuma das duas.
CAMADAS = ("linha", "fase", "corrente")


def vinculos_possiveis(registro: Record) -> list[dict]:
    """Os vínculos que PODEM virar triângulo, para a tela oferecer.

    Só os de tensão de fase, e só a partir do lado da CORRENTE — o mesmo lado
    que nomeia as potências, para o par ter um nome só no programa inteiro.
    """
    escolhas = getattr(registro, "vinculos_de_potencia", None) or {}
    if not escolhas:
        return []
    por_nome = {c.nome: c for c in conjuntos.de_registro(registro)}
    saida = []
    for chave, vinculo in sorted(escolhas.items()):
        corrente = por_nome.get(chave)
        tensao = por_nome.get(str(vinculo.get("com") or ""))
        if corrente is None or tensao is None or corrente.grandeza != "I":
            continue
        # A trinca manda sobre o que o usuário marcou no vínculo: ela é
        # montada de `AB/BC/CA` ou de `A/B/C`, e isso não é palpite. Ver
        # `catalogo._base_do_vinculo`.
        base = ("linha" if tensao.e_de_linha
                else str(vinculo.get("base") or "fase"))
        saida.append({
            "vinculo": chave,
            "par": f"{corrente.rotulo}↔{tensao.rotulo}",
            "base": base,
            # Vai junto o que NÃO serve, e o porquê: a lista mostra o vínculo
            # em delta apagado com o motivo ao lado, em vez de escondê-lo. Um
            # vínculo que some da lista se lê como vínculo que não existe.
            "vale": base == "fase",
            "motivo": "" if base == "fase" else (
                "tensão de linha: o neutro não é medível, e sem ele o "
                "triângulo não distingue falta à terra de falta entre fases"),
        })
    return saida


def sinais_do_vinculo(registro: Record, chave: str) -> tuple[str, ...]:
    """Os seis ids — três tensões, três correntes — na ordem A, B, C.

    Ids de canal (`c{i}:instantaneo`), que é a BASE de cada linha: o fasor é
    da linha, e nem o filtro nem a medida do painel mexem nele. Mesma regra do
    fasorial.
    """
    escolhas = getattr(registro, "vinculos_de_potencia", None) or {}
    vinculo = escolhas.get(chave)
    if not vinculo:
        return ()
    por_nome = {c.nome: c for c in conjuntos.de_registro(registro)}
    corrente = por_nome.get(chave)
    tensao = por_nome.get(str(vinculo.get("com") or ""))
    if corrente is None or tensao is None:
        return ()
    return tuple(f"c{i}:instantaneo"
                 for i in (*tensao.abc, *corrente.abc))


def montar(registro: Record, painel, por_id: dict, escalas: dict,
           lado: str) -> dict:
    """O pacote do painel. Os fasores vêm da leitura do cursor.

    Reaproveita `fasorial.montar` inteiro: a descrição de cada sinal — nome,
    fase, unidade, base de pu — é a mesma pergunta nos dois diagramas, e duas
    implementações dela divergiriam no primeiro caso torto. O que este módulo
    acrescenta é o PAR, a validade do vínculo e as camadas.
    """
    from dataclasses import replace

    from osclab.plot import fasorial

    chave = painel.vinculo or ""
    possiveis = {v["vinculo"]: v for v in vinculos_possiveis(registro)}
    qual = possiveis.get(chave)

    avisos = list(painel.avisos or ())
    sinais = sinais_do_vinculo(registro, chave) if qual and qual["vale"] else ()
    if not chave:
        avisos.append("escolha o vínculo de onde este triângulo sai")
    elif qual is None:
        avisos.append("o vínculo deste triângulo não existe mais neste "
                      "registro — refaça-o em «editar grupos»")
    elif not qual["vale"]:
        avisos.append(qual["motivo"])

    # O fasorial monta a lista a partir de `painel.sinais`; aqui os sinais são
    # do vínculo, não do painel. Um painel-sombra evita duplicar a montagem.
    sombra = replace(painel, sinais=sinais, referencia="")
    pacote = fasorial.montar(registro, sombra, por_id, escalas, lado)
    pacote.update({
        "tipo": TRIANGULO,
        "nome": painel.nome or (f"Triângulo {qual['par']}" if qual
                                else "Triângulo"),
        "vinculo": chave,
        "par": qual["par"] if qual else "",
        "base_da_tensao": qual["base"] if qual else "",
        "camadas": list(painel.camadas or CAMADAS),
        # Quais vínculos a tela pode oferecer, com os que não valem marcados.
        "vinculos": possiveis and list(possiveis.values()) or [],
        "avisos": avisos,
    })
    return pacote
