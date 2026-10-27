"""Reference-image search providers. Add a provider by subclassing ``ReferenceProvider``."""

from .base import ReferenceProvider
from .local import LocalFolderProvider
from .openverse import OpenverseProvider
from .wikimedia import WikimediaCommonsProvider

__all__ = ["ReferenceProvider", "LocalFolderProvider", "OpenverseProvider", "WikimediaCommonsProvider"]
