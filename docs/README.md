# docs/

Notas de projeto, versionadas junto com o código. O registro completo das
conversas vive no projeto "Leitor de Oscilografia" no Claude; isto aqui é a
cópia do que pode ser público — o repositório é aberto e os direitos são da
distribuidora.

**Comece por `estado-do-trabalho.md`.**

| Arquivo | O que é |
|---|---|
| `estado-do-trabalho.md` | **Onde o trabalho parou** — leia primeiro |
| `decisoes.md` | O que já está resolvido, o que está em aberto e por quê |
| `requisitos-funcionais.md` | O que a ferramenta precisa ter, com os detalhes técnicos |
| `ideias.md` | Backlog do Alexandre, com o plano de curto prazo |
| `referencia-pac-ct.md` | Análise da PAC CT, a ferramenta usada como modelo |

## Decisões de tela

| Arquivo | O que é |
|---|---|
| `decisoes-de-interface.md` | Nomes de sinal, menu de sinais, busca, calculadora, barra de energia, vínculo de potência e a unidade da potência (12/10) |
| `decisoes-de-estetica.md` | Logotipo, tela inicial, ícones dos módulos, e o vocabulário de **vários registros abertos** (14/10) |
| `comandos-de-teclado.md` | Teclas que geram painel a partir do gráfico selecionado — a fazer |

## Os gráficos

| Arquivo | O que é |
|---|---|
| `graficos-que-faltam.md` | O levantamento contra o SynchroWave, e a regra do que pode ser escrito dentro do desenho |
| `plano-de-impedancia.md` | O painel mho — **implementado**, com a armadilha da base e os ajustes manuais |
| `ajustes-manuais-do-plano.md` | As dez maquetes de onde moram os ajustes digitados |
| `espectro-complexo-e-moldura.md` | Espectro, gráfico complexo e a moldura do cursor — a fazer |
| `plano-alfa-87l.md` | O plano alfa do 87L — a fazer |

## O relé por dentro

| Arquivo | O que é |
|---|---|
| `ajustes-e-logica-dentro-do-registro.md` | Os ajustes já vêm no arquivo de oscilografia, em boa parte dos casos |
| `logica-e-cores-dos-digitais.md` | O painel da lógica/ajustes, o pincel e as cores dos digitais |
| `schneider-onde-mora-a-logica.md` | O que um registro MiCOM P139 traz, e o que não traz |
| `log-de-eventos.md` | A lista de eventos do relé — a fazer |

## A base de dados

| Arquivo | O que é |
|---|---|
| `base-de-dados.md` | A pasta `database/`, as gavetas e o princípio de ser sempre opcional |
| `dicionario.md` | O CSV dos sinais digitais, as categorias e a regra de precedência |

As regras de trabalho e os invariantes do código estão no `CLAUDE.md`, na raiz.

## O que NÃO está aqui

Notas com dado da empresa — nomes de subestação, parâmetros reais de linha,
casos reais de falta — ficam em `docs-privados/`, que está no `.gitignore`.
