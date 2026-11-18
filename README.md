# Coloração Seletiva de Grafos (SGCP): algoritmo exato

Trabalho 2 de Projeto e Análise de Algoritmos (BCC 2026.2): algoritmo exato do tipo
*branch and bound* para a Coloração Seletiva de Grafos, também conhecida como
*Partition Coloring Problem* (PCP). Os resultados são comparados com a heurística
gulosa do Trabalho 1 e com os valores ótimos publicados na literatura.

**Problema.** Dado um grafo G = (V, E) com os vértices divididos em k grupos,
escolher exatamente um vértice (representante) de cada grupo e colorir os
escolhidos com o menor número de cores, sem que dois vizinhos tenham a mesma cor.
Na metáfora do enunciado, os vértices são tarefas, os grupos são categorias, as
arestas ligam tarefas no mesmo horário e as cores são trabalhadores.

## Requisitos

Python 3.9 ou mais recente (testado nas versões 3.12 e 3.14). Só a biblioteca padrão é usada:
não há nada para instalar. Os comandos abaixo são executados na pasta do projeto.
No Linux/macOS, use `python3` no lugar de `python`.

## Como executar

```bash
python main.py                                  # menu: escolhe o conjunto e depois a instância
python main.py instancias/exemplo/toy.txt       # roda direto a instância indicada
python main.py instancias/random/n80p5t2s1.txt --limite 120   # limite de tempo em segundos
python experimentos.py --limite 60 --processos 6               # todas as instâncias + tabelas
python -m unittest testes                       # testes (inclui comparação com força bruta)
```

`main.py` roda a heurística do Trabalho 1 e o branch and bound na instância escolhida
e mostra um relatório com os dados da instância, o número de cores e o tempo de cada
método, a validação, os limites inferior e superior do B&B, se o ótimo foi provado e
a melhor solução (representante e cor de cada grupo, tarefas de cada trabalhador)
com o seu valor. O mesmo relatório é salvo em
`resultados/<instancia>_<AAAAMMDD-HHMMSS>.txt`.

Opções de `main.py`: `--limite S` (segundos; `0` = sem limite; padrão 60) e
`--estrategia {hibrida,descendente,ascendente}` (padrão `hibrida`).

`experimentos.py` roda o B&B e a heurística em todas as instâncias da literatura e
grava `resultados/bb.csv` (uma linha por instância, gravada assim que ela termina) e
`resultados/tabela_bb.md` (resumo por conjunto e tabela completa). Opções:
`--limite`, `--estrategia`, `--processos N` (instâncias em paralelo),
`--conjuntos random nsfnet ring` e `--continuar` (retoma uma execução interrompida).

## Algoritmo

Implementado em `exato.py` (`branch_and_bound`).

1. **Redução por dominância.** Se dois vértices u e v estão no mesmo grupo e
   N(u) ⊆ N(v) (vizinhos fora do grupo), v pode ser descartado: trocar v por u em
   qualquer solução mantém a coloração própria. A redução é repetida até não mudar.
2. **Limites inferiores na raiz.**
   - *Clique de grupos*: no grafo H em que dois grupos são vizinhos quando todo
     vértice de um é adjacente a todo vértice do outro, uma clique de H exige cores
     distintas. Os grupos dessa clique recebem as cores 0, 1, …, q−1 (quebra de simetria).
   - *Cobertura por cliques*: para uma família de t cliques de G, uma classe de cor
     tem no máximo um vértice de cada clique; se w(v) é o número de cliques que contêm
     v, o número de cores é pelo menos ⌈Σ_grupos min_v w(v) / t⌉. Nas instâncias de
     redes ópticas, as cliques são os enlaces e este é o limite de carga.
3. **Limite superior inicial.** Heurística gulosa do Trabalho 1, melhorada pelo
   guloso iterado de Culberson (reordena as classes de cor e recolore com first-fit,
   o que nunca aumenta o número de cores). Ele para ao atingir o limite inferior,
   após 20000 iterações seguidas sem melhora ou após 5 s (no máximo 10% do limite).
4. **Branch and bound (estilo DSATUR).** Cada nó atribui um par (vértice, cor) a um
   grupo ainda não atendido. O grupo escolhido é o que tem menos cores viáveis
   (desempate: maior grau). Só uma cor nova é aberta por nó, pois cores ainda não
   usadas são equivalentes. Um ramo é podado quando já usa tantas cores quanto a
   melhor solução ou quando algum grupo fica sem nenhum par viável.
5. **Estratégias.** `descendente`: B&B clássico, que melhora o limite superior.
   `ascendente`: pergunta "existe solução com c cores?" para c = LB, LB+1, …; cada
   resposta negativa prova um limite inferior maior. `hibrida` (padrão): metade do
   tempo descendente e o restante ascendente.

Conjuntos de vértices são representados por inteiros usados como vetores de bits,
o que torna interseções e diferenças rápidas em Python puro. Toda solução passa
pelo validador (`validar`, em `sgcp.py`) antes de ser mostrada ou salva. Quando o
limite de tempo é atingido, o algoritmo devolve a melhor solução encontrada e o
maior limite inferior provado, e informa que o ótimo não foi provado.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `exato.py` | branch and bound, limites inferiores, redução e guloso iterado |
| `sgcp.py` | leitura de instância, heurísticas do Trabalho 1 e validador |
| `main.py` | interface: escolha da instância e relatório |
| `experimentos.py` | execução em lote e tabelas |
| `testes.py` | testes (`unittest`): toy, 300 instâncias aleatórias contra força bruta, limites com tempo curto |
| `instancias/` | casos de teste: `exemplo/` (toy), `random/` (80), `nsfnet/` (50), `ring/` (150) |
| `resultados/` | relatórios e tabelas gerados |
| `relatorio/` | relatório em LaTeX (modelo da SBC): `relatorio.tex` e `referencias.bib` |

## Instâncias

As mesmas do Trabalho 1, vindas do repositório de A. Santini
(<https://github.com/alberto-santini/selective-graph-colouring>, licença GPL-3.0),
que acompanha Furini, Malaguti & Santini (2018). Origem, formato e observações
estão em [`instancias/README.md`](instancias/README.md); os valores ótimos ou
melhores conhecidos estão em `instancias/referencias.csv`. Formato dos arquivos:

```text
# comentários / metadados
p edge <n> <m> <k>
c <id_grupo> <v1> <v2> ...     # um grupo por linha ("c" é grupo, não comentário)
e <u> <v>                      # uma aresta por linha
```

Vértices e grupos são numerados a partir de 1. Para testar outra instância, basta
criar um arquivo nesse formato e passar o caminho para `main.py`.
