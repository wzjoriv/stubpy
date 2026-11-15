from __future__ import annotations

import asyncio
import io
import warnings
from pathlib import Path

import pytest

import svgwriter as svg
from svgwriter.io import SerializeOptions, SVGParseError, Strictness, Writer, aiter_chunks, iter_chunks, write_many_async
from svgwriter.elements import UnknownElement

from .conftest import SVG_NS, wellformed


def sample() -> svg.Svg:
    root = svg.Svg.with_size(100, 100)
    grad = root.defs().add(svg.LinearGradient.horizontal("red", "blue", id="g"))
    root.append(svg.Title("Sample & <test>"))
    with_quotes = svg.Text('say "hi"\nnow', x=1, y=2)
    root.append(svg.Group(svg.Rect(0, 0, 50, 50, fill=grad), with_quotes, id="layer", transform="translate(1.23456 2)"))
    root.append(svg.Path("M0 0 L0.5 0.25 L-0.5 -0.25 Z"))
    return root


def test_pretty_output_layout() -> None:
    text = svg.Svg(svg.Group(svg.Rect()), width=10).to_string()
    assert text == (
        '<?xml version="1.0" encoding="utf-8" standalone="no"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" version="1.1">\n'
        "  <g>\n"
        '    <rect x="0" y="0" width="0" height="0"/>\n'
        "  </g>\n"
        "</svg>\n"
    )


def test_compact_output() -> None:
    text = svg.Svg(svg.Group(svg.Rect()), version=None).to_string(pretty=False, xml_declaration=False)
    assert text == '<svg xmlns="http://www.w3.org/2000/svg"><g><rect x="0" y="0" width="0" height="0"/></g></svg>'


def test_xlink_namespace_only_when_used() -> None:
    assert "xmlns:xlink" not in svg.Svg(svg.Rect()).to_string()
    assert 'xmlns:xlink="http://www.w3.org/1999/xlink"' in svg.Svg(svg.Use("#a")).to_string()
    fragment = svg.Use("#a").to_string(xml_declaration=False, pretty=False)
    assert fragment == '<use xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="#a"/>'
    wellformed(fragment)


def test_escaping_survives_round_trip() -> None:
    text = sample().to_string()
    node = wellformed(text)
    assert node.find(f"{SVG_NS}title").text == "Sample & <test>"  # type: ignore[union-attr]
    parsed = svg.parse(text)
    assert parsed.find(svg.Text).text == 'say "hi"\nnow'  # type: ignore[union-attr]
    assert parsed.to_string() == text


def test_precision_and_compact_paths() -> None:
    root = sample()
    text = root.to_string(precision=1, compact_paths=True, pretty=False)
    assert 'transform="translate(1.2 2)"' in text
    assert 'd="M0 0 .5 .2-.5-.2Z"' in text
    assert svg.parse(text).to_string(precision=1, compact_paths=True, pretty=False) == text


def test_doctype_and_declaration() -> None:
    text = svg.Svg().to_string(doctype=True, encoding="utf-8")
    assert "<!DOCTYPE svg PUBLIC" in text
    wellformed(text)
    assert svg.parse(text).tag == "svg"
    assert not svg.Rect().to_string(xml_declaration=False).startswith("<?xml")


def test_options_object_and_init_var() -> None:
    options = SerializeOptions(pretty=False, indent="\t")
    assert options.indent == "" and options.newline == ""
    assert SerializeOptions().newline == "\n"
    with pytest.raises(TypeError):
        SerializeOptions(False)  # type: ignore[misc]
    assert svg.to_string(svg.Rect(), options=options).count("\n") == 1


def test_write_to_path_stream_and_str_path(tmp_path: Path) -> None:
    root = sample()
    target = tmp_path / "out.svg"
    root.save(target)
    root.save(str(tmp_path / "out2.svg"))
    stream = io.StringIO()
    root.save(stream)
    expected = root.to_string()
    assert target.read_text(encoding="utf-8") == expected
    assert (tmp_path / "out2.svg").read_text(encoding="utf-8") == expected
    assert stream.getvalue() == expected
    with pytest.raises(TypeError):
        svg.write(root, 42)  # type: ignore[arg-type]


def test_iter_chunks_streams() -> None:
    chunks = list(iter_chunks(sample(), xml_declaration=False))
    assert len(chunks) > 10
    assert "".join(chunks) == sample().to_string(xml_declaration=False)
    writer = Writer(pretty=False)
    assert "".join(writer.iter_chunks(svg.Rect(), xml_declaration=False)) == '<rect x="0" y="0" width="0" height="0"/>'


def test_async_helpers(tmp_path: Path) -> None:
    root = sample()

    async def run() -> str:
        await svg.write_async(root, tmp_path / "a.svg")
        count = await write_many_async({tmp_path / "b.svg": root, tmp_path / "c.svg": svg.Svg()})
        assert count == 2
        await svg.Document(root=root).save_async(tmp_path / "d.svg")
        return "".join([chunk async for chunk in aiter_chunks(root)])

    streamed = asyncio.run(run())
    assert streamed == root.to_string()
    assert (tmp_path / "a.svg").read_text(encoding="utf-8") == streamed
    assert (tmp_path / "d.svg").exists() and (tmp_path / "c.svg").exists()


class TestParser:
    def test_parse_file_and_types(self, tmp_path: Path) -> None:
        path = tmp_path / "s.svg"
        sample().save(path)
        root = svg.parse_file(path)
        assert isinstance(root, svg.Svg)
        assert isinstance(root.find("linearGradient"), svg.LinearGradient)
        assert root.get_element_by_id("layer") is not None

    def test_bytes_and_unprefixed_input(self) -> None:
        root = svg.parse(b"<svg><circle r='3'/></svg>")
        assert isinstance(root.find(svg.Circle), svg.Circle)

    def test_xml_and_xlink_attributes(self) -> None:
        source = (
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
            '<text xml:space="preserve">  a  </text><use xlink:href="#x"/></svg>'
        )
        root = svg.parse(source)
        assert root.find(svg.Text).get("xml:space") == "preserve"  # type: ignore[union-attr]
        assert root.find(svg.Text).text == "  a  "  # type: ignore[union-attr]
        assert root.find(svg.Use).target == "x"  # type: ignore[union-attr]

    def test_whitespace_dropped_between_elements(self) -> None:
        root = svg.parse("<svg>\n  <g>\n    <rect/>\n  </g>\n</svg>")
        assert all(not isinstance(c, str) for c in root.children)

    def test_foreign_content_preserved(self) -> None:
        source = (
            '<svg xmlns="http://www.w3.org/2000/svg"><metadata>'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description about="x"/></rdf:RDF>'
            "</metadata></svg>"
        )
        root = svg.parse(source)
        rdf = root.find("RDF")
        assert isinstance(rdf, UnknownElement) and rdf.namespace.endswith("rdf-syntax-ns#")  # type: ignore[union-attr]
        again = svg.parse(root.to_string())
        assert again.to_string() == root.to_string()

    def test_strictness(self) -> None:
        source = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:x="urn:x" x:a="1"><blink/></svg>'
        root = svg.parse(source)
        assert isinstance(root.find("blink"), UnknownElement)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            svg.parse(source, strictness=Strictness.WARN)
        assert len(caught) == 2
        with pytest.raises(SVGParseError):
            svg.parse(source, strictness=Strictness.STRICT)
        assert Strictness.STRICT > Strictness.WARN > Strictness.LENIENT

    def test_malformed(self) -> None:
        with pytest.raises(SVGParseError):
            svg.parse("<svg><g></svg>")
