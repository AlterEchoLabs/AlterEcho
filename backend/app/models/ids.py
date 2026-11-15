"""Identifier constraints shared by every route that maps an ID onto a file or catalog record.

IDs are lower-case slugs. This blocks path traversal (``..``, ``\\``), absolute or UNC paths on
Windows hosts, and glob metacharacters before any filesystem access happens.
"""

from typing import Annotated

from fastapi import Path

SITE_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"
RUN_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,40}-\d{8}T\d{6}Z-[0-9a-f]{8}$"
IMAGERY_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,95}$"

SiteIdPath = Annotated[str, Path(pattern=SITE_ID_PATTERN, max_length=64, description="Catalog site identifier")]
SourceIdPath = Annotated[str, Path(pattern=SITE_ID_PATTERN, max_length=64, description="Source manifest identifier")]
RunIdPath = Annotated[str, Path(pattern=RUN_ID_PATTERN, max_length=80, description="Processing-run identifier")]
ImageryIdPath = Annotated[str, Path(pattern=IMAGERY_ID_PATTERN, max_length=96, description="Imagery record identifier")]
