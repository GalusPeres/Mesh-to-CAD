"""Public API of the scan alignment.

The alignment is a slot of the document, evaluated first in every rebuild. Its
inputs are fitted in scan coordinates, so fit features referenced as inputs are
refitted from their stored triangles here (never from their own results, which
are in part coordinates and depend on the alignment).
"""

from __future__ import annotations

from m2c_kernel.document.model import Document
from m2c_kernel.geometry import Matrix4
from m2c_kernel.session.jobs import JobContext


def evaluate_alignment(document: Document, job: JobContext) -> Matrix4:
    """Return the scan-to-part transform for the document's alignment slot.

    Until the alignment methods exist this returns the stored matrix, which is the
    identity for a new document.
    """
    return document.alignment.matrix
