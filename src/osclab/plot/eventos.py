"""A lista de eventos pronta para a tela, no TEMPO DA ABA.

O leitor (`formats/eventos.py`) entrega o tempo de cada evento contado da
primeira amostra do registro dele. Com mais de um registro na aba, o B e o C
estão deslocados em relação ao A (`plot/alinhamento.py`): o instante `t` da
aba cai em `t + d` no outro registro, então o evento do outro entra em
`t − d`. A conta é feita aqui, com o MESMO `d` que desloca as ondas — se a
lista e a onda usassem deslocamentos diferentes, clicar no trip do B poria o
cursor fora do trip do B, sem nada denunciar.

A lista de cada registro vai separada, com a letra do IED. Juntar e ordenar
é da tela, que precisa das duas formas: uma lista só, em ordem de tempo, que
é o que responde «o trip do B veio antes ou depois do A?», e o filtro por IED.
"""

from __future__ import annotations

#: O que se diz quando o registro não traz lista nenhuma.
SEM_LISTA = ("este registro não trouxe lista de eventos. A da Schneider vem no "
             ".hdr, junto com o COMTRADE; a SEL (SER) e a Ingeteam (SUCESOS) "
             "exportam a lista à parte, e a importação desses arquivos ainda "
             "vai entrar")
#: E quando há um arquivo, mas o programa não achou nele uma tabela que
#: soubesse ler. Pedido dele, 02/11/2026: relé que nunca vimos escreve a
#: hora, o sinal e o valor em outra ordem, e tabela lida errado é pior que o
#: texto cru — o texto ao menos não mente.
NAO_RECONHECIDA = ("o programa não reconheceu uma tabela de eventos neste "
                   "arquivo, então ele vai como veio, sem ligação com o cursor")


def chave_do_nome(nome: str) -> str:
    """O nome sem espaço nem dois-pontos, em maiúsculas.

    O mesmo sinal vem escrito de dois jeitos pelo MESMO relé: `MAIN  Gen.
    trip command` na lista de eventos e `MAIN : Gen. trip command` no canal
    digital do COMTRADE (Schneider, conferido nos 250 `.hdr` do banco: 15 316
    eventos casaram com o digital na mesma amostra).
    """
    return "".join(c for c in (nome or "").upper() if not c.isspace() and c != ":")


def indice_dos_digitais(canais) -> dict[str, int]:
    """`{chave do nome: índice}` dos digitais de um registro. Nome repetido
    fica com o primeiro: dois canais de mesmo nome não se distinguem pelo
    texto do evento, e escolher o segundo seria palpite."""
    saida: dict[str, int] = {}
    for canal in canais or ():
        saida.setdefault(chave_do_nome(canal.name), canal.index)
    return saida


def _linha(evento, d: float, fim: float | None, conhecida: bool,
           digitais: dict[str, int] | None = None) -> dict:
    t = evento.t - d if conhecida else None
    # Fora da gravação: o relé continua listando depois que o COMTRADE acaba
    # (no banco, 4186 eventos de 250 listas). Aparece, mas não leva o cursor:
    # ali não há onda para ele cair.
    fora = conhecida and (evento.t < 0 or (fim is not None and evento.t > fim))
    # O digital que este evento nomeia, quando o registro o grava: clicar no
    # evento seleciona a tira dele (pedido dele, 02/11/2026). Sem casamento,
    # `None` — o clique só move o cursor, e nada se inventa.
    digital = (digitais or {}).get(chave_do_nome(evento.descricao))
    return {"t": t, "hora": evento.hora, "endereco": evento.endereco,
            "descricao": evento.descricao, "valor": evento.valor, "fora": bool(fora),
            "digital": digital}


def lista(letra: str, sha: str, apelido: str, achada, d: float = 0.0,
          fim: float | None = None, digitais: dict[str, int] | None = None) -> dict:
    """O pacote de UM registro. `achada` é a `formats.eventos.Lista` ou None.

    `tem` é ter a lista ANIMADA (ligada ao cursor). Sem ela, `cru` pode
    trazer o arquivo como veio — a tela mostra o texto em vez de nada.
    """
    pacote = {"letra": letra, "sha": sha, "apelido": apelido or "",
              "tem": achada is not None and achada.reconhecida,
              "cru": achada.cru if achada is not None else ""}
    if achada is None or not achada.reconhecida:
        pacote.update(motivo=SEM_LISTA if achada is None else NAO_RECONHECIDA,
                      de=achada.de if achada is not None else "",
                      referencia="", avisos=[], eventos=[], dados=[])
        return pacote
    conhecida = achada.referencia_conhecida
    pacote.update(
        motivo="",
        de=achada.de,
        referencia=achada.referencia,
        avisos=list(achada.avisos),
        eventos=[_linha(e, d, fim, conhecida, digitais) for e in achada.eventos],
        dados=[_linha(e, d, fim, conhecida) for e in achada.dados],
    )
    return pacote
