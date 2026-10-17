"""(library) Load a notes_*.py file with a guard. Claude writes these files from untrusted course material, so they run
without imports, without _private/dunder names and with only data builtins. This keeps prompt-injected code away from
files, processes and the network; it is not a sandbox against a determined attacker."""
import ast, builtins, sys, types

SAFE_BUILTINS = {n: getattr(builtins, n) for n in ('dict', 'list', 'tuple', 'set', 'str', 'int', 'float', 'bool', 'len', 'range',
                                                    'enumerate', 'zip', 'sorted', 'reversed', 'min', 'max', 'sum', 'any', 'all',
                                                    'abs', 'round', 'isinstance', 'print')}

def load_notes(f):
    """-> namespace with NOTES, and SUMMARY / patch if the file defines them"""
    tree = ast.parse(open(f, encoding='utf-8').read(), f)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)) or \
                (isinstance(node, ast.Attribute) and node.attr.startswith('_')) or (isinstance(node, ast.Name) and node.id.startswith('_')):
            sys.exit(f'!! {f} line {node.lineno}: {type(node).__name__} is not allowed in a notes file (see references/notes_guide.md)')
    ns = {'__builtins__': SAFE_BUILTINS}
    exec(compile(tree, f, 'exec'), ns)
    return types.SimpleNamespace(**{k: ns[k] for k in ('NOTES', 'SUMMARY', 'patch') if k in ns})
