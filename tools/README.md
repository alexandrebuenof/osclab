# tools/

Scripts de manutenção e conferência, que **não** fazem parte do programa.

| script | para quê |
|---|---|
| `paleta.py` | valida a paleta de cores: ΔE2000 entre todos os pares, nos dois temas, sob visão normal e sob daltonismo (simulado no espaço LMS), mais o contraste contra o fundo |
| `fotografia.py` | tira a «foto» de um banco de oscilografias (o que o programa conclui de cada registro: fases, trincas, falta, disparo…) e compara duas fotos. É a regressão contra o dado real: cada diferença depois de uma mudança tem de ter explicação. A foto tem dado real e fica em `docs-privados/`, fora do git |
| `comissionar.py` | o comissionamento em massa: roda as conferências de `tests/conferencias.py` (as mesmas do `test_comissionamento.py`, contra os números que o próprio relé gravou) sobre todo registro de uma pasta — um processo por registro — e grava o placar em CSV, uma linha por coisa conferida; `comparar` lista o que piorou entre duas rodadas. O placar tem dado real e fica em `docs-privados/comissionamento/` |
