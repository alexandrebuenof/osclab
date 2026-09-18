# OscLab

Leitor e analisador de oscilografia para sistemas de potência.

Lê registros de perturbação de relés de vários fabricantes, analisa a falta,
estima onde ela ocorreu por diferentes métodos e gera relatório. A interface é
uma página web que roda na própria máquina — nada sai para a internet.

> **Versão 0.2 — o leitor.** Já lê COMTRADE de verdade (testado contra
> registros reais de GE, Schneider e SEL), mas a tela de formas de onda só chega
> no marco 0.3. Por enquanto o resultado sai no terminal.

## Requisitos

- Python 3.11 ou mais novo
- Windows, Linux ou macOS

## Como rodar

**Windows** — clique duas vezes em `osclab.cmd` e escolha no menu. Na primeira
vez, use a opção 2 para preparar a pasta.

**Qualquer sistema**, pela linha de comando:

```bash
python app.py --preparar     # cria o venv e instala as dependências
python app.py --web          # sobe o servidor
```

Depois abra <http://localhost:8770/> no navegador. `Ctrl+C` encerra.

Para descrever uma oscilografia no terminal, sem interface:

```bash
python app.py --ler caminho/do/registro.cfg
```

O `app.py` cuida do virtualenv sozinho: cria `.venv/` ao lado dele e se
re-executa lá dentro. Ele só chama o `pip` quando alguma dependência falha ao
importar — nunca para conferir se há versão nova. Isso é proposital: a
ferramenta precisa abrir numa subestação sem internet.

## Estrutura

```
osclab/
├── app.py                 launcher: virtualenv, dependências, modo de execução
├── osclab.cmd / .sh       menu no terminal
├── VERSION                o número da versão, e nada mais
├── requirements.txt       dependências de execução (curtas de propósito)
├── config/
│   ├── config.ini.example modelo versionado
│   └── config.ini         o real — fica FORA do git
├── src/osclab/
│   ├── paths.py           todo caminho do programa sai daqui
│   ├── version.py         leitura e comparação de versões
│   ├── formats/           leitura de oscilografia
│   │   ├── base.py        o contrato: o que é um `Record`
│   │   └── registry.py    escolhe o leitor pelo conteúdo do arquivo
│   ├── dsp/               processamento de sinal: DC, janela, DFT, fasores
│   ├── analysis/          perturbação: descontinuidade, classificação, inrush
│   ├── faultloc/          localização de faltas, um método por módulo
│   ├── network/           impedâncias de linha, TC/TP, estruturas do KMZ
│   ├── library/           acervo de arquivos endereçado por sha256
│   ├── report/            geração do relatório
│   ├── cli/               análise em lote, sem navegador
│   └── web/               interface — e só ela
├── data/                  dados de referência que acompanham o programa
├── samples/               oscilografias de exemplo, usadas nos testes
├── docs/                  requisitos, decisões e notas de projeto
├── tests/                 pytest
└── tools/                 scripts de build e manutenção
```

A regra que sustenta esse desenho: **a camada `web/` não calcula.** Ler formato,
processar sinal e localizar falta rodam sem navegador nenhum — é o que permite
testar, rodar em lote e gerar relatório automaticamente.

## Desenvolvimento

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # Windows: .venv\Scripts\pip

pytest              # testes
ruff check .        # lint
```

## Formatos

| Formato | Situação |
|---|---|
| COMTRADE `.cfg` + `.dat` | **lê** — edições 1991, 1999 e 2013 |
| COMTRADE `.cff` (arquivo único) | **lê** |
| Dados ASCII, binário 16 e 32 bits, float 32 | **lê** |
| SEL `.CEV` | próximo formato |
| ATP `.PL4` | para validar os algoritmos contra resposta conhecida |

Verificado contra registros reais de **GE 850**, **Schneider MiCOM P139**,
**SEL-421**, **SEL-487E** e **SEL-TWFL**. Cada esquisitice de fabricante que
apareceu virou um teste — a lista está no `CLAUDE.md`.

COMTRADE é norma aberta e os sete fabricantes do parque a geram — por isso é a
base. Os formatos proprietários entram como leitores adicionais que convertem
para o mesmo modelo interno.

## Licença

AGPL-3.0-or-later. Ver [LICENSE](LICENSE) e [NOTICE.md](NOTICE.md).

Em uma frase: qualquer pessoa pode usar, estudar e modificar — mas quem
distribuir o programa, ou servi-lo pela rede, tem que entregar o código-fonte
junto, sob a mesma licença.
