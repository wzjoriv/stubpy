"""The SMIL sandwich model: every animation's effect at a time, applied to a copy of the document."""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..dom.document import Document
from ..dom.node import Node
from ..dom.style import PROPERTIES
from ._motion import motion_transform
from ._timing import INDEFINITE, Scheduler, Timing, simple_time
from ._values import Value, add, format_value, interpolate, parse_key_times, parse_splines, parse_value, zero_like

ANIMATION_TAGS = frozenset({"animate", "set", "animateColor", "animateTransform", "animateMotion"})
MOTION = "#motion"
TRANSFORM_ARITY = {"translate": 2, "scale": 2, "rotate": 3, "skewX": 1, "skewY": 1}
CACHE_KEY = "animations"


@dataclass
class Animation:
    """One animation element with its target, attribute and timing."""

    node: Node
    target: Node
    attribute: str
    timing: Timing
    order: int

    @property
    def is_css(self) -> bool:
        """Whether the attribute is animated as a presentation property."""
        return self.attribute in PROPERTIES and self.node.get("attributeType", "auto") != "XML"


def collect(document: Document) -> list[Animation]:
    """Every animation element with a resolvable target, in document order."""
    cached = document.cache.get(CACHE_KEY)
    if cached is not None:
        return cached
    out = []
    for node in document.root.iter():
        if node.tag not in ANIMATION_TAGS:
            continue
        target = document.lookup(node.href) if node.href else node.parent
        if target is None:
            continue
        if node.tag == "animateMotion":
            attribute = MOTION
        elif node.tag == "animateTransform":
            attribute = node.get("attributeName", "transform").split(":")[-1]
        else:
            attribute = (node.get("attributeName") or "").split(":")[-1]
            if not attribute:
                continue
        out.append(Animation(node, target, attribute, Timing.from_node(node), len(out)))
    document.cache[CACHE_KEY] = out
    return out


def _transform_value(kind: str, text: str) -> Value:
    nums = list(parse_value(text).numbers)
    arity = TRANSFORM_ARITY.get(kind, 1)
    if kind == "scale" and len(nums) == 1:
        nums.append(nums[0])
    nums = (nums + [0.0] * arity)[:arity]
    parts = (f"{kind}(",) + (" ",) * (arity - 1) + (")",)
    return Value(text, parts, tuple(nums))


def _values(anim: Animation, underlying: str) -> tuple[list[Value], bool, bool]:
    """``(keyframe values, is a to-animation, forced additive)``."""
    node = anim.node
    kind = node.get("type", "translate") if node.tag == "animateTransform" else None

    def parse(text: str) -> Value:
        return _transform_value(kind, text) if kind else parse_value(text, anim.attribute)

    if node.get("values") is not None:
        return [parse(v) for v in node.get("values").split(";") if v.strip()], False, False
    start, end, by = node.get("from"), node.get("to"), node.get("by")
    if start is not None and end is not None:
        return [parse(start), parse(end)], False, False
    if start is not None and by is not None:
        first = parse(start)
        return [first, add(first, parse(by))], False, False
    if by is not None:
        delta = parse(by)
        return [zero_like(delta), delta], False, True
    if end is not None:
        base = _transform_value(kind, "") if kind else parse_value(underlying, anim.attribute)
        return [base, parse(end)], True, False
    return [], False, False


def _evaluate(anim: Animation, progress: float, iteration: int, underlying: str) -> str | None:
    node = anim.node
    if node.tag == "set":
        return node.get("to")
    values, to_anim, forced_sum = _values(anim, underlying)
    if not values:
        return None
    mode = node.get("calcMode", "linear")
    value = interpolate(values, progress, mode, parse_key_times(node.get("keyTimes")),
                        parse_splines(node.get("keySplines")))
    if node.get("accumulate") == "sum" and iteration > 0 and not to_anim:
        value = add(value, values[-1], float(iteration))
    text = format_value(value)
    additive = (node.get("additive") == "sum" or forced_sum) and not to_anim
    if node.tag == "animateTransform":
        return f"{underlying} {text}".strip() if additive else text
    if additive:
        return format_value(add(parse_value(underlying, anim.attribute), value))
    return text


def _underlying(anim: Animation) -> str:
    target = anim.target
    if anim.attribute == MOTION:
        return ""
    if anim.is_css:
        return target.style.get(anim.attribute, target.attrs.get(anim.attribute, "0"))
    return target.attrs.get(anim.attribute, "" if anim.attribute == "transform" else "0")


def _progress(timing: Timing, local: float, frozen: bool) -> float:
    dur = timing.dur
    if dur is None or dur == INDEFINITE:
        return 0.0
    return 1.0 if frozen and local >= dur else min(1.0, local / dur)


def snapshot(document: Document, time: float) -> Document:
    """A copy of ``document`` with every animation applied at ``time`` seconds."""
    anims = collect(document)
    if not anims:
        return document
    scheduler = Scheduler({a.node.id: a.timing for a in anims if a.node.id})
    groups: dict[tuple[int, str], list] = {}
    for anim in anims:
        interval = scheduler.interval_at(anim.timing, time)
        if interval is None:
            continue
        local, iteration, frozen = simple_time(anim.timing, interval[0], interval[1], time)
        if not math.isfinite(local):
            continue
        key = (id(anim.target), anim.attribute)
        groups.setdefault(key, []).append((interval[0], anim.order, anim, local, iteration, frozen))
    copy_root = document.root.copy_tree()
    mapping = {id(o): c for o, c in zip(document.root.iter(), copy_root.iter())}
    motions: dict[int, str] = {}
    for entries in groups.values():
        entries.sort(key=lambda e: (e[0], e[1]))
        anim = entries[0][2]
        current = _underlying(anim)
        for _, _, anim, local, iteration, frozen in entries:
            progress = _progress(anim.timing, local, frozen)
            if anim.node.tag == "animateMotion":
                progress = progress if anim.timing.dur not in (None, INDEFINITE) else 0.0
                current = motion_transform(anim.node, document, progress)
                continue
            value = _evaluate(anim, progress, iteration, current)
            if value is not None:
                current = value
        target = mapping[id(anim.target)]
        if anim.attribute == MOTION:
            motions[id(target)] = current
        elif anim.is_css:
            target.animated = dict(target.animated, **{anim.attribute: current})
        else:
            target.attrs[anim.attribute] = current
    for node in copy_root.iter():
        motion = motions.get(id(node))
        if motion:
            node.attrs["transform"] = f"{motion} {node.attrs.get('transform', '')}".strip()
    return document.derive(copy_root)


def timeline(document: Document) -> float:
    """A natural length in seconds: the latest finite end, or one cycle of repeating animations."""
    anims = collect(document)
    scheduler = Scheduler({a.node.id: a.timing for a in anims if a.node.id})
    end = 0.0
    for anim in anims:
        begin = scheduler.first_begin(anim.timing)
        if not math.isfinite(begin):
            continue
        stop = scheduler.interval_end(anim.timing, begin)
        if not math.isfinite(stop):
            dur = anim.timing.dur
            stop = begin + (dur if dur is not None and math.isfinite(dur) else 0.0)
        end = max(end, stop)
    return end
