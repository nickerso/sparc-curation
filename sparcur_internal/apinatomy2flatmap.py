import json
from collections import defaultdict as base_dd


class defaultdict(base_dd):
    __str__ = dict.__str__
    __repr__ = dict.__repr__


CYCLE = 'CYCLE DETECTED'


def process_nodes(j, direction, verbose):
    nodes = {n['id']:n['lbl'] for n in j['nodes']}
    nodes[CYCLE] = CYCLE  # make sure we can look up the cycle
    edgerep = ['{} {} {}'.format(nodes[e['sub']], e['pred'], nodes[e['obj']]) for e in j['edges']]
    # note that if there are multiple relations between s & p then last one wins
    # sorting by the predicate should help keep it a bit more stable
    pair_rel = {(e['sub'], e['obj'])
                if direction == 'OUTGOING' else
                (e['obj'], e['sub']):
                e['pred'] + '>'
                if direction == 'OUTGOING' else
                '<' + e['pred']
                for e in sorted(j['edges'], key = lambda e: e['pred'])}

    objects = defaultdict(list)  # note: not all nodes are objects!
    for edge in j['edges']:
        objects[edge['obj']].append(edge['sub'])

    subjects = defaultdict(list)
    for edge in j['edges']:
        subjects[edge['sub']].append(edge['obj'])

    if direction == 'OUTGOING':  # flip for the tree
        objects, subjects = subjects, objects
    elif direction == 'BOTH':  # FIXME BOTH needs help!
        from pprint import pprint
        pprint(subjects)
        pprint(objects)
        pass

    ss, so = set(subjects), set(objects)
    roots = so - ss
    leaves = ss - so

    root = None
    if len(roots) == 1:
        root = next(iter(roots))
    else:
        root = '*ROOT*'
        nodes[root] = 'ROOT'
        objects[root] = list(roots)

    return nodes, objects, subjects, edgerep, root, roots, leaves, pair_rel


def print_node(indent, node, objects, nodes):
    for o in objects[node]:
        print(indent + '|--' + ((nodes[o] + " (" + o + ")" ) if nodes[o] else o))
        next_level = indent + '|   '
        print_node(next_level, o, objects, nodes)

def main(soma_processes_file=None, verbose=False):

    if verbose:
        print("Soma process filename: " + soma_processes_file)

    j = None
    with open(soma_processes_file) as json_file:
        soma_processes = json.load(json_file)
        j = dict(soma_processes)

    if verbose:
        print('raw input, number of nodes: ' + str(len(j['nodes'])))
        print('raw input, number of edges: ' + str(len(j['edges'])))

    # filter out owl:Nothing
    j['edges'] = [e for e in j['edges'] if 'owl:Nothing' not in e.values()]
    if verbose:
        print('owl:nothing, number of edges: ' + str(len(j['edges'])))

    # filter out has part meta edges
    j['edges'] = [e for e in j['edges'] if not
                    ('meta' in e and
                    'owlType' in e['meta'] and
                    'http://purl.obolibrary.org/obo/BFO_0000051' in e['meta']['owlType'])]
    if verbose:
        print('filter has part, number of nodes: ' + str(len(j['nodes'])))
        print('filter has part, number of edges: ' + str(len(j['edges'])))

    direction = 'INCOMING'
    (nodes, objects, subjects, edgerep, root, roots, leaves, pair_rel) = process_nodes(j, direction, verbose)

    if verbose:
        print('nodes, number of nodes: ' + str(len(nodes)))
        print('nodes, number of objects: ' + str(len(objects)))
        print('nodes, number of subjects: ' + str(len(subjects)))
        print('nodes, root: ' + str(root))
        print('nodes, number of roots: ' + str(len(roots)))
        print('nodes, number of pair_rel: ' + str(len(pair_rel)))

    print("UBERON:0000407")  # sympathetic trunk
    print_node('', 'UBERON:0000407', objects, nodes)

    print("FMA:7643")# Anterior root of first thoracic nerve
    print_node('', 'FMA:7643', objects, nodes)

    print("UBERON:0000057") # urethra
    print_node('', 'UBERON:0000057', objects, nodes)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Generate flatmap connectivity from ApiNATOMY KB (via JSON export from SciCrunch)')
    parser.add_argument('--soma-processes', metavar='path', required=True,
                        help='the path to the JSON export file')
    parser.add_argument('--verbose', help="increase output verbosity",
                        action="store_true")
    args = parser.parse_args()
    main(soma_processes_file = args.soma_processes, verbose = args.verbose)
