"""Interface: escolhe uma instância, roda o branch and bound exato e a heurística do
Trabalho 1, mostra o relatório na tela e o salva em resultados/.

Uso:
  python main.py                                   # menu: conjunto e depois instância
  python main.py instancias/exemplo/toy.txt        # roda direto a instância indicada
  python main.py <arquivo> --limite 120            # limite de tempo do B&B em segundos
  python main.py <arquivo> --estrategia descendente
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from sgcp import ler_instancia, guloso_classes, validar
from exato import branch_and_bound

CONJUNTOS = ['exemplo', 'random', 'nsfnet', 'ring']
ESTRATEGIAS = ['hibrida', 'descendente', 'ascendente']


def escolher(titulo, opcoes):
    """Mostra as opções numeradas e devolve a escolhida."""
    print(f'\n{titulo}')
    for i, opcao in enumerate(opcoes, 1):
        print(f'  {i:3}. {opcao}')
    while True:
        resposta = input('Número: ').strip()
        if resposta.isdigit() and 1 <= int(resposta) <= len(opcoes):
            return opcoes[int(resposta) - 1]
        print(f'Digite um número de 1 a {len(opcoes)}.')


def menu():
    """Menu em dois níveis: conjunto e depois instância. Devolve o caminho do arquivo."""
    conjunto = escolher('Conjunto de instâncias:', CONJUNTOS)
    arquivos = sorted(Path('instancias', conjunto).glob('*.txt'))
    nome = escolher(f'Instâncias de {conjunto}:', [a.stem for a in arquivos])
    return Path('instancias', conjunto, nome + '.txt')


def densidade(inst):
    """Densidade do grafo: 2m / (n(n-1))."""
    n, m = inst['n'], inst['m']
    return 2 * m / (n * (n - 1)) if n > 1 else 0


def n_cores(cores):
    return len(set(cores[1:]))


def executar(inst, limite_s, estrategia):
    """Roda a heurística do Trabalho 1 e o B&B; valida as duas soluções."""
    inicio = time.perf_counter()
    reps_h, cores_h = guloso_classes(inst)
    ms_h = (time.perf_counter() - inicio) * 1000
    bb = branch_and_bound(inst, limite_s, estrategia)
    return {
        'heuristica': (reps_h, cores_h, ms_h, validar(inst, reps_h, cores_h)),
        'bb': bb,
        'erros_bb': validar(inst, bb['representantes'], bb['cores']),
    }


def relatorio(caminho, inst, res, limite_s, estrategia):
    """Monta o texto do relatório."""
    n, m, k = inst['n'], inst['m'], inst['k']
    bb, erros = res['bb'], res['erros_bb']
    _, cores_h, ms_h, erros_h = res['heuristica']

    def status(e):
        return 'válida' if not e else f'INVÁLIDA ({len(e)} erros; 1º: {e[0]})'

    limite = 'sem limite' if limite_s is None else f'{limite_s:g} s'
    linhas = [
        'Coloração Seletiva de Grafos (SGCP) - algoritmo exato (branch and bound)',
        f'Data: {datetime.now():%Y-%m-%d %H:%M:%S}',
        '',
        f'Instância: {inst["nome"]} ({caminho})',
        f'n = {n} vértices, m = {m} arestas, k = {k} grupos, densidade = {densidade(inst):.4f}',
        f'Estratégia: {estrategia}; limite de tempo: {limite}',
        '',
        f'{"Método":<28}{"Cores":>6}{"Tempo (ms)":>14}  Validação',
        f'{"Heurística (Trabalho 1)":<28}{n_cores(cores_h):>6}{ms_h:>14.3f}  {status(erros_h)}',
        f'{"Branch and bound":<28}{bb["n_cores"]:>6}{bb["tempo_ms"]:>14.3f}  {status(erros)}',
        '',
        'Branch and bound:',
        f'  ótimo provado: {"sim" if bb["otimo"] else "não (limite de tempo atingido)"}',
        f'  limite inferior final: {bb["lb"]}   limite superior final: {bb["n_cores"]}',
        f'  limite inferior na raiz: {bb["lb_raiz"]} (clique de grupos = {bb["clique"]}, '
        f'cobertura por cliques = {bb["lb_cobertura"]})',
        f'  UB inicial: guloso = {bb["ub_guloso"]}, após guloso iterado = {bb["ub_inicial"]}',
        f'  vértices removidos por dominância: {bb["removidos"]}',
        f'  nós explorados: {bb["nos"]}',
    ]
    if bb['otimo']:
        linhas.append(f'  gap da heurística para o ótimo: {n_cores(cores_h) - bb["n_cores"]} cor(es)')
    else:
        gap = 100 * (bb['n_cores'] - bb['lb']) / bb['lb']
        linhas.append(f'  gap entre UB e LB: {gap:.2f}%')

    if erros:
        linhas += ['', 'A solução do B&B não passou pelo validador.']
        return '\n'.join(linhas)

    representantes, cores = bb['representantes'], bb['cores']
    linhas += ['', 'Melhor solução (branch and bound)',
               f'Valor (número de cores = trabalhadores): {n_cores(cores)}',
               '', f'{"Grupo":>6}{"Representante":>15}{"Cor":>6}']
    for g in range(1, k + 1):
        linhas.append(f'{g:>6}{representantes[g]:>15}{cores[g]:>6}')
    linhas += ['', 'Tarefas (vértices) de cada trabalhador (cor):']
    tarefas = {}
    for g in range(1, k + 1):
        tarefas.setdefault(cores[g], []).append(representantes[g])
    for cor in sorted(tarefas):
        qtd = len(tarefas[cor])
        lista = ', '.join(str(v) for v in tarefas[cor])
        linhas.append(f'  Trabalhador {cor} ({qtd} {"tarefa" if qtd == 1 else "tarefas"}): {lista}')
    return '\n'.join(linhas)


def main():
    parser = argparse.ArgumentParser(description='SGCP: branch and bound exato.')
    parser.add_argument('instancia', nargs='?', help='arquivo da instância (sem ele, abre o menu)')
    parser.add_argument('--limite', type=float, default=60,
                        help='limite de tempo do B&B em segundos (0 = sem limite; padrão 60)')
    parser.add_argument('--estrategia', choices=ESTRATEGIAS, default='hibrida')
    args = parser.parse_args()

    if args.instancia:
        caminho = Path(args.instancia)
        if not caminho.is_file():
            sys.exit(f'Arquivo não encontrado: {caminho}')
    else:
        caminho = menu()
    limite = args.limite if args.limite > 0 else None

    inst = ler_instancia(caminho)
    print(f'\nResolvendo {inst["nome"]} (limite: {"nenhum" if limite is None else f"{limite:g} s"})...')
    texto = relatorio(caminho, inst, executar(inst, limite, args.estrategia), limite, args.estrategia)
    print('\n' + texto)

    Path('resultados').mkdir(exist_ok=True)
    saida = Path('resultados', f'{inst["nome"]}_{datetime.now():%Y%m%d-%H%M%S}.txt')
    saida.write_text(texto + '\n', encoding='utf-8')
    print(f'\nRelatório salvo em {saida}')


if __name__ == '__main__':
    main()
