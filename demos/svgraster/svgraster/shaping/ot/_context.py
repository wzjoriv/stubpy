"""Contextual and chained contextual subtables (formats 1-3), shared by GSUB and GPOS."""
from __future__ import annotations

from dataclasses import dataclass

from ._tables import ClassDef, Coverage, offsets, u16, u16s


def _glyph(value: int, gid: int) -> bool:
    return gid == value


def _covered(value: Coverage, gid: int) -> bool:
    return gid in value


@dataclass
class Rule:
    """A rule's backtrack, input (after the first glyph) and lookahead values, and its lookup records."""

    backtrack: tuple
    input: tuple
    lookahead: tuple
    records: tuple


def _records(data: bytes, pos: int, count: int) -> tuple:
    flat = u16s(data, pos, 2 * count)
    return tuple((flat[k], flat[k + 1]) for k in range(0, len(flat), 2))


def _plain_rule(data: bytes, pos: int) -> Rule:
    glyphs, count = u16(data, pos), u16(data, pos + 2)
    inputs = u16s(data, pos + 4, glyphs - 1)
    return Rule((), inputs, (), _records(data, pos + 4 + 2 * (glyphs - 1), count))


def _chain_rule(data: bytes, pos: int) -> Rule:
    nb = u16(data, pos)
    back = u16s(data, pos + 2, nb)
    p = pos + 2 + 2 * nb
    ni = u16(data, p)
    inputs = u16s(data, p + 2, ni - 1)
    p += 2 + 2 * (ni - 1)
    na = u16(data, p)
    ahead = u16s(data, p + 2, na)
    p += 2 + 2 * na
    return Rule(back, inputs, ahead, _records(data, p + 2, u16(data, p)))


def _rule_sets(data: bytes, pos: int, at: int, chained: bool) -> list[list[Rule]]:
    read = _chain_rule if chained else _plain_rule
    sets = []
    for set_pos in u16s(data, at + 2, u16(data, at)):
        if not set_pos:
            sets.append([])
            continue
        base = pos + set_pos
        sets.append([read(data, r) for r in offsets(data, base, base + 2, u16(data, base))])
    return sets


class ContextSubtable:
    """Sequence (format 1), class (format 2) or coverage (format 3) context, optionally chained."""

    def __init__(self, data: bytes, pos: int, chained: bool):
        fmt = u16(data, pos)
        self.fmt = fmt
        self.tests = (_glyph, _glyph, _glyph)
        if fmt == 1:
            self.coverage = Coverage(data, pos + u16(data, pos + 2))
            self.sets = _rule_sets(data, pos, pos + 4, chained)
        elif fmt == 2:
            self.coverage = Coverage(data, pos + u16(data, pos + 2))
            if chained:
                back, inp, ahead = (ClassDef(data, pos + o if o else 0) for o in u16s(data, pos + 4, 3))
                self.sets = _rule_sets(data, pos, pos + 10, True)
            else:
                inp = ClassDef(data, pos + u16(data, pos + 4))
                back = ahead = inp
                self.sets = _rule_sets(data, pos, pos + 6, False)
            self.input_class = inp
            self.tests = tuple((lambda cd: lambda v, g: cd(g) == v)(cd) for cd in (back, inp, ahead))
        elif chained:
            self.rule, first = self._chain_format3(data, pos)
            self.coverage = first
            self.tests = (_covered, _covered, _covered)
        else:
            glyphs, count = u16(data, pos + 2), u16(data, pos + 4)
            covs = [Coverage(data, o) for o in offsets(data, pos, pos + 6, glyphs)]
            self.coverage = covs[0]
            self.rule = Rule((), tuple(covs[1:]), (), _records(data, pos + 6 + 2 * glyphs, count))
            self.tests = (_covered, _covered, _covered)

    @staticmethod
    def _chain_format3(data: bytes, pos: int) -> tuple[Rule, Coverage]:
        p = pos + 2
        groups = []
        for _ in range(3):
            n = u16(data, p)
            groups.append(tuple(Coverage(data, o) for o in offsets(data, pos, p + 2, n)))
            p += 2 + 2 * n
        back, inp, ahead = groups
        return Rule(back, inp[1:], ahead, _records(data, p + 2, u16(data, p))), inp[0]

    def _rules(self, gid: int) -> list[Rule]:
        index = self.coverage(gid)
        if index is None:
            return []
        if self.fmt == 3:
            return [self.rule]
        key = index if self.fmt == 1 else self.input_class(gid)
        return self.sets[key] if key < len(self.sets) else []

    def apply(self, ctx, i: int) -> int | None:
        """Match a rule at ``i`` and apply its nested lookups."""
        back_test, in_test, ahead_test = self.tests
        for rule in self._rules(ctx.buf[i].gid):
            found = ctx.match(i, 1, rule.input, in_test, True)
            if found is None:
                continue
            last = found[-1] if found else i
            if rule.lookahead and ctx.match(last, 1, rule.lookahead, ahead_test, False) is None:
                continue
            if rule.backtrack and ctx.match(i, -1, rule.backtrack, back_test, False) is None:
                continue
            return ctx.apply_records([i, *found], rule.records)
        return None
