"""``svgraster fonts`` (discovery and matching) and ``svgraster backends`` (native layer report)."""
from __future__ import annotations

import json

from .._backend import backend_info
from ..fonts import FontDatabase, default_database, system_font_dirs


def add_parsers(sub) -> None:
    """Register ``fonts`` and ``backends``."""
    p = sub.add_parser("fonts", help="list font families or show which face a CSS font request matches")
    p.add_argument("--match", metavar="FAMILIES", help='a font-family list, e.g. "Georgia, serif"')
    p.add_argument("--weight", default="normal", help="CSS weight for --match (default normal)")
    p.add_argument("--italic", action="store_true", help="request an italic face for --match")
    p.add_argument("--font-dir", action="append", default=[], metavar="PATH", help="extra font file or folder")
    p.add_argument("--dirs", action="store_true", help="print the searched system font folders")
    p.set_defaults(run=run_fonts)
    b = sub.add_parser("backends", help="print which native layers are built (JSON)")
    b.set_defaults(run=run_backends)


def run_fonts(args, parser) -> int:
    """List families, folders or a match."""
    db = FontDatabase(args.font_dir, parent=default_database()) if args.font_dir else default_database()
    if args.dirs:
        for folder in system_font_dirs():
            print(folder)
        return 0
    if args.match:
        for found in db.match(args.match, args.weight, args.italic):
            font = found.font
            extra = [n for n, on in (("synthetic bold", found.synthetic_bold),
                                     ("synthetic oblique", found.synthetic_oblique)) if on]
            where = font.source or "<memory>"
            print(f"{font.family} {font.weight}{' italic' if font.italic else ''}  {where}"
                  + (f"  ({', '.join(extra)})" if extra else ""))
        return 0
    families = db.families()
    for name in families:
        print(name)
    print(f"{len(families)} families", flush=True)
    return 0


def run_backends(args, parser) -> int:
    """Print the backend report."""
    print(json.dumps(backend_info(), indent=2))
    return 0
