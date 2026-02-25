# Configuration file for the Sphinx documentation builder.

project = "OpenJobSpec Python SDK"
copyright = "2024, OpenJobSpec Contributors"
author = "OpenJobSpec Contributors"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
]

# Napoleon settings for Google/NumPy style docstrings
napoleon_google_docstring = True
napoleon_numpy_docstring = False

autodoc_member_order = "bysource"
autodoc_typehints = "description"

html_theme = "alabaster"
html_theme_options = {
    "description": "Official Python SDK for Open Job Spec",
    "github_user": "openjobspec",
    "github_repo": "ojs-python-sdk",
}

