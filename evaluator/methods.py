import re
from avocado.query import oldparsers as parsers
from avocado.models import DataConcept
from avocado.query.operators import registry as operators


# Operator mapping.
op_map_in = {
    'eq': 'exact',
    '-eq': '-exact',
}

op_map_out = {
    'exact': 'eq',
    '-exact': '-eq',
}

op_set = {'range', 'exact', 'gt', 'lt', 'gte', 'lte', 'in'}

punc_re = re.compile(r'[\/\'",]+')
space_re = re.compile(r'\s+')


def catalog():
    concepts_query = DataConcept.objects.published().filter(queryable=True)
    concepts = []

    for c in concepts_query:
        params = []

        for cf in c.concept_fields.select_related('field'):
            f = cf.field

            ops = []
            for k, _ in f.operators:
                o = operators.get(k)

                if o.lookup not in op_set:
                    continue

                k = op_map_out.get(k, k)
                ops.append({
                    'id': o.lookup,
                    'doc': o.verbose_name,
                    'multiple': hasattr(o, 'join_string'),
                })

            params.append({
                'id': f.pk,
                'label': str(cf),
                'type': f.simple_type,
                'doc': f.description,
                'operators': ops,
            })

        concepts.append({
            'id': c.pk,
            'label': str(c),
            'doc': c.description,
            'keywords': c.keywords,
            'params': params,
        })

    return {
        'version': '1.0.0',
        'concepts': concepts,
    }


def validate(expr):
    try:
        cxt = translate_expr(expr)
        return parsers.datacontext.parse(cxt), None
    except Exception as e:
        return None, e


def plan(expr, node):
    cxt = translate_expr(expr)
    queryset = node.apply().values_list('pk', flat=True).order_by()
    compiler = queryset.query.get_compiler(queryset.db)
    sql, params = compiler.as_sql()

    return {
        'context': cxt,
        'sql': sql,
        'params': params,
    }


def idents(expr, node):
    queryset = node.apply().values_list('pk', flat=True).order_by()
    compiler = queryset.query.get_compiler(queryset.db)

    return tuple(r[0] for r in compiler.results_iter())


def count(expr, node):
    return node.apply().count()


def translate_expr(expr):
    return translate_term(expr['term'])


def translate_term(term):
    ttype = term.get('type')

    # Corresponds to a branch.
    if ttype == 'branch':
        return {
            'type': term['operator'],
            'children': map(translate_term, term['terms']),
        }

    # Corresponds to a set of query conditions that are ANDed together.
    elif ttype == 'concept':
        # Wrap in a branch node.
        preds = []

        for param in term['params']:
            op, val = translate_op(param['operator'], param['value'])

            preds.append({
                'concept': term['concept'],
                'field': param['id'],
                'operator': op,
                'value': val,
            })

        return {
            'type': 'and',
            'children': preds,
        }

    raise ValueError('Unknown term type `{0}`'.format(ttype))


def translate_op(op, val):
    if op in op_map_in:
        op = op_map_in[op]

    if op == 'range':
        if 'gt' in val and 'lt' in val:
            return op, (val['gt'], val['lt'])

        if 'gt' in val:
            return 'gt', val['gt']

        if 'lt' in val:
            return 'lt', val['lt']

        raise ValueError('invalid range')

    return op, val
