"""Persist a parsed observation without dropping it when the archive is backed up."""

import asyncio
import logging

from web_search_crawler.db.executor import run_in_db_executor
from web_search_crawler.workers.types import PipelineContext
from web_search_web_model.archive.outbox import ArchiveFull

logger = logging.getLogger(__name__)


async def record_links(ctx: PipelineContext, outlinks: list[str]) -> None:
    while True:
        try:
            await run_in_db_executor(
                ctx.link_graph.replace_observed_links, ctx.url, outlinks
            )
            return
        except ArchiveFull:
            logger.warning(
                "Link archive is full; waiting before recording the parsed page"
            )
            await asyncio.sleep(10)
