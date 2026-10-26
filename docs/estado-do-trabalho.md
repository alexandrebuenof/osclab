# Onde o trabalho está

## 25/10/2026 — confiabilidade e universalidade (commits b6c1495 … 3b1a958)

**Princípio novo (CLAUDE.md): o leitor é universal.** Qualquer relé abre e
analisa; o que não se lê automaticamente se digita; nada do parque da
Energisa MT pode virar condição.

Feito:

- Diferencial 87T sai em 28/28 registros de 487E/787 (o `ccbm` com o nome do
  relé juntava os terminais; `E87HR` lido). 87L: cada terminal vira trinca,
  o plano de impedância casa `I*` ↔ `V*`, o alfa lê `87LPR/87LPA` e `87LR/87LANG`.
- Paleta: o validador simulava daltonismo errado (fora do espaço LMS);
  corrigido. Tema ESCURO com cores novas escolhidas pelo Alexandre.
- LDL: validação independente virou `tests/test_ldl_validacao.py`; nota 50 → ~75.
- Rotinas contra o dado real: `tools/comissionar.py` (placar em
  `docs-privados/comissionamento/`), `tools/fotografia.py` (foto em
  `docs-privados/fotografia/banco-2026-10-25.jsonl`), `tests/test_varredura.py`.

**Pendente com o Alexandre:**

1. `git push` dos commits do dia.
2. Cores: escolher entre as 10 maquetes de «cores das fases»
   (`OscLab maquetes/cores-das-fases-10.html`) e as cores do tema CLARO (ele
   ainda reprova no validador corrigido).
3. Classificador: «falta já em curso» (inclui a falta entre 1 e 2 ciclos do
   começo, xfail em `test_varredura.py`), os 74 religadores «AG sem trip»,
   seleção de fase do relé como prova.
4. LDL: Takagi como RESULTADO de um terminal quando houver pré-falta (hoje
   é só conferência; o pior erro com carga cai de 50 para 5 km, mas piora no
   TC saturado e na falta à terra perto da barra). Antes, medir o Takagi
   polarizado por I2. A capacitância `b1` ainda não tem campo na tela.
5. Propostas de função nova (pedem 10 maquetes): diferencial juntando dois
   registros (P139/451), ajustes do MiCOM por exportação de texto do Easergy,
   ajustes do PL300 pelo `AJUSTES_*`.

6. Plano de impedância: a ficha «% da LT» é |Z|/|ZL| e soma a Rf ao
   comprimento (Rondonópolis CG: 16,5 % contra 12 % do relé). Mostrar a
   reatância, as duas, ou deixar?
7. A conferência 1 (resíduo) reprova 72 registros do banco em que o `IN`
   medido é entrada própria (`Current IN` do MiCOM, `IN` do 311C, `INS`
   sensível do PL300). Não é defeito de conta; a conferência precisa
   reconhecer esse caso em vez de reprovar.

Feito depois (commits 7a153f8, 51157ed, f71e71d): 87T com bloqueio e
restrição juntos; LDL recusa a trifásica externa (a direção comparava fasores
que giram), Takagi de conferência, seq. negativa pela linha distribuída;
plano de impedância com k0 sobre a soma das fases (o `IN` do 311C é entrada
própria e tirava a compensação: 6 de 22 faltas reais erravam até 71 pontos);
conferências 9 (87T) e 10 (21) contra o relé — na 10, só o 321 de Coxipó
diverge, sem explicação ainda (conferir no SIGRA).

## 24/10/2026 — etapa de aprendizagem sobre o banco do parque (sem commit)

O banco inteiro de oscilografias (558 registros) foi lido, junto com os `.hdr` e os manuais dos seis fabricantes. O que se aprendeu, com os dados reais, está em `docs-privados/aprendizado/`, e o dicionário dos digitais em `docs-privados/dicionario/dicionario.csv`, com 2077 verbetes prontos para importar. Nada disso entra no git.

Defeitos corrigidos, cada um com teste:

- **Dialetos SEL:**
  - o `.CEV` do 311C/311L (`"FID",<soma>`), que não abria;
  - um leitor novo para o relatório EVE em texto do SEL-321 (`formats/sel_texto.py`).
- **Taxa `nrates = 0`:** o `.cfg` do SEL-751 e do 311C não declara taxa, e `analysis/falta.py` lia `sample_rates[0]`, que vale 0 nesse caso. Faltas de 9 kA saíam «nenhuma descontinuidade». Agora a taxa sai de `Record.trechos`.
- **Trincas que não fechavam:**
  - O religador escreve `T1 Phase C Current` e a última ocorrência do C é a de `CURRENT`.
  - O PL300 escreve `IA-Int.Fase A`, com a fase duas vezes, e o `Int.` era lido como neutro.
  - O acento de `Tensión` soltava o N.
  - A correção é uma **segunda tentativa** (`conjuntos._sem_as_marcas`), só para quem a primeira deixou sem trinca. A fotografia do banco antes × depois mostrou que nenhuma trinca que já fechava mudou.
- **Data da edição 1991:** a norma manda `mm/dd/aa`, e ela era lida como dd/mm.
- **`.dat` ASCII com linha colada (coletor RTAC):** a amostra perdida comprimia a onda. Agora cada amostra vai para a posição do seu número, e o que se perdeu fica em branco, com aviso.
- **Trip em espanhol:** `disparo_do_rele` passou a reconhecer `Disparo` (Ingeteam).
- **`k0`:**
  - Agora se lê `k0M1`/`k0A1` em par.
  - `Z0F`, que é o limiar do 32G e não k0, deixou de ser usado.
- **Dicionário:** `identificar` passou a entender a FID da SEL (`FID=SEL-487E-3-R312…` → SEL 487E; `411L-A` → 411L) e o MiCOM.
- **Digitais sem placa:** os digitais que a placa do relé não tem saem da tela padrão (`[IOBOARDS]`).

**Em aberto com o Alexandre:** a lista está no relatório da sessão. O principal:
- os 74 religadores que agora saem AG sem trip;
- a identificação de fabricante do PL300 e do SIPROTEC, que não vem no campo do equipamento;
- a cor do cursor 2, que o validador de paleta não confere;
- as maquetes do acervo e dos temas.

## 23/10/2026 — localização de falta, etapa 1 de 3 (sem commit)

O painel 1 das maquetes entrou no programa: **«localizar falta» abre uma tela
própria** no lugar das ondas, com a faixa do resultado presa no topo e três
passos (alinhar A × B, conferir o platô, resultado). A conta é
`faultloc/ldl.py`: a LDL amostra a amostra pela **sequência negativa de dois
terminais** e pelo **laço da falta (reatância)**, a mediana do platô, a
direção pela seq. negativa com V2 na referência, e o cursor 1 compartilhado
com a oscilografia. A linha ganhou **Z0** (base, ajustes Z0MAG/Z0ANG,
digitado). Testes em `tests/test_ldl.py`. Ver `localizacao-de-falta.md`.

**Próximo:** etapa 2, a aba de simulações (painel 1 da maquete
`localizacao-painel-1.html`); depois a etapa 3, a ajuda dos métodos.
**Em aberto com o Alexandre:** a polaridade de corrente dos registros reais
(ver «O que os registros reais mostraram» em `localizacao-de-falta.md`).

---

Atualizado em **21/10/2026**, versão **0.7.0**. Este arquivo existe para uma
sessão nova saber de onde continuar sem reler o histórico inteiro. Mantê-lo
curto e atual vale mais do que mantê-lo completo.

## O ponto exato

A última rodada fechou o **plano de impedância**, incluindo os ajustes
manuais. O próximo passo, escolhido pelo Alexandre em 21/10/2026, são os
**outros três gráficos** — complexo, espectro e plano alfa —, que já têm
maquete aprovada e nenhuma pergunta de engenharia em aberto.

Suíte: **725 passam, 0 falham, 19 pulam** (`python3 tudo.py` da raiz).

## O que já funciona

| Parte | Estado |
|---|---|
| Leitura | COMTRADE (`.cfg`/`.dat`), `.CEV` + `.HDR` da SEL, com detecção de filtragem |
| Acervo | importação, metadados, selo do tipo de falta no cartão |
| Painéis | analógico, digital, fasorial, triângulo de tensões, harmônicos, **plano de impedância** |
| Análise | classificador de tipo de falta (11 tipos), com os porquês escritos |
| Base de dados | pasta, gavetas, dicionário de sinais digitais |
| Ajustes do relé | lidos do `SETTINGS` do `.CEV` e do `.HDR`; painel de lógica |

### O plano de impedância, em detalhe

É o painel mais novo e o que tem mais decisão acumulada. O registro completo
está em `plano-de-impedancia.md` no projeto do Claude; o essencial:

- Entra pelo «+ adicionar gráfico» e nasce no **laço que o classificador
  achou** (`data-laco` no `<body>` do `onda.html`).
- Desenha trajetória, zonas, parâmetros da linha, MTA e os dois cursores. Os
  pontos da trajetória só aparecem **enquanto a mão está no cursor**.
- **Todo número carrega a origem**: `lido` (traço cheio), `sugerido`
  (tracejado) e `digitado` (pontilhado). Uma zona inventada que pareça lida
  do relé é o pior defeito que esta tela pode ter.
- Os ajustes manuais ficam numa caixa pendurada no `body`, **não dentro do
  painel**: cada tecla pede a janela ao servidor de novo e a resposta refaz
  os painéis, então um menu no cabeçalho sumiria a cada letra.
- O que se digita é **ohm secundário**, como o ajuste do relé. O JSON traz um
  campo `ajuste` com os valores antes da conversão de base — é o que o
  formulário edita.

## A fila

1. **Os outros três gráficos** — complexo, espectro, plano alfa. ← aqui
2. **Abas e multi-registro** — duas oscilografias independentes em abas, e a
   tira para somar um terceiro registro na mesma janela.
3. **Localizador de falta** — reatância simples, Takagi com 3I0 e Takagi com
   ΔI. É o propósito do programa, e tudo o que ele precisa já existe.
4. **Relatório automático** — a outra metade do propósito, ainda sem nada.
5. **Log de eventos** — do `.HDR` quando vem, ou importado de `.txt`.
6. **Popular a base** — todas as linhas e todos os sinais digitais.

## Pendências conhecidas

Dívidas reais, não ideias. Cada uma já foi vista e deixada para depois:

1. **`tudo.py` pula em silêncio quem pede fixture** — 239 de 646 testes. Teste
   que não roda é pior que teste nenhum. Os testes novos de `impedancia` e
   `falta` foram escritos **sem fixture** por causa disso.
2. **Entrada na zona medida na trajetória decimada** (600 pontos): erra
   algumas amostras num registro longo.
3. **Quadrilátero não desenhado** — o relé declara (`E21MG`, `XG1`/`RG1`) e o
   painel só faz mho.
4. **Vínculo em delta é recusado inteiro** no plano, mas
   `Z_AB = V_AB / (I_A − I_B)` sai direto de uma trinca de linha. Só o laço
   de terra é que não.
5. **«entrou Z1 · amostra 71»** usa o índice cru da amostra. Seria mais útil
   em ms depois do início da falta, ou em ciclos.
6. **A sugestão de zona** (80 %, 120 %, 200 %) está **a confirmar com a
   proteção**.
7. **`OSCLAB_DATA_DIR` aponta para dentro da pasta do programa** — acervo,
   cache e base no mesmo lugar do código. Decisão pendente: mudar só a base,
   mover a pasta de dados inteira, ou deixar como está.

## Como rodar

```
python3 tudo.py                 # a suíte inteira, da raiz
osclab.cmd                      # o programa (reiniciar após mexer em .py ou template)
```

Depois de mexer só em `.js` ou `.css`, Ctrl+F5 no navegador basta — o Jinja
cacheia template, então template exige reiniciar.

Servidor de desenvolvimento, quando for preciso um porta separada:

```
OSCLAB_DATA_DIR=<dir> python3 app.py --web --port <N> --no-venv --skip-install
```

**Amostras fictícias** para testar sem registro real: duas oscilografias
coerentes entre si (COMTRADE e `.CEV`+`.HDR`), dois terminais da mesma linha,
falta AN a 62 % com 1,5 Ω de arco. Ficam **fora do repositório**, na pasta de
arquivos do OscLab no computador do Alexandre, com um `LEIAME.md` e o script
que as gera.

## O que NÃO está neste repositório, e por quê

O repositório é **público** e os direitos são da distribuidora.

- **Oscilografias reais** da empresa. As fictícias existem justamente para
  isso; as reais ficam fora, apontadas por `OSCLAB_AMOSTRAS`.
- **Manuais de fabricante** — direito autoral. Entra o dado factual escrito
  com as nossas palavras, nunca o manual.
- **A base de dados** — KMZ das estruturas, parâmetros de linha, histórico.
  `/base/`, `/database/`, `/base-*/` e `/bases.json` estão no `.gitignore`.
- **`config/config.ini`** — tem IP e senha de equipamento. O modelo versionado
  é o `config.ini.example`. Uma senha de subestação commitada fica no
  histórico para sempre.
- **Os docs do projeto com dado da empresa.** O registro das discussões vive
  no projeto "Leitor de Oscilografia" no Claude. Alguns daqueles documentos
  **não podem** ser copiados para cá — em particular o de modelagem de
  linhas, que traz nomes de subestação e parâmetros reais do estudo de curto.

## As maquetes

Antes de implementar função nova, dez maquetes funcionais com dados fictícios
(regra 6 do `CLAUDE.md`). As publicadas até aqui, para consulta:

| Assunto | Link |
|---|---|
| Plano de impedância (mho) | `claude.ai/artifact/NQMGnoy2aSQwjc8ZJieHTX` |
| Plano complexo | `claude.ai/artifact/4xrQ2A5EKjmDZjtVHdCsHM` |
| Espectro | `claude.ai/artifact/4oqyPNNB7GjiSf4EjKu661` |
| Plano alfa (87L) | `claude.ai/artifact/5DdPuQwpWkLvDSx9Xa6ATV` |
| Multi-oscilografia | `claude.ai/artifact/56GuKo62gdQFWnSjDKo9ZF` |
| Tipo de falta | `claude.ai/artifact/VjBrrfVwB6D3tMSinTFjv3` |
| Ajustes manuais do plano | `claude.ai/artifact/RDW2oMHeh8GcHojowGnNiv` |

Os três primeiros são justamente os da próxima etapa: **complexo, espectro e
alfa já estão decididos em maquete** — falta só trazer para o programa.
