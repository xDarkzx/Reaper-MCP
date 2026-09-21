"""Undo groups: label the undo steps a multi-command tool makes.

A tool such as `engine_mix` runs many bridge commands, and each one records
its own undo step. Wrapping the tool in an undo group labels those steps
"MCP: <tool>#<run> > <command>", so they can be undone one by one, by count
(`project_undo(steps=3)`), or all at once (`project_undo_group`).

Nothing is held open in REAPER: a group only labels. (REAPER drops an undo
block that is held open between bridge ticks, so collapsing a tool into one
step was not possible, and it would also have removed the finer control.)

If the bridge script predates undo groups it rejects the command, and the
tool simply runs unlabelled, as it always did.
"""

import functools
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def undo_group(client, name: str):
    """Run the body inside one undo group named `name`."""
    try:
        await client.execute("undo_group_begin", name=name)
        opened = True
    except Exception as exc:
        # An older bridge script doesn't know the command: run unlabelled.
        logger.debug("Undo group %r not started (%s); running unlabelled", name, exc)
        opened = False
    try:
        yield
    finally:
        if opened:
            try:
                await client.execute("undo_group_end")
            except Exception as exc:
                # The bridge stops labelling an abandoned group itself after
                # a while, and failing to close must never mask the tool's
                # own result.
                logger.warning("Could not close undo group %r: %s", name, exc)


def undo_grouped(client, name: str):
    """Decorator form of `undo_group` for an async tool function.

    Keeps the wrapped function's name, docstring and signature, which FastMCP
    reads to build the tool's schema. Apply it beneath `@mcp.tool()`.
    """

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            async with undo_group(client, name):
                return await fn(*args, **kwargs)

        return wrapper

    return decorator
