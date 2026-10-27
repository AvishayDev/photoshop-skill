"""Learned visual patterns: measure them on reference images and keep them in a reusable library.

``learn`` turns a reference photo (or a region of it) into numbers the painting engine understands -
palette, stripe/spot period, orientation and coverage, silhouette contour, light direction. ``library``
stores those (and hand-authored figure/scene recipes) as JSON under ``knowledge/patterns/`` so every
future task can reuse them instead of learning again. Commit the files to share them.
"""

from .learn import learn_from_image
from .library import PatternEntry, PatternLibrary

__all__ = ["PatternEntry", "PatternLibrary", "learn_from_image"]
