"""A base de dados do usuário: o que o programa sabe sobre o mundo real.

Duas gavetas:

1. **Dicionário** — o nome e o significado de cada sinal digital de relé
   (`51P1T`, `TRIP`, `52A`), por fabricante e modelo. Tela de consulta:
   procura-se um nome e lê-se o que ele quer dizer.
2. **Linhas e estruturas** — parâmetros de linha para a localização de falta e
   os KMZ das estruturas.

Uma terceira — o **histórico de oscilografias** — está desenhada e adiada:
ela chega com o módulo que a usa.

A regra que vale como contrato deste pacote: **nada aqui é necessário para o
programa funcionar.** Sem o dicionário, o digital aparece com o nome cru que
veio no arquivo. Sem a linha cadastrada, os parâmetros são digitados na tela a
cada cálculo. A base acelera; ela nunca destrava.
"""

from osclab.basedados import digitais, navegar, pasta  # noqa: F401
