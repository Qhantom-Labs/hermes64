"""Data-only JSON Patch subset. No scripts or generated-file edits."""
import copy
import re
from .safety import fail, encode


def apply_patch(document, operations):
    if not isinstance(operations, list) or not 1 <= len(operations) <= 100:
        fail('patch', 'Patch must contain 1-100 operations')
    result = copy.deepcopy(document)
    for op in operations:
        if not isinstance(op, dict) or op.get('op') not in ('add', 'remove', 'replace', 'test'):
            fail('patch', 'Supported JSON Patch ops: add/remove/replace/test')
        expected = {'op', 'path'} if op['op'] == 'remove' else {'op', 'path', 'value'}
        if set(op) != expected:
            fail('patch', 'Invalid patch fields')
        path = op['path']
        if not isinstance(path, str) or not path.startswith('/') or len(path) > 512:
            fail('patch', 'Patch path must be a non-root JSON Pointer')
        if re.search(r'~(?![01])', path):
            fail('patch', 'Invalid JSON Pointer escape')
        parts = [x.replace('~1', '/').replace('~0', '~') for x in path[1:].split('/')]
        if parts[0] in ('contract_version', 'id'):
            fail('patch', 'Contract version and game identity are immutable')
        node = result
        for part in parts[:-1]:
            node = lookup(node, part)
        key, action = parts[-1], op['op']
        if isinstance(node, list):
            if key == '-' and action == 'add':
                index = len(node)
            elif re.fullmatch(r'0|[1-9][0-9]*', key):
                index = int(key)
            else:
                fail('patch', 'Invalid array index')
            if index > len(node) or (action != 'add' and index == len(node)):
                fail('patch', 'Array index outside range')
            if action == 'add':
                node.insert(index, copy.deepcopy(op['value']))
            elif action == 'remove':
                node.pop(index)
            elif action == 'replace':
                node[index] = copy.deepcopy(op['value'])
            elif encode(node[index]) != encode(op['value']):
                fail('patch_test', 'JSON Patch test failed at ' + path)
        elif isinstance(node, dict):
            if action != 'add' and key not in node:
                fail('patch', 'Object path absent: ' + path)
            if action in ('add', 'replace'):
                node[key] = copy.deepcopy(op['value'])
            elif action == 'remove':
                del node[key]
            elif encode(node[key]) != encode(op['value']):
                fail('patch_test', 'JSON Patch test failed at ' + path)
        else:
            fail('patch', 'Cannot descend through scalar')
    encode(result)
    return result


def lookup(node, part):
    if isinstance(node, dict) and part in node:
        return node[part]
    if isinstance(node, list) and re.fullmatch(r'0|[1-9][0-9]*', part) and int(part) < len(node):
        return node[int(part)]
    fail('patch', 'JSON Pointer parent absent')


def diff(before, after, path=''):
    if encode(before) == encode(after):
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        out = []
        for key in sorted(set(before) | set(after)):
            ptr = path + '/' + key.replace('~', '~0').replace('/', '~1')
            if key not in before or key not in after:
                out.append({'path': ptr, 'before': before.get(key), 'after': after.get(key),
                            'before_exists': key in before, 'after_exists': key in after})
            else:
                out.extend(diff(before[key], after[key], ptr))
        return out
    return [{'path': path or '/', 'before': before, 'after': after}]
