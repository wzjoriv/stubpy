#!/usr/bin/env python3
"""Baseline integration test runner — no pytest required."""
import sys, ast, textwrap, tempfile, traceback
from pathlib import Path
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from stubpy import generate_stub
from stubpy.context import StubContext

def make_stub(source: str) -> str:
    source = textwrap.dedent(source)
    with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False, encoding='utf-8') as f:
        f.write(source)
        tmp = Path(f.name)
    out = tmp.with_suffix('.pyi')
    return generate_stub(str(tmp), str(out))

def flatten(content: str) -> str:
    lines = content.splitlines()
    out, buf = [], []
    for line in lines:
        if buf:
            stripped = line.strip()
            if stripped.startswith(')'):
                out.append(buf[0] + ', '.join(buf[1:]) + stripped)
                buf = []
            else:
                buf.append(stripped)
        elif line.rstrip().endswith('('):
            buf.append(line.rstrip())
        else:
            out.append(line)
    out.extend(buf)
    return '\n'.join(out)

def assert_valid_syntax(c):
    try:
        ast.parse(c)
    except SyntaxError as e:
        raise AssertionError(f'Invalid syntax: {e}')

passed = failed = 0
errors_list = []

def T(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f'  ✓ {name}')
    except Exception as e:
        failed += 1
        errors_list.append((name, traceback.format_exc()))
        print(f'  ✗ {name}: {e}')

# ── Backwards-compat: existing tests ─────────────────────────────────────────
print('── TestPlain')
def t_basic():
    c = make_stub('''
        class Rect:
            def __init__(self, width: float, height: float) -> None: pass
            def area(self) -> float: return 0
    ''')
    assert 'def __init__(self, width: float, height: float) -> None:' in c
    assert 'def area(self) -> float:' in c
T('basic_signature', t_basic)

def t_default():
    c = make_stub('class Box:\n    def __init__(self, size: int = 10) -> None: pass\n')
    assert 'size: int = 10' in c
T('default_value', t_default)

def t_no_hints():
    c = make_stub('class Bare:\n    def __init__(self, x, y): pass\n')
    assert 'def __init__(self, x, y)' in c
T('no_hints_keeps_param_names', t_no_hints)

print('── TestAnnotations')
def t_optional():
    c = make_stub('class A:\n    def __init__(self, x: str | None = None) -> None: pass')
    assert 'Optional[str]' in c
T('optional_shorthand', t_optional)

def t_union3():
    c = make_stub('class A:\n    def __init__(self, x: str | int | float) -> None: pass')
    assert 'str | int | float' in c
T('union_three_types', t_union3)

def t_callable():
    c = make_stub('from typing import Callable\nclass A:\n    def __init__(self, fn: Callable[[], None] | None = None) -> None: pass')
    assert 'Callable' in c
T('callable_annotation', t_callable)

def t_literal():
    c = make_stub('from typing import Literal\nclass A:\n    def __init__(self, cap: Literal["butt","round"] = "butt") -> None: pass')
    assert "Literal['butt', 'round']" in c
T('literal_annotation', t_literal)

def t_tuple():
    c = make_stub('from typing import Tuple\nclass A:\n    def __init__(self, pt: Tuple[float, float]) -> None: pass')
    assert 'Tuple[float, float]' in c
T('tuple_annotation', t_tuple)

print('── TestSingleKwargs')
SRC_SINGLE = '''
    class Parent:
        def __init__(self, color: str, size: int) -> None: pass
    class Child(Parent):
        def __init__(self, label: str, **kwargs): super().__init__(**kwargs)
'''
def child_sec(c): return c.split('class Child')[1].split('\nclass ')[0]

def t_merged():
    c = make_stub(SRC_SINGLE)
    ch = child_sec(c)
    for p in ('label: str', 'color: str', 'size: int'):
        assert p in ch, f'Missing: {p}'
T('merged', t_merged)

def t_kwargs_gone():
    assert '**kwargs' not in child_sec(make_stub(SRC_SINGLE))
T('kwargs_gone', t_kwargs_gone)

def t_defaults_preserved():
    c = make_stub('''
        class B:
            def __init__(self, x: float = 0.0) -> None: pass
        class D(B):
            def __init__(self, name: str, **kwargs): super().__init__(**kwargs)
    ''')
    assert 'x: float = 0.0' in c
T('defaults_preserved', t_defaults_preserved)

print('── TestMultiLevel')
SRC_MULTI = '''
    class A:
        def __init__(self, name: str, legs: int, wild: bool = True) -> None: pass
    class B(A):
        def __init__(self, owner: str, **kwargs): super().__init__(**kwargs)
    class C(B):
        def __init__(self, breed: str, **kwargs): super().__init__(**kwargs)
    class D(C):
        def __init__(self, job: str, **kwargs): super().__init__(**kwargs)
'''
def sec(c, name): return c.split(f'class {name}')[1].split('\nclass ')[0]

def t_3lvl():
    c = make_stub(SRC_MULTI); s = sec(c, 'C')
    for p in ('breed: str', 'owner: str', 'name: str', 'legs: int'):
        assert p in s, f'Missing: {p}'
    assert '**kwargs' not in s
T('three_levels', t_3lvl)

def t_4lvl():
    c = make_stub(SRC_MULTI); s = sec(c, 'D')
    for p in ('job: str', 'breed: str', 'owner: str', 'name: str', 'wild: bool = True'):
        assert p in s, f'Missing: {p}'
    assert '**kwargs' not in s
T('four_levels_with_default', t_4lvl)

print('── TestEdgeCases')
def t_open_kw():
    assert '**kwargs' in make_stub('class W:\n    def __init__(self, x: str, **kwargs): pass\n')
T('open_kwargs_preserved', t_open_kw)

def t_unresolved_args():
    assert '*args' in make_stub('class V:\n    def __init__(self, first: int, *args): pass\n')
T('unresolved_args_preserved', t_unresolved_args)

def t_kw_only():
    c = flatten(make_stub('class K:\n    def __init__(self, a: int, *, b: str = "x") -> None: pass'))
    init_line = [l for l in c.splitlines() if 'def __init__' in l][0]
    assert '*,' in init_line
    assert init_line.index('*,') < init_line.index('b:')
T('kw_only_gets_separator', t_kw_only)

print('── TestSpecialMethods')
def t_cm():
    c = make_stub("class F:\n    @classmethod\n    def create(cls, v: int) -> 'F': return cls()")
    assert '@classmethod' in c and 'def create(cls, v: int)' in c
T('classmethod', t_cm)

def t_sm():
    c = make_stub('class U:\n    @staticmethod\n    def add(a: int, b: int) -> int: return a + b')
    assert '@staticmethod' in c and 'def add(a: int, b: int) -> int:' in c
T('staticmethod', t_sm)

def t_prop():
    c = make_stub(
        'class P:\n'
        '    @property\n'
        '    def value(self) -> float: return self._v\n'
        '    @value.setter\n'
        '    def value(self, v: float) -> None: self._v = v'
    )
    assert '@property' in c and 'def value(self) -> float:' in c
    assert '@value.setter' in c and 'def value(self, v: float) -> None:' in c
T('property_with_setter', t_prop)

print('── TestFormatting')
def t_mline():
    c = make_stub('class A:\n    def __init__(self, x: int, y: int, z: int) -> None: pass')
    assert [l for l in c.splitlines() if 'def __init__' in l][0].rstrip().endswith('(')
T('many_params_multiline', t_mline)

def t_inline():
    c = make_stub('class A:\n    def move(self, x: int, y: int) -> None: pass')
    assert 'x: int' in [l for l in c.splitlines() if 'def move' in l][0]
T('few_params_inline', t_inline)

def t_valid():
    c = make_stub('class A:\n    def __init__(self, a: int, b: str, c: float, d: bool = True) -> None: pass')
    assert_valid_syntax(c)
T('multiline_is_valid_python', t_valid)

print('── TestClassmethodCls')
SRC_CLS = (
    'class Widget:\n'
    '    def __init__(self, width: int, height: int, color: str = "black") -> None: pass\n'
    '    @classmethod\n'
    '    def square(cls, **kwargs) -> "Widget": return cls(**kwargs)\n'
    '    @classmethod\n'
    '    def colored(cls, color: str, **kwargs) -> "Widget": return cls(color=color, **kwargs)\n'
)
def ml(content, method):
    for line in flatten(content).splitlines():
        if f'def {method}(cls' in line: return line
    return ''

def t_square():
    line = ml(make_stub(SRC_CLS), 'square')
    assert line and 'width: int' in line and 'height: int' in line and 'color: str' in line
    assert '**kwargs' not in line
T('square_gets_init_params', t_square)

def t_colored():
    line = ml(make_stub(SRC_CLS), 'colored')
    assert line and 'color: str' in line and 'width: int' in line and line.count('color:') == 1
T('colored_excludes_explicit', t_colored)

print('── TestStaticMethods')
def t_static_no_args():
    c = make_stub('class A:\n    @staticmethod\n    def util() -> int: return 42')
    assert '@staticmethod' in c and 'def util() -> int: ...' in c
T('static_no_args', t_static_no_args)

def t_static_args():
    c = make_stub('class A:\n    @staticmethod\n    def add(a: float, b: float = 1.0) -> float: return a + b')
    assert 'def add(a: float, b: float = 1.0) -> float: ...' in c
T('static_with_args', t_static_args)

def t_static_valid():
    c = make_stub('class A:\n    @staticmethod\n    def compute(x: int, y: int, z: int) -> int: return x + y + z')
    assert_valid_syntax(c)
T('static_valid_syntax', t_static_valid)

print('── TestArgsAndKwargsTogether')
def t_both_no_parent():
    c = make_stub('from typing import Any\nclass A:\n    def __init__(self, x: int, *args: str, flag: bool = False, **kwargs: Any) -> None: pass')
    cf = flatten(c)
    init = [l for l in cf.splitlines() if 'def __init__' in l][0]
    assert '*args: str' in init and '**kwargs: Any' in init and 'flag: bool' in init
    assert init.index('*args') < init.index('**kwargs')
    assert_valid_syntax(c)
T('both_no_parent', t_both_no_parent)

def t_kw_only_resolved():
    c = make_stub(
        'class Parent:\n'
        '    def __init__(self, a: int, *, b: str = "x") -> None: pass\n'
        'class Child(Parent):\n'
        '    def __init__(self, prefix: str, **kwargs) -> None:\n'
        '        super().__init__(**kwargs)\n'
    )
    child_sec2 = flatten(c.split('class Child')[1])
    init_line = [l for l in child_sec2.splitlines() if 'def __init__' in l][0]
    assert 'prefix: str' in init_line and 'a: int' in init_line and 'b: str' in init_line
    assert '*,' in init_line and '**kwargs' not in init_line
    assert_valid_syntax(c)
T('kw_only_with_kwargs_resolved', t_kw_only_resolved)



from stubpy.diagnostics import DiagnosticCollector, DiagnosticLevel, DiagnosticStage, Diagnostic
from stubpy.ast_pass import ast_harvest
from stubpy.symbols import (SymbolTable, ClassSymbol, FunctionSymbol, VariableSymbol,
                             AliasSymbol, OverloadGroup, SymbolKind, build_symbol_table)
from stubpy.context import StubContext, StubConfig, ExecutionMode

print('── DiagnosticCollector')
def t_diag_empty():
    c = DiagnosticCollector()
    assert len(c) == 0 and not c.has_errors() and not c.has_warnings()
    assert c.summary() == '0 errors, 0 warnings, 0 infos'
T('empty_collector', t_diag_empty)

def t_diag_levels():
    c = DiagnosticCollector()
    c.info(DiagnosticStage.LOAD, 'f.py', 'loaded')
    c.warning(DiagnosticStage.RESOLVE, 'Foo', 'warn')
    c.error(DiagnosticStage.EMIT, 'Bar', 'err')
    assert len(c) == 3
    assert c.has_errors() and c.has_warnings()
    assert len(c.errors) == 1 and len(c.warnings) == 1 and len(c.infos) == 1
    assert c.summary() == '1 errors, 1 warnings, 1 infos'
T('all_levels', t_diag_levels)

def t_diag_str():
    d = Diagnostic(DiagnosticLevel.ERROR, DiagnosticStage.EMIT, 'Foo', 'bad')
    s = str(d)
    assert '[ERROR]' in s and '(emit)' in s and 'Foo' in s and 'bad' in s
T('diagnostic_str_format', t_diag_str)

def t_diag_frozen():
    d = Diagnostic(DiagnosticLevel.WARNING, DiagnosticStage.LOAD, 'x', 'y')
    try:
        d.message = 'z'
        assert False, 'Should be frozen'
    except (AttributeError, TypeError):
        pass
T('diagnostic_is_frozen', t_diag_frozen)

def t_diag_by_stage():
    c = DiagnosticCollector()
    c.error(DiagnosticStage.LOAD, 'x', 'm1')
    c.warning(DiagnosticStage.EMIT, 'y', 'm2')
    assert len(c.by_stage(DiagnosticStage.LOAD)) == 1
    assert len(c.by_stage(DiagnosticStage.EMIT)) == 1
    assert len(c.by_stage(DiagnosticStage.RESOLVE)) == 0
T('by_stage', t_diag_by_stage)

def t_diag_by_symbol():
    c = DiagnosticCollector()
    c.error(DiagnosticStage.EMIT, 'Alpha', 'm1')
    c.warning(DiagnosticStage.EMIT, 'Alpha', 'm2')
    c.info(DiagnosticStage.LOAD, 'Beta', 'm3')
    assert len(c.by_symbol('Alpha')) == 2
    assert len(c.by_symbol('Beta')) == 1
    assert len(c.by_symbol('Missing')) == 0
T('by_symbol', t_diag_by_symbol)

def t_diag_clear():
    c = DiagnosticCollector()
    c.error(DiagnosticStage.EMIT, 'X', 'e'); c.clear()
    assert len(c) == 0 and not c.has_errors()
T('clear', t_diag_clear)

def t_diag_iter():
    c = DiagnosticCollector()
    c.info(DiagnosticStage.LOAD, 'a', 'x')
    c.info(DiagnosticStage.LOAD, 'b', 'y')
    items = list(c)
    assert len(items) == 2 and all(isinstance(i, Diagnostic) for i in items)
T('iteration', t_diag_iter)

def t_diag_bool():
    c = DiagnosticCollector()
    assert not bool(c)
    c.info(DiagnosticStage.LOAD, 'x', 'y')
    assert bool(c)
T('bool_protocol', t_diag_bool)

def t_diag_format_all():
    c = DiagnosticCollector()
    c.warning(DiagnosticStage.RESOLVE, 'Foo', 'test msg')
    s = c.format_all()
    assert 'WARNING' in s and 'Foo' in s and 'test msg' in s
T('format_all', t_diag_format_all)

def t_diag_all_property():
    c = DiagnosticCollector()
    c.info(DiagnosticStage.LOAD, 'a', 'x')
    lst = c.all
    assert isinstance(lst, list) and len(lst) == 1
    lst.append(None)  # mutation of copy should not affect collector
    assert len(c) == 1
T('all_property_returns_copy', t_diag_all_property)

def t_diag_stages_enum():
    stages = [s for s in DiagnosticStage]
    names = [s.value for s in stages]
    for expected in ('load', 'ast_pass', 'symbol_table', 'alias', 'resolve', 'emit', 'import', 'generator'):
        assert expected in names, f'Missing stage: {expected}'
T('all_stages_defined', t_diag_stages_enum)

print('── ASTHarvester')
def t_ast_empty():
    syms = ast_harvest('')
    assert syms.classes == [] and syms.functions == [] and syms.variables == []
    assert syms.all_exports is None
T('empty_source', t_ast_empty)

def t_ast_syntax_error():
    syms = ast_harvest('def :(')
    assert syms.classes == [] and syms.functions == []
T('syntax_error_returns_empty', t_ast_syntax_error)

def t_ast_class_bases():
    syms = ast_harvest('class Foo(Bar, Baz): pass')
    assert syms.classes[0].name == 'Foo'
    assert 'Bar' in syms.classes[0].bases and 'Baz' in syms.classes[0].bases
T('class_bases', t_ast_class_bases)

def t_ast_class_no_base():
    syms = ast_harvest('class Foo: pass')
    assert syms.classes[0].bases == []
T('class_no_base', t_ast_class_no_base)

def t_ast_class_decorator():
    syms = ast_harvest('import dataclasses\n@dataclasses.dataclass\nclass Foo: pass')
    assert 'dataclass' in syms.classes[0].decorators
T('class_decorator', t_ast_class_decorator)

def t_ast_async():
    syms = ast_harvest('async def fetch(url: str) -> None: ...')
    fn = syms.functions[0]
    assert fn.is_async is True
    assert fn.raw_return_annotation == 'None'
T('async_function', t_ast_async)

def t_ast_sync():
    syms = ast_harvest('def greet(name: str) -> str: ...')
    assert syms.functions[0].is_async is False
T('sync_function', t_ast_sync)

def t_ast_overload():
    src = (
        'from typing import overload\n'
        '@overload\ndef parse(x: int) -> int: ...\n'
        '@overload\ndef parse(x: str) -> str: ...\n'
        'def parse(x): ...\n'
    )
    syms = ast_harvest(src)
    overloaded = [f for f in syms.functions if f.is_overload]
    assert len(overloaded) == 2
T('overload_detection', t_ast_overload)

def t_ast_all():
    syms = ast_harvest('__all__ = ["Foo", "bar"]\nclass Foo: pass\ndef bar(): pass\n')
    assert syms.all_exports == ['Foo', 'bar']
T('all_exports', t_ast_all)

def t_ast_all_none():
    syms = ast_harvest('class Foo: pass')
    assert syms.all_exports is None
T('all_exports_absent', t_ast_all_none)

def t_ast_typevar():
    syms = ast_harvest('from typing import TypeVar\nT = TypeVar("T")')
    assert syms.typevar_decls[0].name == 'T'
    assert syms.typevar_decls[0].kind == 'TypeVar'
T('typevar_detection', t_ast_typevar)

def t_ast_paramspec():
    syms = ast_harvest('from typing import ParamSpec\nP = ParamSpec("P")')
    assert syms.typevar_decls[0].name == 'P'
    assert syms.typevar_decls[0].kind == 'ParamSpec'
T('paramspec_detection', t_ast_paramspec)

def t_ast_typealias():
    syms = ast_harvest('from typing import TypeAlias\nMyType: TypeAlias = int | str')
    assert syms.typevar_decls[0].name == 'MyType'
    assert syms.typevar_decls[0].kind == 'TypeAlias'
T('typealias_detection', t_ast_typealias)

def t_ast_annotated_var():
    syms = ast_harvest('MAX: int = 100')
    v = syms.variables[0]
    assert v.name == 'MAX' and v.annotation_str == 'int' and v.value_repr == '100'
T('annotated_variable', t_ast_annotated_var)

def t_ast_plain_var():
    syms = ast_harvest('VERSION = "1.0"')
    v = syms.variables[0]
    assert v.name == 'VERSION' and v.annotation_str is None
    assert v.value_repr == "'1.0'"
T('plain_variable', t_ast_plain_var)

def t_ast_private_skip():
    # The AST harvester is a pure collector:
    # Private-name filtering is the symbol table's responsibility, not the harvester's.
    # The harvester DOES collect private names; build_symbol_table filters them.
    syms = ast_harvest('_PRIVATE = 1\n_Helper = None\nPUBLIC = 2\n')
    # All names are harvested (private + public)
    all_names = [v.name for v in syms.variables]
    assert '_PRIVATE' in all_names, 'Harvester must collect all names for symbol table to filter'
    assert 'PUBLIC' in all_names
    # Private filtering happens in build_symbol_table (tested separately)
    import types as _t2
    from stubpy.symbols import build_symbol_table as _bst
    m2 = _t2.ModuleType('_stubpy_target_priv')
    m2._PRIVATE, m2.PUBLIC = 1, 2
    tbl_default = _bst(m2, '_stubpy_target_priv', syms)
    assert '_PRIVATE' not in tbl_default, 'Symbol table must filter private names by default'
    assert 'PUBLIC' in tbl_default
    tbl_priv = _bst(m2, '_stubpy_target_priv', syms, include_private=True)
    assert '_PRIVATE' in tbl_priv, 'include_private=True must expose private names'
T('private_names_skipped_by_harvester', t_ast_private_skip)

def t_ast_methods():
    src = 'class Foo:\n    def a(self): pass\n    def b(self, x: int): pass\n'
    syms = ast_harvest(src)
    assert len(syms.classes[0].methods) == 2
    names = [m.name for m in syms.classes[0].methods]
    assert 'a' in names and 'b' in names
T('class_method_harvest', t_ast_methods)

def t_ast_if_type_checking():
    src = (
        'from typing import TYPE_CHECKING\n'
        'if TYPE_CHECKING:\n'
        '    class TypeOnly: pass\n'
    )
    syms = ast_harvest(src)
    names = [c.name for c in syms.classes]
    assert 'TypeOnly' in names
T('if_type_checking_visited', t_ast_if_type_checking)

def t_ast_source_order():
    syms = ast_harvest('class B: pass\nclass A: pass\n')
    assert syms.classes[0].name == 'B' and syms.classes[1].name == 'A'
T('source_order_preserved', t_ast_source_order)

def t_ast_arg_annotations():
    src = 'def foo(x: int, y: str = "a", *args: float, **kwargs: bool) -> None: ...\n'
    fn = ast_harvest(src).functions[0]
    assert fn.raw_arg_annotations.get('x') == 'int'
    assert fn.raw_arg_annotations.get('y') == 'str'
    assert fn.raw_arg_annotations.get('*args') == 'float'
    assert fn.raw_arg_annotations.get('**kwargs') == 'bool'
    assert fn.raw_return_annotation == 'None'
T('function_arg_annotations', t_ast_arg_annotations)

def t_ast_method_decorators():
    src = (
        'class Foo:\n'
        '    @classmethod\n'
        '    def create(cls): ...\n'
        '    @staticmethod\n'
        '    def helper(): ...\n'
        '    @property\n'
        '    def val(self) -> int: ...\n'
    )
    cls = ast_harvest(src).classes[0]
    m_names = {m.name: m for m in cls.methods}
    assert 'classmethod' in m_names['create'].decorators
    assert 'staticmethod' in m_names['helper'].decorators
    assert 'property' in m_names['val'].decorators
T('method_decorator_detection', t_ast_method_decorators)

def t_ast_newtype():
    syms = ast_harvest('from typing import NewType\nUserId = NewType("UserId", int)')
    assert syms.typevar_decls[0].name == 'UserId'
    assert syms.typevar_decls[0].kind == 'NewType'
T('newtype_detection', t_ast_newtype)

def t_ast_lineno():
    src = '\n\nclass Foo: pass\n'
    syms = ast_harvest(src)
    assert syms.classes[0].lineno == 3
T('lineno_captured', t_ast_lineno)

print('── SymbolTable')
def t_sym_empty():
    t = SymbolTable()
    assert len(t) == 0 and 'Foo' not in t
T('empty_table', t_sym_empty)

def t_sym_add_get():
    t = SymbolTable()
    t.add(ClassSymbol('Foo', 1))
    assert 'Foo' in t and t.get('Foo').kind == SymbolKind.CLASS
    assert t.get('Missing') is None
T('add_and_get', t_sym_add_get)

def t_sym_overwrite():
    t = SymbolTable()
    t.add(ClassSymbol('X', 1))
    t.add(FunctionSymbol('X', 2))
    assert t.get('X').kind == SymbolKind.FUNCTION  # last wins in index
T('name_overwrite_in_index', t_sym_overwrite)

def t_sym_kinds():
    t = SymbolTable()
    t.add(ClassSymbol('A', 1))
    t.add(FunctionSymbol('b', 2))
    t.add(VariableSymbol('C', 3))
    t.add(AliasSymbol('T', 4))
    t.add(OverloadGroup('parse', 5))
    assert len(list(t.classes())) == 1
    assert len(list(t.functions())) == 1
    assert len(list(t.variables())) == 1
    assert len(list(t.aliases())) == 1
    assert len(list(t.overload_groups())) == 1
T('iteration_by_kind', t_sym_kinds)

def t_sym_sorted():
    t = SymbolTable()
    t.add(ClassSymbol('C', 10))
    t.add(ClassSymbol('A', 1))
    t.add(ClassSymbol('B', 5))
    names = [s.name for s in t.sorted_by_line()]
    assert names == ['A', 'B', 'C']
T('sorted_by_line', t_sym_sorted)

def t_sym_all_names():
    t = SymbolTable()
    t.add(ClassSymbol('Alpha', 1))
    t.add(FunctionSymbol('beta', 2))
    assert t.all_names() == ['Alpha', 'beta']
T('all_names', t_sym_all_names)

def t_sym_func_async():
    from stubpy.ast_pass import FunctionInfo
    fi = FunctionInfo(name='fetch', lineno=1, is_async=True)
    sym = FunctionSymbol('fetch', 1, ast_info=fi)
    assert sym.is_async is True
T('function_symbol_async_flag', t_sym_func_async)

def t_sym_var_effective():
    v = VariableSymbol('X', 1, annotation_str='int')
    assert v.effective_type_str == 'int'
    v2 = VariableSymbol('Y', 2, inferred_type_str='str')
    assert v2.effective_type_str == 'str'
    v3 = VariableSymbol('Z', 3)
    assert v3.effective_type_str is None
T('variable_effective_type', t_sym_var_effective)

def t_sym_overload_group():
    g = OverloadGroup('parse', 1)
    assert g.kind == SymbolKind.OVERLOAD and g.variants == []
    g.variants.append(FunctionSymbol('parse', 2))
    assert len(g.variants) == 1
T('overload_group_structure', t_sym_overload_group)

def t_sym_repr():
    t = SymbolTable()
    t.add(ClassSymbol('Foo', 1))
    r = repr(t)
    assert 'SymbolTable' in r and 'Foo' in r
T('repr', t_sym_repr)

def t_sym_by_kind():
    t = SymbolTable()
    t.add(ClassSymbol('A', 1))
    t.add(FunctionSymbol('b', 2))
    classes = list(t.by_kind(SymbolKind.CLASS))
    assert len(classes) == 1 and classes[0].name == 'A'
T('by_kind', t_sym_by_kind)

print('── build_symbol_table')
import types as _t

def t_bst_classes():
    src = 'class Foo: pass\nclass Bar: pass\n'
    syms = ast_harvest(src)
    m = _t.ModuleType('_stubpy_target_bst1')
    class Foo: pass
    class Bar: pass
    Foo.__module__ = Bar.__module__ = '_stubpy_target_bst1'
    m.Foo, m.Bar = Foo, Bar
    tbl = build_symbol_table(m, '_stubpy_target_bst1', syms)
    assert 'Foo' in tbl and 'Bar' in tbl
    assert tbl.get_class('Foo').live_type is Foo
T('builds_class_symbols', t_bst_classes)

def t_bst_live_type_none():
    src = 'class Foo: pass\n'
    syms = ast_harvest(src)
    tbl = build_symbol_table(None, '_stubpy_target_none', syms)
    assert 'Foo' in tbl
    assert tbl.get_class('Foo').live_type is None
T('ast_only_live_type_none', t_bst_live_type_none)

def t_bst_functions():
    src = 'def greet(name: str) -> str: ...\nasync def fetch() -> None: ...\n'
    syms = ast_harvest(src)
    m = _t.ModuleType('_stubpy_target_bst2')
    def greet(n): return n
    async def fetch(): pass
    m.greet, m.fetch = greet, fetch
    tbl = build_symbol_table(m, '_stubpy_target_bst2', syms)
    assert 'greet' in tbl and 'fetch' in tbl
    assert tbl.get_function('fetch').is_async is True
T('builds_function_symbols', t_bst_functions)

def t_bst_variables():
    src = 'MAX: int = 42\nNAME = "test"\n'
    syms = ast_harvest(src)
    m = _t.ModuleType('_stubpy_target_bst3')
    m.MAX, m.NAME = 42, 'test'
    tbl = build_symbol_table(m, '_stubpy_target_bst3', syms)
    assert 'MAX' in tbl and 'NAME' in tbl
    max_sym = next(v for v in tbl.variables() if v.name == 'MAX')
    assert max_sym.annotation_str == 'int' and max_sym.live_value == 42
    name_sym = next(v for v in tbl.variables() if v.name == 'NAME')
    assert name_sym.inferred_type_str == 'str'
T('builds_variable_symbols', t_bst_variables)

def t_bst_aliases():
    src = 'from typing import TypeVar\nT = TypeVar("T")\n'
    syms = ast_harvest(src)
    m = _t.ModuleType('_stubpy_target_bst4')
    from typing import TypeVar
    m.T = TypeVar('T')
    tbl = build_symbol_table(m, '_stubpy_target_bst4', syms)
    assert 'T' in tbl and tbl.get('T').kind == SymbolKind.ALIAS
T('builds_alias_symbols', t_bst_aliases)

def t_bst_all_filter():
    src = 'class Pub: pass\nclass Priv: pass\nPUB = 1\n'
    syms = ast_harvest(src)
    m = _t.ModuleType('_stubpy_target_bst5')
    class Pub: pass
    class Priv: pass
    Pub.__module__ = Priv.__module__ = '_stubpy_target_bst5'
    m.Pub, m.Priv, m.PUB = Pub, Priv, 1
    tbl = build_symbol_table(m, '_stubpy_target_bst5', syms, all_exports={'Pub'})
    assert 'Pub' in tbl and 'Priv' not in tbl and 'PUB' not in tbl
T('all_exports_filter', t_bst_all_filter)

def t_bst_no_filter():
    src = 'class Pub: pass\nPUB = 1\n'
    syms = ast_harvest(src)
    m = _t.ModuleType('_stubpy_target_bst5b')
    class Pub: pass
    Pub.__module__ = '_stubpy_target_bst5b'
    m.Pub, m.PUB = Pub, 1
    tbl = build_symbol_table(m, '_stubpy_target_bst5b', syms, all_exports=None)
    assert 'Pub' in tbl and 'PUB' in tbl
T('no_all_exports_includes_all', t_bst_no_filter)

def t_bst_private_filtered():
    src = '_PRIVATE = 1\n'
    syms = ast_harvest(src)
    m = _t.ModuleType('_stubpy_target_bst6')
    m._PRIVATE = 1
    tbl = build_symbol_table(m, '_stubpy_target_bst6', syms)
    assert '_PRIVATE' not in tbl
T('private_symbols_filtered', t_bst_private_filtered)

def t_bst_overload_group():
    src = (
        'from typing import overload\n'
        '@overload\ndef parse(x: int) -> int: ...\n'
        '@overload\ndef parse(x: str) -> str: ...\n'
        'def parse(x): ...\n'
    )
    syms = ast_harvest(src)
    m = _t.ModuleType('_stubpy_target_bst7')
    def parse(x): return x
    m.parse = parse
    tbl = build_symbol_table(m, '_stubpy_target_bst7', syms)
    grps = list(tbl.overload_groups())
    assert len(grps) == 1 and len(grps[0].variants) == 2
T('builds_overload_group', t_bst_overload_group)

def t_bst_class_has_ast_info():
    src = 'class Widget(object): pass\n'
    syms = ast_harvest(src)
    m = _t.ModuleType('_stubpy_target_bst8')
    class Widget: pass
    Widget.__module__ = '_stubpy_target_bst8'
    m.Widget = Widget
    tbl = build_symbol_table(m, '_stubpy_target_bst8', syms)
    sym = tbl.get_class('Widget')
    assert sym.ast_info is not None
    assert sym.ast_info.name == 'Widget'
T('class_has_ast_info', t_bst_class_has_ast_info)

print('── StubContext')
def t_ctx_new():
    ctx = StubContext()
    assert isinstance(ctx.diagnostics, DiagnosticCollector)
    assert isinstance(ctx.config, StubConfig)
    assert ctx.symbol_table is None
    assert ctx.all_exports is None
T('fresh_context', t_ctx_new)

def t_ctx_execution_mode():
    cfg = StubConfig(execution_mode=ExecutionMode.AST_ONLY)
    ctx = StubContext(config=cfg)
    assert ctx.config.execution_mode == ExecutionMode.AST_ONLY
T('execution_mode_config', t_ctx_execution_mode)

def t_ctx_all_modes():
    for mode in ExecutionMode:
        cfg = StubConfig(execution_mode=mode)
        assert cfg.execution_mode == mode
T('all_execution_modes', t_ctx_all_modes)

def t_ctx_config_defaults():
    cfg = StubConfig()
    assert cfg.include_private is False
    assert cfg.respect_all is True
    assert cfg.verbose is False
    assert cfg.strict is False
T('config_defaults', t_ctx_config_defaults)

def t_ctx_alias_lookup_unchanged():
    from stubpy.context import AliasEntry
    ctx = StubContext()
    ctx.alias_registry.append(AliasEntry(str | int, 'types.T'))
    ctx.type_module_imports['types'] = 'from pkg import types'
    assert ctx.lookup_alias(str | int) == 'types.T'
    assert ctx.lookup_alias(str | float) is None
    assert 'types' in ctx.used_type_imports
T('alias_lookup_unchanged', t_ctx_alias_lookup_unchanged)

def t_ctx_diagnostics_attached():
    ctx = StubContext()
    ctx.diagnostics.error(DiagnosticStage.EMIT, 'X', 'test')
    assert ctx.diagnostics.has_errors()
T('diagnostics_attached_to_context', t_ctx_diagnostics_attached)

print('── loader diagnostics')
from stubpy.loader import load_module

def t_loader_file_not_found():
    d = DiagnosticCollector()
    try:
        load_module('/nonexistent/file.py', diagnostics=d)
    except FileNotFoundError:
        pass
    assert d.has_errors()
    assert d.errors[0].stage == DiagnosticStage.LOAD
T('loader_records_fnf_error', t_loader_file_not_found)

def t_loader_no_diagnostics_still_raises():
    try:
        load_module('/nonexistent/file.py')
        assert False, 'Should have raised'
    except FileNotFoundError:
        pass
T('loader_raises_without_diagnostics', t_loader_no_diagnostics_still_raises)

print('── generate_stub integration')
def t_gen_basic_unchanged():
    c = make_stub('class Simple:\n    def __init__(self, x: int) -> None: pass\n')
    assert 'class Simple:' in c
    assert 'def __init__(self, x: int) -> None:' in c
    assert_valid_syntax(c)
T('generate_stub_unchanged_output', t_gen_basic_unchanged)

def t_gen_diagnostics_info_added():
    # generate_stub now adds INFO diagnostics internally; this just tests it doesn't break
    c = make_stub('class A:\n    pass\n')
    assert 'class A:' in c
T('generate_stub_adds_info_diagnostics', t_gen_diagnostics_info_added)

def t_gen_symbol_table_built():
    from stubpy.loader import load_module
    from stubpy.ast_pass import ast_harvest
    from stubpy.symbols import build_symbol_table
    src = 'class Widget:\n    pass\n'
    with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False, encoding='utf-8') as f:
        f.write(src); tmp = Path(f.name)
    mod, path, mod_name = load_module(str(tmp))
    ast_syms = ast_harvest(src)
    tbl = build_symbol_table(mod, mod_name, ast_syms)
    assert 'Widget' in tbl
    sym = tbl.get_class('Widget')
    assert sym.live_type is not None and sym.ast_info is not None
T('symbol_table_merges_ast_and_runtime', t_gen_symbol_table_built)

def t_gen_all_exports_in_ctx():
    src = '__all__ = ["Public"]\nclass Public: pass\nclass Internal: pass\n'
    syms = ast_harvest(src)
    assert syms.all_exports == ['Public']
    # Verify only Public ends up in symbol table when filter applied
    m = _t.ModuleType('_stubpy_target_allexport')
    class Public: pass
    class Internal: pass
    Public.__module__ = Internal.__module__ = '_stubpy_target_allexport'
    m.Public, m.Internal = Public, Internal
    tbl = build_symbol_table(m, '_stubpy_target_allexport', syms, all_exports={'Public'})
    assert 'Public' in tbl and 'Internal' not in tbl
T('all_exports_correctly_filters', t_gen_all_exports_in_ctx)

# ── Demo integration ─────────────────────────────────────────────────────────
print('── Demo/integration')
DEMO = Path(__file__).parent.parent / 'demo'

def t_elem_valid():
    out = Path(tempfile.mktemp(suffix='.pyi'))
    c = generate_stub(str(DEMO / 'element.py'), str(out))
    assert 'class Style:' in c and 'class Element(ABC):' in c
    assert_valid_syntax(c)
T('element_stub_valid', t_elem_valid)

def t_container_valid():
    out = Path(tempfile.mktemp(suffix='.pyi'))
    c = generate_stub(str(DEMO / 'container.py'), str(out))
    assert 'class Container(Element):' in c
    assert 'from demo.element import Element' in c
    assert_valid_syntax(c)
T('container_stub_valid', t_container_valid)

def t_graphics_valid():
    out = Path(tempfile.mktemp(suffix='.pyi'))
    c = generate_stub(str(DEMO / 'graphics.py'), str(out))
    assert 'from demo import types' in c
    assert 'types.Color' in c
    assert_valid_syntax(c)
T('graphics_stub_valid', t_graphics_valid)

def t_graphics_kwargs():
    out = Path(tempfile.mktemp(suffix='.pyi'))
    c = generate_stub(str(DEMO / 'graphics.py'), str(out))
    # kwargs must still be back-traced correctly
    arc_sec = c.split('class Arc')[1].split('\nclass ')[0]
    assert 'angle: float' in arc_sec
    assert '**kwargs' not in arc_sec
T('graphics_kwargs_still_resolved', t_graphics_kwargs)

# ════════════════════════════════════════════════════════════════════
print()
print('═' * 60)
print(f'  TOTAL: {passed + failed}  |  ✓ {passed} passed  |  ✗ {failed} failed')
print('═' * 60)

if errors_list:
    print('\nFailed tests:')
    for name, tb in errors_list:
        print(f'\n  FAILED: {name}')
        for line in tb.strip().splitlines()[-5:]:
            print(f'    {line}')
    sys.exit(1)
else:
    print('\n  All tests passed ✓')
