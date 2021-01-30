import json
from collections import defaultdict as base_dd
import networkx as nx


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


def print_node(indent, node, objects, nodes, pair_rel):
    for o in objects[node]:
        predicate = pair_rel[(node, o)]
        print(indent + '|--' + predicate + ((nodes[o] + " (" + o + ")" ) if nodes[o] else o))
        next_level = indent + '|   '
        print_node(next_level, o, objects, nodes, pair_rel)

def find_object(subject, predicate, objects, pair_rel):
    for o in objects[subject]:
        if pair_rel[(subject, o)] == predicate:
            return o
    return ''

def get_primary_info(id, nodes, objects, pair_rel):
    if id:
        # default name is the label if one is provided, otherwise the raw id is used
        name = nodes[id] if nodes[id] else id
        # if an external identifier is defined, that should be preferred
        external_id = find_object(id, 'apinatomy:external>', objects, pair_rel)
    else:
        name = "UNKOWN"
        external_id = "REALLY_UNKNOWN"
    return external_id, name

def get_primary_name(id, nodes, objects, pair_rel):
    external_id, name = get_primary_info(id, nodes, objects, pair_rel)
    if external_id:
        name = external_id + "(" + name + ")"
    return name

def get_flatmap_node(node, nodes, objects, pair_rel):
    flatmap_node = {
        'id': node,
    }
    # layered type or direct?
    layer = find_object(node, 'apinatomy:layerIn>', objects, pair_rel)
    if layer:
        clone = find_object(node, 'apinatomy:cloneOf>', objects, pair_rel)
        supertype = find_object(clone, 'apinatomy:supertype>', objects, pair_rel)
        external_id, name = get_primary_info(supertype, nodes, objects, pair_rel)
        # the external (ontology) ID for this node
        flatmap_node['external_id'] = external_id
        # the (potentially) human readable name for this node
        flatmap_node['name'] = name

        # the containing layer?
        external_id, name = get_primary_info(layer, nodes, objects, pair_rel)
        flatmap_node['layer_in'] = {
            'id': layer,
            'external_id': external_id,
            'name': name
        }
    else:
        external_id, name = get_primary_info(node, nodes, objects, pair_rel)
        # the external (ontology) ID for this node
        flatmap_node['external_id'] = external_id
        # the (potentially) human readable name for this node
        flatmap_node['name'] = name
    return flatmap_node

def trace_route_part(indent, part, nodes, objects, pair_rel, graph):
    # is there a flatmap "node" for this part?
    node = find_object(part, 'apinatomy:fasciculatesIn>', objects, pair_rel)
    if node:
        flatmap_node = get_flatmap_node(node, nodes, objects, pair_rel)
        s = flatmap_node['external_id'] + "(" + flatmap_node['name'] + ")"
        if 'layer_in' in flatmap_node:
            l = flatmap_node['layer_in']
            s = s + " [in layer: " + l['external_id'] + "(" + l['name'] + ")"
        print('{} {}'.format(indent, s))
        graph.add_node(node, **flatmap_node)
    # are the more parts in this route?
    next_part = find_object(part, 'apinatomy:next>', objects, pair_rel)
    if next_part:
        new_indent = '  ' + indent
        np = trace_route_part(new_indent, next_part, nodes, objects, pair_rel, graph)
        graph.add_edge(node, np)
    else:
        # if the chain merges into another chain?
        next_part = find_object(part, 'apinatomy:nextChainStartLevels>', objects, pair_rel)
        if next_part:
            new_indent = '  ' + indent
            np = trace_route_part(new_indent, next_part, nodes, objects, pair_rel, graph)
            graph.add_edge(node, np)
    return node

def trace_route(neuron, nodes, objects, pair_rel, graph):
    print("Neuron: {} ({})".format(nodes[neuron], neuron))
    conveys = find_object(neuron, 'apinatomy:conveys>', objects, pair_rel)
    if conveys == '':
        return
    target = find_object(conveys, 'apinatomy:target>', objects, pair_rel)
    target_root = find_object(target, 'apinatomy:rootOf>', objects, pair_rel)
    source = find_object(conveys, 'apinatomy:source>', objects, pair_rel)
    source_root = find_object(source, 'apinatomy:rootOf>', objects, pair_rel)
    print("  Conveys {} ==> {}".format(
        get_primary_name(source_root, nodes, objects, pair_rel),
        get_primary_name(target_root, nodes, objects, pair_rel)
    ))
    print("  Target: " + get_primary_name(target_root, nodes, objects, pair_rel))
    part = find_object(target, 'apinatomy:sourceOf>', objects, pair_rel)
    trace_route_part('    -->', part, nodes, objects, pair_rel, graph)
    print("  Source: " + get_primary_name(source_root, nodes, objects, pair_rel))
    part = find_object(source, 'apinatomy:sourceOf>', objects, pair_rel)
    trace_route_part('    -->', part, nodes, objects, pair_rel, graph)


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

    direction = 'OUTGOING'
    (nodes, objects, subjects, edgerep, root, roots, leaves, pair_rel) = process_nodes(j, direction, verbose)

    if verbose:
        print('nodes, number of nodes: ' + str(len(nodes)))
        print('nodes, number of objects: ' + str(len(objects)))
        print('nodes, number of subjects: ' + str(len(subjects)))
        print('nodes, root: ' + str(root))
        print('nodes, number of roots: ' + str(len(roots)))
        print('nodes, number of pair_rel: ' + str(len(pair_rel)))
        print('edgerep, number of edgereps: ' + str(len(edgerep)))

    # print("UBERON:0000407")  # sympathetic trunk
    # print_node('', 'UBERON:0000407', objects, nodes)
    #
    # print("FMA:7643")# Anterior root of first thoracic nerve
    # print_node('', 'FMA:7643', objects, nodes)
    #
    # print("UBERON:0000057") # urethra
    # print_node('', 'UBERON:0000057', objects, nodes)

    # print("UBERON:0016508") # pelvic ganglia
    # print_node('', 'UBERON:0016508', objects, nodes, pair_rel)

    neuron6_neuron2 = True
    neuron7_neuron3 = False

    if neuron6_neuron2:
        print("NLX:154731"  # soma
            + " ==> https://apinatomy.org/uris/models/keast-bladder/ids/snl26")
        print_node('', 'https://apinatomy.org/uris/models/keast-bladder/ids/snl26', objects, nodes, pair_rel)
        print_node('', 'https://apinatomy.org/uris/models/keast-bladder/ids/snl16', objects, nodes, pair_rel)
        print_node('', 'https://apinatomy.org/uris/models/keast-bladder/ids/sn-pg_2', objects, nodes, pair_rel)

    if neuron7_neuron3:
        print("NLX:154731"  # soma
            + " ==> https://apinatomy.org/uris/models/keast-bladder/ids/snl17")
        print_node('', 'https://apinatomy.org/uris/models/keast-bladder/ids/snl17', objects, nodes, pair_rel)
        print_node('', 'https://apinatomy.org/uris/models/keast-bladder/ids/snl27', objects, nodes, pair_rel)
        print_node('', 'https://apinatomy.org/uris/models/keast-bladder/ids/sn-img_3', objects, nodes, pair_rel)

    # root node will be soma (NLX:154731)
    graph = nx.DiGraph()
    print("Soma routes:")
    # eventually we would do all soma's
    for neuron in objects[root]:
        if neuron6_neuron2:
            if neuron == 'https://apinatomy.org/uris/models/keast-bladder/ids/snl26':
                trace_route(neuron, nodes, objects, pair_rel, graph)
            if neuron == 'https://apinatomy.org/uris/models/keast-bladder/ids/snl16':
                trace_route(neuron, nodes, objects, pair_rel, graph)
            if neuron == 'https://apinatomy.org/uris/models/keast-bladder/ids/sn-pg_2':
                trace_route(neuron, nodes, objects, pair_rel, graph)
        if neuron7_neuron3:
            if neuron == 'https://apinatomy.org/uris/models/keast-bladder/ids/snl17':
                trace_route(neuron, nodes, objects, pair_rel, graph)
            if neuron == 'https://apinatomy.org/uris/models/keast-bladder/ids/snl27':
                trace_route(neuron, nodes, objects, pair_rel, graph)
            if neuron == 'https://apinatomy.org/uris/models/keast-bladder/ids/sn-img_3':
                trace_route(neuron, nodes, objects, pair_rel, graph)

    import plotly.graph_objects as go
    import dash
    import dash_core_components as dcc
    import dash_html_components as html
    from addEdge import addEdge

    # Controls for how the graph is drawn
    nodeColor = 'Blue'
    nodeSize = 20
    lineWidth = 2
    lineColor = '#000000'

    # define the layout of the graph
    #pos = nx.spring_layout(graph)
    #pos = nx.planar_layout(graph, scale=2)
    pos = nx.kamada_kawai_layout(graph)
    for node in graph.nodes:
        graph.nodes[node]['pos'] = list(pos[node])

    # Make list of nodes for plotly
    node_x = []
    node_y = []
    node_labels = []
    node_text = []
    for node in graph.nodes():
        x, y = graph.nodes[node]['pos']
        node_x.append(x)
        node_y.append(y)
        # build the label for the node
        n = graph.nodes[node]
        label = \
            "<i>" + node + "</i><br />" + \
            n['external_id'] + "<i>" + n['name'] + "</i>"
        if 'layer_in' in n:
            l = n['layer_in']
            label = label + "<br />[[in layer: " + l['external_id'] + "(<i>" + l['name'] + "</i>)]]"
        node_labels.append(label)
        node_text.append(n['external_id'])

    # Make a list of edges for plotly, including line segments that result in arrowheads
    edge_x = []
    edge_y = []
    for edge in graph.edges():
        # addEdge(start, end, edge_x, edge_y, lengthFrac=1, arrowPos = None, arrowLength=0.025, arrowAngle = 30, dotSize=20)
        start = graph.nodes[edge[0]]['pos']
        end = graph.nodes[edge[1]]['pos']
        edge_x, edge_y = addEdge(start, end, edge_x, edge_y, .9, 'end', .04, 30, nodeSize)

    edge_trace = go.Scatter(x=edge_x, y=edge_y, line=dict(width=lineWidth, color=lineColor), hoverinfo='none',
                            mode='lines')

    node_trace = go.Scatter(x=node_x, y=node_y, mode='text', hoverinfo='text',
                            marker=dict(showscale=False, color=nodeColor, size=nodeSize))
    node_trace.hovertext = node_labels
    node_trace.text = node_text

    fig = go.Figure(data=[edge_trace, node_trace],
                    layout=go.Layout(
                        showlegend=False,
                        hovermode='closest',
                        margin=dict(b=20, l=5, r=5, t=40),
                        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False))
                    )

    # Note: if you don't use fixed ratio axes, the arrows won't be symmetrical
    fig.update_layout(yaxis=dict(scaleanchor="x", scaleratio=1), plot_bgcolor='rgb(255,255,255)')
    app = dash.Dash()
    app.layout = html.Div([dcc.Graph(figure=fig)])

    app.run_server(debug=True, use_reloader=False)

    # edge_x = []
    # edge_y = []
    # for edge in graph.edges():
    #     x0, y0 = pos[edge[0]]
    #     x1, y1 = pos[edge[1]]
    #     edge_x.append(x0)
    #     edge_x.append(x1)
    #     edge_x.append(None)
    #     edge_y.append(y0)
    #     edge_y.append(y1)
    #     edge_y.append(None)
    #
    # edge_trace = go.Scatter(
    #     x=edge_x, y=edge_y,
    #     line=dict(width=0.5, color='#888'),
    #     hoverinfo='none',
    #     mode='lines')
    #
    # node_x = []
    # node_y = []
    # node_text = []
    # for node in graph.nodes():
    #     x, y = pos[node]
    #     node_x.append(x)
    #     node_y.append(y)
    #     # build the label for the node
    #     n = graph.nodes[node]
    #     label = \
    #         "<i>" + node + "</i><br />" + \
    #         n['external_id'] + "<i>" + n['name'] + "</i>"
    #     if 'layer_in' in n:
    #         l = n['layer_in']
    #         label = label + "<br />[[in layer: " + l['external_id'] + "(<i>" + l['name'] + "</i>)]]"
    #     node_text.append(label)
    #
    # node_trace = go.Scatter(
    #     x=node_x, y=node_y,
    #     mode='markers',
    #     hoverinfo='text',
    #     marker=dict(
    #         showscale=False,
    #         # colorscale options
    #         #'Greys' | 'YlGnBu' | 'Greens' | 'YlOrRd' | 'Bluered' | 'RdBu' |
    #         #'Reds' | 'Blues' | 'Picnic' | 'Rainbow' | 'Portland' | 'Jet' |
    #         #'Hot' | 'Blackbody' | 'Earth' | 'Electric' | 'Viridis' |
    #         colorscale='YlGnBu',
    #         reversescale=True,
    #         color=[],
    #         size=10,
    #         colorbar=dict(
    #             thickness=15,
    #             title='Node Connections',
    #             xanchor='left',
    #             titleside='right'
    #         ),
    #         line_width=2))
    #
    # node_adjacencies = []
    # #node_text = []
    # for node, adjacencies in enumerate(graph.adjacency()):
    #     node_adjacencies.append(len(adjacencies[1]))
    #     #node_text.append('# of connections: '+str(len(adjacencies[1])))
    #
    # node_trace.marker.color = node_adjacencies
    # node_trace.text = node_text
    #
    # fig = go.Figure(data=[edge_trace, node_trace],
    #              layout=go.Layout(
    #                 title='<br>Network graph made with Python',
    #                 titlefont_size=16,
    #                 showlegend=False,
    #                 hovermode='closest',
    #                 margin=dict(b=20,l=5,r=5,t=40),
    #                 annotations=[
    #                     dict(
    #                         ax=x0[i], ay=y0[i], axref='x', ayref='y',
    #                         x=x1[i], y=y1[i], xref='x', yref='y',
    #                         showarrow=True, arrowhead=1 ) for i in range(0, len(x0))
    #                 ],
    #                 xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    #                 yaxis=dict(showgrid=False, zeroline=False, showticklabels=False))
    #                 )
    # fig.show()

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Generate flatmap connectivity from ApiNATOMY KB (via JSON export from SciCrunch)')
    parser.add_argument('--soma-processes', metavar='path', required=True,
                        help='the path to the JSON export file')
    parser.add_argument('--verbose', help="increase output verbosity",
                        action="store_true")
    args = parser.parse_args()
    main(soma_processes_file = args.soma_processes, verbose = args.verbose)
