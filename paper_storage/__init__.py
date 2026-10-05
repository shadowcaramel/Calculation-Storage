"""
Reader for published articles linked to calculation results.

This package is separate from ``results_library``. A calculation build does not
import it unless ``--with-papers`` is passed. Papers, PDFs, and parsed tables
are hand-curated inputs; the paper site is regenerated from them.
"""

from __future__ import annotations

__all__: list[str] = []
