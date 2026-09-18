# NOTICE

OscLab — Leitor e analisador de oscilografia
Copyright (C) 2026

Licenciado sob a **GNU Affero General Public License, versão 3 ou posterior**
(AGPL-3.0-or-later). O texto completo está em [LICENSE](LICENSE).

> **Titularidade:** os direitos patrimoniais sobre este programa pertencem à
> distribuidora de energia para a qual ele foi desenvolvido. Substitua a linha
> de copyright acima pela razão social antes da primeira release pública.

## Por que AGPL

Escolha deliberada, e não a única possível — vale entender o que ela faz.

A AGPL **permite** uso comercial. O que ela exige é outra coisa: quem
distribuir o programa, **ou servi-lo pela rede**, tem que entregar o
código-fonte junto, sob esta mesma licença, incluindo as modificações.

O objetivo aqui é impedir que alguém pegue este trabalho, feche o código e o
comercialize como produto próprio. A AGPL faz isso sem proibir uso comercial:
torna a apropriação fechada impossível em vez de ilegal.

A cláusula que importa para esta ferramenta especificamente é a **§13**. O
OscLab é servido por HTTP: se alguém o hospedar para uma equipe usar, isso já
aciona a obrigação de oferecer o código aos usuários — o buraco que a GPL comum
deixaria aberto.

O repositório é público por decisão de projeto, o que satisfaz a §13 por
construção e, de quebra, é o que permite a atualização automática funcionar sem
nenhum token embarcado no pacote distribuído.

## Dependências

| Pacote | Versão mínima | Licença |
|---|---|---|
| numpy | >= 1.26 | BSD-3-Clause |
| flask | >= 3.0 | BSD-3-Clause |

Desenvolvimento apenas (não entram no pacote distribuído):

| Pacote | Licença |
|---|---|
| pytest | MIT |
| ruff | MIT |

Todas são permissivas e compatíveis com a AGPL. **Antes de acrescentar qualquer
dependência, confira a licença dela:** uma biblioteca GPL ou AGPL nova não muda
nada aqui, mas uma com licença incompatível, ou não-livre, tornaria este projeto
indistribuível.

## Bibliotecas de terceiros embarcadas

Nenhuma até o momento. Quando a interface gráfica chegar (marco 0.3), o **uPlot**
(MIT, Leon Sorokin) passará a viajar dentro de `src/osclab/web/static/js/` — uma
subestação pode não ter internet, então nenhuma página pode buscar biblioteca em
CDN. A licença dele acompanhará o arquivo.

## Material não redistribuído

Manuais de fabricante, perfis de dispositivo e arquivos de oscilografia reais de
subestações **não** entram neste repositório. Dados derivados que sejam de
autoria própria podem entrar; os documentos originais, não.

Oscilografias reais merecem atenção redobrada: identificam instalação, data e
comportamento da rede da distribuidora. Os exemplos em `samples/` devem ser
sintéticos ou explicitamente liberados.
