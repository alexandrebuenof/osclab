# Fontes embutidas

As fontes da identidade visual (decidida em 10/11/2026, ver
`docs/identidade-visual.md`) viajam DENTRO do pacote: uma subestação sem
internet não pode depender de CDN para a tela ter a cara que tem. Quem as
declara é o `@font-face` no topo de `css/osclab.css`.

| arquivo | família | peso | uso |
|---|---|---|---|
| `public-sans-400.woff2` | Public Sans | 400 | texto |
| `public-sans-700.woff2` | Public Sans | 700 (serve 600–800) | títulos, item atual |
| `ibm-plex-mono-400.woff2` | IBM Plex Mono | 400 | números, chaves |
| `ibm-plex-mono-600.woff2` | IBM Plex Mono | 600 (serve 600–800) | números em destaque |

Só o subconjunto **latino** (inclui os acentos do português). Origem: os
pacotes `@fontsource/public-sans` e `@fontsource/ibm-plex-mono` do npm,
copiados da maquete de identidade (`../osclab-maquetes`, ramo
`maquete/identidade-visual`).

## Licença

As duas famílias estão sob a **SIL Open Font License 1.1** (texto integral em
`OFL.txt`, ao lado). Ela permite usar, embutir e redistribuir as fontes junto
com o programa, desde que este aviso e a licença viajem junto e que as fontes
não sejam vendidas sozinhas.

- **Public Sans** — Copyright 2015 The Public Sans Project Authors
  (<https://github.com/uswds/public-sans>).
- **IBM Plex Mono** — Copyright © 2017 IBM Corp., com Reserved Font Name
  «Plex» (<https://github.com/IBM/plex>).

Nenhuma das duas foi modificada além do recorte do subconjunto feito pelo
Fontsource.
