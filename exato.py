"""Branch and bound exato para a Coloração Seletiva de Grafos (SGCP).

Ideia geral (estilo DSATUR com seleção):
  * cada nó da árvore atribui a um grupo ainda não atendido um par (vértice, cor);
  * o grupo ramificado é o mais restrito: o que tem menos cores viáveis (DSATUR);
  * cores são indistinguíveis, então só se abre UMA cor nova por nó (quebra de simetria);
  * limite superior (UB): melhor solução conhecida, iniciada com o guloso do Trabalho 1
    e melhorada pelo guloso iterado de Culberson;
  * limites inferiores (LB): clique máxima no grafo de grupos "totalmente adjacentes"
    (seus grupos recebem cores fixas 0, 1, ..., q-1, mais quebra de simetria) e limite
    por cobertura de cliques de vértices (limite de carga em redes ópticas);
  * estratégia híbrida: metade do tempo em B&B descendente (melhora o UB) e o resto em
    busca ascendente (alvo = LB, LB+1, ...), que prova limites inferiores maiores;
  * pré-processamento por dominância: se N(u) ⊆ N(v) dentro do mesmo grupo, v é descartado.

Conjuntos de vértices e de grupos são representados por inteiros usados como
vetores de bits (bit v ligado = vértice v no conjunto), o que torna as operações
de interseção e diferença rápidas em Python puro.
"""

import sys
import time

from sgcp import guloso_classes

try:
    _popcount = int.bit_count           # Python 3.10+
except AttributeError:                  # Python 3.9
    def _popcount(x):
        return bin(x).count('1')


class _TempoEsgotado(Exception):
    """Sinaliza que o limite de tempo foi atingido durante a busca."""


def _bits(x):
    """Itera os índices dos bits ligados de x."""
    while x:
        b = x & -x
        yield b.bit_length() - 1
        x ^= b


def mascaras_adjacencia(inst):
    """adjm[v] = vizinhos de v fora do seu grupo (arestas internas são irrelevantes)."""
    grupo_de, adj = inst['grupo_de'], inst['adj']
    adjm = [0] * (inst['n'] + 1)
    for v in range(1, inst['n'] + 1):
        m = 0
        for u in adj[v]:
            if grupo_de[u] != grupo_de[v]:
                m |= 1 << u
        adjm[v] = m
    return adjm


def reduzir_dominancia(inst, adjm):
    """Remove vértices dominados até não haver mais mudanças.

    u domina v (mesmo grupo) quando N(u) ⊆ N(v); se N(u) = N(v), fica o de menor id.
    Trocar v por u em qualquer solução mantém a coloração própria, então existe uma
    solução ótima só com vértices não dominados. Arestas para vértices removidos
    também deixam de importar e são apagadas, o que pode gerar novas dominâncias.
    Devolve (vertices_por_grupo, adjm_reduzida, removidos).
    """
    k = inst['k']
    verts = [None] + [list(inst['grupos'][g]) for g in range(1, k + 1)]
    adjm = list(adjm)
    removidos = 0
    mudou = True
    while mudou:
        mudou = False
        mortos = 0
        for g in range(1, k + 1):
            vivos = verts[g]
            if len(vivos) < 2:
                continue
            fica = []
            for v in vivos:
                dominado = False
                for u in vivos:
                    if u == v:
                        continue
                    if adjm[u] & ~adjm[v] == 0 and (adjm[u] != adjm[v] or u < v):
                        dominado = True
                        break
                if dominado:
                    mortos |= 1 << v
                else:
                    fica.append(v)
            if len(fica) < len(vivos):
                removidos += len(vivos) - len(fica)
                verts[g] = fica
                mudou = True
        if mortos:
            vivos_mask = ~mortos
            for v in range(1, inst['n'] + 1):
                adjm[v] &= vivos_mask
    return verts, adjm, removidos


def clique_de_grupos(k, verts, adjm, limite_nos=200_000):
    """Clique máxima (ou a maior encontrada no limite de nós) no grafo H de grupos,
    onde g ~ h quando todo vértice de g é adjacente a todo vértice de h.

    Grupos de uma clique de H precisam de cores distintas em qualquer seleção,
    logo o tamanho da clique é um limite inferior para o número de cores.
    """
    gm = [0] * (k + 1)
    for g in range(1, k + 1):
        for v in verts[g]:
            gm[g] |= 1 << v
    viz = [0] * (k + 1)
    for g in range(1, k + 1):
        for h in range(g + 1, k + 1):
            if all(gm[h] & ~adjm[v] == 0 for v in verts[g]):
                viz[g] |= 1 << h
                viz[h] |= 1 << g

    melhor = []
    nos = 0

    def expandir(atual, cand):
        nonlocal melhor, nos
        nos += 1
        if nos > limite_nos:
            return
        if not cand:
            if len(atual) > len(melhor):
                melhor = list(atual)
            return
        # ordena candidatos por grau em H (maiores primeiro) para achar cliques grandes cedo
        ordem = sorted(_bits(cand), key=lambda g: -_popcount(viz[g] & cand))
        for g in ordem:
            if len(atual) + _popcount(cand) <= len(melhor):
                return
            atual.append(g)
            expandir(atual, cand & viz[g])
            atual.pop()
            cand &= ~(1 << g)

    expandir([], sum(1 << g for g in range(1, k + 1)))
    return melhor, nos <= limite_nos


def limite_cobertura(n, k, verts, adjm):
    """Limite inferior por família de cliques de vértices.

    Seja F = {Q_1, ..., Q_t} uma família de cliques de G e w(v) o número de cliques de F
    que contêm v. Uma classe de cor é um conjunto independente, logo tem no máximo um
    vértice de cada Q_j e peso total (soma de w) no máximo t. Qualquer seleção tem peso
    pelo menos W = soma, sobre os grupos, de min_{v no grupo} w(v). Portanto o número
    de cores é pelo menos ceil(W / t). Em redes ópticas, as cliques correspondem aos
    enlaces e o limite é o de carga (total de enlaces usados / número de enlaces).

    As cliques candidatas são maximais, construídas de forma gulosa a partir de cada
    vértice. A família começa com todas elas e, em rodadas, perde as cliques cuja
    retirada aumenta a razão W / t (as que contribuem menos que a média W / t).
    """
    vivos = 0
    for g in range(1, k + 1):
        for v in verts[g]:
            vivos |= 1 << v
    grupo_de = [0] * (n + 1)
    for g in range(1, k + 1):
        for v in verts[g]:
            grupo_de[v] = g

    # cobertura gulosa das arestas por cliques maximais: enquanto v tiver uma aresta
    # v-u ainda fora de toda clique, cria uma clique que contém v e u
    candidatas = set()
    coberto = [0] * (n + 1)     # coberto[v] = vértices que já dividem uma clique com v
    for v in _bits(vivos):
        while True:
            livres = adjm[v] & vivos & ~coberto[v]
            if not livres:
                break
            u = (livres & -livres).bit_length() - 1
            q = (1 << v) | (1 << u)
            cand = adjm[v] & adjm[u] & vivos
            while cand:
                x = max(_bits(cand), key=lambda y: _popcount(adjm[y] & cand))
                q |= 1 << x
                cand &= adjm[x]
            candidatas.add(q)
            for x in _bits(q):
                coberto[x] |= q
    familia = [(q, list(_bits(q))) for q in candidatas]
    if not familia:
        return 0
    return max(_familia_direta(k, verts, grupo_de, familia, n),
               _familia_reversa(k, verts, grupo_de, familia, n))


def _familia_direta(k, verts, grupo_de, candidatas, n):
    """Escolha gulosa: acrescenta a clique de maior ganho em W enquanto W / t aumenta."""
    w = [0] * (n + 1)
    minimo = [0] * (k + 1)
    W = t = melhor = 0
    usadas = set()
    while True:
        melhor_ganho, melhor_i = 0, -1
        for i, (q, lista) in enumerate(candidatas):
            if i in usadas:
                continue
            ganho = 0
            for v in lista:
                g = grupo_de[v]
                ganho += min(w[u] + ((q >> u) & 1) for u in verts[g]) - minimo[g]
            if ganho > melhor_ganho:
                melhor_ganho, melhor_i = ganho, i
        if melhor_i < 0 or (t > 0 and melhor_ganho * t <= W):
            break
        usadas.add(melhor_i)
        for v in candidatas[melhor_i][1]:
            w[v] += 1
        for v in candidatas[melhor_i][1]:
            g = grupo_de[v]
            minimo[g] = min(w[u] for u in verts[g])
        W += melhor_ganho
        t += 1
        melhor = max(melhor, -(-W // t))
    return melhor


def _familia_reversa(k, verts, grupo_de, familia, n):
    """Começa com todas as cliques e retira as que contribuem menos que a média W / t."""
    w = [0] * (n + 1)
    for _, lista in familia:
        for v in lista:
            w[v] += 1

    def peso_total():
        return sum(min(w[u] for u in verts[g]) for g in range(1, k + 1))

    W, t = peso_total(), len(familia)
    melhor = -(-W // t)
    while t > 1:
        # perda de W ao retirar cada clique sozinha
        perdas = []
        for i, (q, lista) in enumerate(familia):
            perda = 0
            for v in lista:
                g = grupo_de[v]
                atual = min(w[u] for u in verts[g])
                perda += atual - min(w[u] - ((q >> u) & 1) for u in verts[g])
            perdas.append(perda)
        # retirar a clique i aumenta W / t quando perda_i < W / t
        fora = [i for i, p in enumerate(perdas) if p * t < W]
        if not fora:
            break
        # retira em lote, mas no máximo metade, para não remover demais de uma vez
        fora.sort(key=lambda i: perdas[i])
        fora = set(fora[:max(1, len(familia) // 2)])
        for i in fora:
            for v in familia[i][1]:
                w[v] -= 1
        familia = [c for i, c in enumerate(familia) if i not in fora]
        novo_W, novo_t = peso_total(), len(familia)
        if novo_t == 0:
            break
        W, t = novo_W, novo_t
        melhor = max(melhor, -(-W // t))
    return melhor


def guloso_iterado(k, verts, adjm, reps, cores, limite_s, lb=1, semente=0):
    """Melhora uma solução com o guloso iterado de Culberson adaptado à seleção.

    A cada iteração, as classes de cor da solução atual são reordenadas (inversa,
    maiores primeiro ou aleatória) e os grupos são recoloridos com first-fit nessa
    ordem. Em cada cor, o representante atual é testado antes dos outros vértices do
    grupo; com isso o número de cores nunca aumenta (argumento de Culberson: os grupos
    da j-ésima classe sempre cabem em uma das j primeiras cores).

    reps e cores seguem o formato do Trabalho 1 (k+1 posições, cores a partir de 1).
    Devolve (reps, cores) da melhor solução encontrada dentro de limite_s segundos.
    """
    import random
    rng = random.Random(semente)
    fim = time.perf_counter() + limite_s
    reps, cores = list(reps), list(cores)
    melhor = max(cores[1:])
    it = 0
    while time.perf_counter() < fim and melhor > lb:
        it += 1
        classes = {}
        for g in range(1, k + 1):
            classes.setdefault(cores[g], []).append(g)
        ordem = list(classes.values())
        modo = it % 3
        if modo == 0:
            ordem.reverse()
        elif modo == 1:
            ordem.sort(key=len, reverse=True)
        else:
            rng.shuffle(ordem)
        bloq = []                    # bloq[c] = vizinhos dos vértices na cor c
        novos_reps = [0] * (k + 1)
        novas_cores = [0] * (k + 1)
        for classe in ordem:
            for g in classe:
                atual = reps[g]
                tentativa = [atual] + [v for v in verts[g] if v != atual]
                feito = False
                for c in range(len(bloq)):
                    b = bloq[c]
                    for v in tentativa:
                        if not (b >> v) & 1:
                            bloq[c] = b | adjm[v]
                            novos_reps[g], novas_cores[g] = v, c + 1
                            feito = True
                            break
                    if feito:
                        break
                if not feito:
                    bloq.append(adjm[atual])
                    novos_reps[g], novas_cores[g] = atual, len(bloq)
        reps, cores = novos_reps, novas_cores
        melhor = min(melhor, len(bloq))
    return reps, cores


def branch_and_bound(inst, limite_s=None, estrategia='hibrida', tempo_iterado=5.0):
    """Resolve a SGCP de forma exata.

    limite_s: limite de tempo em segundos (None = sem limite). Se o limite for atingido,
    devolve a melhor solução encontrada e o limite inferior, com otimo = False.
    estrategia: 'descendente' (B&B que melhora o UB), 'ascendente' (testa alvo = LB,
    LB+1, ... até achar uma solução) ou 'hibrida' (metade do tempo descendente e o
    restante ascendente; sem limite de tempo equivale à descendente).
    tempo_iterado: tempo máximo (s) do guloso iterado que gera o UB inicial
    (no máximo 10% de limite_s).

    Devolve um dict com: representantes, cores (listas com k+1 posições, cores a partir
    de 1), n_cores, otimo, lb, ub_inicial, nos, tempo_ms, removidos, clique.
    """
    inicio = time.perf_counter()
    k = inst['k']
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 4 * k + 1000))

    adjm_original = mascaras_adjacencia(inst)
    verts, adjm, removidos = reduzir_dominancia(inst, adjm_original)
    # dentro de cada grupo, tenta primeiro os vértices de menor grau
    for g in range(1, k + 1):
        verts[g].sort(key=lambda v: (_popcount(adjm[v]), v))
    gm = [0] * (k + 1)
    for g in range(1, k + 1):
        for v in verts[g]:
            gm[g] |= 1 << v
    grau_g = [0] + [min(_popcount(adjm[v]) for v in verts[g]) for g in range(1, k + 1)]

    clique, clique_exata = clique_de_grupos(k, verts, adjm)
    lb_cobertura = limite_cobertura(inst['n'], k, verts, adjm)
    lb = lb_raiz = max(1, len(clique), lb_cobertura)
    fixa = {g: i for i, g in enumerate(clique)}   # grupo da clique -> cor fixa

    # limite superior inicial: heurística gulosa do Trabalho 1, melhorada pelo guloso
    # iterado (usa o grafo original, pois o representante pode ser um vértice dominado)
    reps0, cores0 = guloso_classes(inst)
    ub_guloso = max(cores0[1:])
    if ub_guloso > lb:
        t_ig = tempo_iterado if limite_s is None else min(tempo_iterado, 0.1 * limite_s)
        reps0, cores0 = guloso_iterado(k, inst['grupos'], adjm_original, reps0, cores0, t_ig, lb)
    best = max(cores0[1:])
    best_sol = (list(reps0), list(cores0))
    ub_inicial = best

    rep = [0] * (k + 1)
    col = [0] * (k + 1)
    bloqueado = [0] * (k + 2)    # bloqueado[c] = vizinhos dos vértices já na cor c
    nos = 0

    def busca(usadas, restantes):
        nonlocal best, best_sol, nos
        nos += 1
        if prazo is not None and nos & 63 == 0 and time.perf_counter() > prazo:
            raise _TempoEsgotado
        if usadas >= best or best <= lb:
            return
        if not restantes:
            best = usadas
            best_sol = (list(rep), [c + 1 for c in col])
            best_sol[1][0] = 0
            return

        pode_abrir = usadas + 1 < best    # abrir uma cor nova ainda melhora o UB?

        # escolhe o grupo mais restrito (DSATUR): menos cores viáveis e, no empate,
        # maior grau; cnt conta os pares (vértice, cor) viáveis, para podar e forçar
        escolhido, menor = 0, None
        for g in restantes:
            m = gm[g]
            if g in fixa:
                cnt = _popcount(m & ~bloqueado[fixa[g]])
                ncores = 1 if cnt else 0
            else:
                cnt = ncores = 0
                for c in range(usadas):
                    a = _popcount(m & ~bloqueado[c])
                    if a:
                        cnt += a
                        ncores += 1
                if pode_abrir:
                    cnt += len(verts[g])
                    ncores += 1
            if cnt == 0:
                return               # grupo sem opção: poda por inviabilidade
            chave = (ncores, -grau_g[g])
            if menor is None or chave < menor:
                escolhido, menor = g, chave
                if cnt == 1:
                    break

        g = escolhido
        resto = [h for h in restantes if h != g]
        cores_g = (fixa[g],) if g in fixa else range(usadas)
        candidatos = []
        for v in verts[g]:
            bit = 1 << v
            for c in cores_g:
                if not bloqueado[c] & bit:
                    candidatos.append((c, v))
        if g not in fixa and pode_abrir:
            for v in verts[g]:
                candidatos.append((usadas, v))   # cor nova (só uma, por simetria)

        for c, v in candidatos:
            nova = c == usadas
            if (usadas + 1 if nova else usadas) >= best or best <= lb:
                continue
            antigo = bloqueado[c]
            bloqueado[c] = antigo | adjm[v]
            rep[g], col[g] = v, c
            busca(usadas + 1 if nova else usadas, resto)
            bloqueado[c] = antigo
        rep[g] = col[g] = 0

    fim = None if limite_s is None else inicio + limite_s
    prazo = fim
    def busca_raiz():
        """Começa uma busca do zero. O estado é zerado porque uma busca interrompida
        pelo limite de tempo (exceção) não desfaz as atribuições que estavam em curso."""
        for i in range(len(bloqueado)):
            bloqueado[i] = 0
        for i in range(k + 1):
            rep[i] = col[i] = 0
        busca(len(clique), list(range(1, k + 1)))

    def descendente():
        """B&B clássico: cada solução encontrada reduz o UB e a busca continua.
        Devolve True se a árvore foi percorrida inteira (best é ótimo)."""
        try:
            busca_raiz()
            return True
        except _TempoEsgotado:
            return False

    def ascendente():
        """Para alvo = lb, lb+1, ..., best-1 pergunta "existe solução com alvo cores?".
        Cada busca que termina sem solução prova que o ótimo é maior que alvo.
        Devolve True se o ótimo foi provado."""
        nonlocal best, lb
        ub = best
        alvo = lb
        try:
            for alvo in range(lb, ub):
                best = alvo + 1          # aceita só soluções com no máximo alvo cores
                busca_raiz()
                if best <= alvo:         # achou: como alvo - 1 já foi refutado, é ótima
                    lb = best
                    return True
                best = ub
                lb = alvo + 1
            return True                  # todos os alvos abaixo de ub refutados
        except _TempoEsgotado:
            if best <= alvo:             # a solução saiu bem no fim do prazo
                lb = best
                return True
            best = ub                    # alvo não decidido: volta ao UB conhecido
            return False

    if best <= lb:
        provado = True
    elif estrategia == 'descendente':
        provado = descendente()
    elif estrategia == 'ascendente':
        provado = ascendente()
    else:  # híbrida: metade do tempo melhorando o UB, o resto provando o LB
        if fim is not None:
            prazo = inicio + (fim - inicio) / 2
        provado = descendente()
        prazo = fim
        if not provado and best > lb:
            provado = ascendente()
        provado = provado or best <= lb

    representantes, cores = best_sol
    otimo = provado or best <= lb
    return {
        'representantes': representantes,
        'cores': cores,
        'n_cores': best,
        'otimo': otimo,
        'lb': best if otimo else lb,
        'lb_raiz': lb_raiz,
        'ub_guloso': ub_guloso,
        'ub_inicial': ub_inicial,
        'nos': nos,
        'tempo_ms': (time.perf_counter() - inicio) * 1000,
        'removidos': removidos,
        'clique': len(clique),
        'lb_cobertura': lb_cobertura,
        'clique_exata': clique_exata,
    }
