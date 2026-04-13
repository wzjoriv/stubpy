"""
Sphinx configuration for stubpy documentation.

Build:
    pip install -e ".[docs]"
    cd docs && make html          # output: docs/_build/html/index.html
    make livehtml                  # auto-reload dev server (requires sphinx-autobuild)
"""
import sys
from pathlib import Path

# Make the package importable for autodoc without installing it first
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ---------------------------------------------------------------------------
# Project metadata
# ---------------------------------------------------------------------------
project   = "stubpy"
copyright = "2026, Josue N Rivera"
author    = "Josue N Rivera"

# Keep in sync with stubpy/__init__.py
release = "0.5.3"
version = "0.5"

# ---------------------------------------------------------------------------
# Extensions
# ---------------------------------------------------------------------------
extensions = [
    # Auto-generate API reference from docstrings
    "sphinx.ext.autodoc",
    # Summary tables via .. autosummary:: (used in stubpy/__init__.py)
    "sphinx.ext.autosummary",
    # Cross-reference Python objects (e.g. :class:`StubContext`)
    "sphinx.ext.intersphinx",
    # Napoleon: parse Google- and NumPy-style docstrings
    "sphinx.ext.napoleon",
    # Source-link "View source" buttons
    "sphinx.ext.viewcode",
    # Markdown support for .md files
    "myst_parser",
]

# ---------------------------------------------------------------------------
# autodoc settings
# ---------------------------------------------------------------------------
autodoc_default_options = {
    "members":            True,
    "undoc-members":      False,
    "private-members":    False,
    "show-inheritance":   True,
    "special-members":    "__init__",
    "member-order":       "bysource",
}
# Show type hints in the signature (not repeated in the description)
autodoc_typehints = "signature"
# Don't repeat the class name prefix for every attribute
add_module_names = False

# Auto-generate stub .rst files for .. autosummary:: directives
autosummary_generate = False

# Suppress duplicate-description warnings that arise when autosummary
# generates stubs for members already documented in api/*.rst pages.
suppress_warnings = ["autosummary"]

# ---------------------------------------------------------------------------
# Napoleon (docstring style)
# ---------------------------------------------------------------------------
napoleon_google_docstring  = False
napoleon_numpy_docstring   = True
napoleon_include_init_with_doc = True
napoleon_use_rtype         = False   # merge return type into signature

# ---------------------------------------------------------------------------
# Intersphinx — link to Python stdlib docs
# ---------------------------------------------------------------------------
import os as _os
# Allow CI to skip network fetches: set SPHINX_INTERSPHINX=0
_intersphinx_enabled = _os.environ.get('SPHINX_INTERSPHINX', '1') != '0'
intersphinx_mapping = (
    {
    "python": ("https://docs.python.org/3", None),
}
    if _intersphinx_enabled else {}
)

# ---------------------------------------------------------------------------
# MyST (Markdown) parser
# ---------------------------------------------------------------------------
myst_enable_extensions = [
    "colon_fence",    # ::: directive blocks
    "deflist",        # definition lists
]

# ---------------------------------------------------------------------------
# HTML output — Furo theme
# ---------------------------------------------------------------------------
html_theme = "furo"

html_theme_options = {
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
    "light_css_variables": {
        "color-brand-primary":    "#2563eb",
        "color-brand-content":    "#1d4ed8",
        "color-admonition-title": "#2563eb",
    },
    "dark_css_variables": {
        "color-brand-primary":    "#60a5fa",
        "color-brand-content":    "#93c5fd",
    },
    "footer_icons": [
        {
            "name": "GitHub",
            "url":  "https://github.com/wzjoriv/stubpy",
            "html": (
                '<svg stroke="currentColor" fill="currentColor" stroke-width="0" '
                'viewBox="0 0 16 16" height="1em" width="1em">'
                '<path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 '
                '2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49'
                '-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-'
                '.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.'
                '66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-'
                '1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-'
                '.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-'
                '.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87'
                ' 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 '
                '0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z">'
                '</path></svg>'
            ),
            "class": "",
        }
    ],
}

html_title          = "stubpy"
html_static_path    = ["_static"]
templates_path      = ["_templates"]
html_css_files      = ["custom.css"]
html_show_sourcelink = True

# ---------------------------------------------------------------------------
# Source file extensions
# ---------------------------------------------------------------------------
source_suffix = {
    ".rst": "restructuredtext",
    ".md":  "markdown",
}

# Root document
root_doc = "index"

# ---------------------------------------------------------------------------
# Output settings
# ---------------------------------------------------------------------------
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
pygments_style   = "friendly"
