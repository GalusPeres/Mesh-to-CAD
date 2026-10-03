"""Starting, saving and opening projects.

`project.save` and `project.load` take a file path and are called only by the
main process after a file dialog (ARCHITECTURE.md 3.5.8). Opening a project
replaces the document; bodies and display data are rebuilt from it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from m2c_kernel.codes.project import ErrorCode, ProgressStage
from m2c_kernel.document.model import Document
from m2c_kernel.document.project_file import load_project, save_project
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.protocol.wire import JsonValue
from m2c_kernel.session.jobs import JobContext


@dataclass(frozen=True)
class NewParams:
    pass


@dataclass(frozen=True)
class NewResult:
    revision: int


@command("project.new")
def project_new(ctx: JobContext, params: NewParams) -> NewResult:
    """Start over with an empty document."""
    session = ctx.session
    session.pending_imports.clear()
    snapshot = session.commit(Document.empty(), "new", ctx)
    return NewResult(revision=snapshot.revision)


@dataclass(frozen=True)
class SaveParams:
    path: str
    ui: JsonValue = None
    """View state of the renderer (camera, stage, visibility), stored as `ui.json`."""


@dataclass(frozen=True)
class SaveResult:
    file_name: str
    revision: int
    """The revision that was saved; the renderer compares it to find unsaved changes."""


@command("project.save", caller="main")
def project_save(ctx: JobContext, params: SaveParams) -> SaveResult:
    """Write the current document and the view state to a project file."""
    path = Path(params.path)
    document = ctx.session.document
    ctx.progress(None, ProgressStage.SAVING)
    try:
        save_project(path, document, params.ui, ctx.session.blobs)
    except OSError as error:
        raise KernelError(
            ErrorCode.SAVE_FAILED, {"fileName": path.name}, details=repr(error)
        ) from error
    return SaveResult(file_name=path.name, revision=document.revision)


@dataclass(frozen=True)
class LoadParams:
    path: str


@dataclass(frozen=True)
class LoadResult:
    file_name: str
    revision: int
    ui: JsonValue


@command("project.load", caller="main")
def project_load(ctx: JobContext, params: LoadParams) -> LoadResult:
    """Open a project file: its document becomes the head and is rebuilt."""
    path = Path(params.path)
    if not path.is_file():
        raise KernelError(ErrorCode.FILE_NOT_FOUND, {"fileName": path.name})
    session = ctx.session
    ctx.progress(None, ProgressStage.LOADING)
    try:
        loaded = load_project(path, session.blobs)
    except KernelError as error:
        with_name = {"fileName": path.name, **error.params}
        raise KernelError(error.code, with_name, error.details) from error
    ctx.check_cancelled()
    session.pending_imports.clear()
    snapshot = session.commit(replace(loaded.document, revision=0), "load", ctx)
    return LoadResult(file_name=path.name, revision=snapshot.revision, ui=loaded.ui_state)
