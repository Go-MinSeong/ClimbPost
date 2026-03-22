"""Instagram Graph API client for carousel publishing."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from server.config.settings import INSTAGRAM_USER_ID, INSTAGRAM_ACCESS_TOKEN

logger = logging.getLogger(__name__)

GRAPH_API = "https://graph.facebook.com/v21.0"


@dataclass
class PublishResult:
    ig_media_id: str
    container_ids: list[str]
    carousel_container_id: str | None


class InstagramService:
    """Handles Instagram Graph API carousel/reel publishing."""

    def __init__(
        self,
        ig_user_id: str = "",
        access_token: str = "",
    ):
        self.ig_user_id = ig_user_id or INSTAGRAM_USER_ID
        self.access_token = access_token or INSTAGRAM_ACCESS_TOKEN

    # ------------------------------------------------------------------
    # Low-level API calls
    # ------------------------------------------------------------------

    async def _create_video_container(
        self, client: httpx.AsyncClient, video_url: str, is_carousel_item: bool = True
    ) -> str:
        """Create a video media container. Returns container ID."""
        params = {
            "media_type": "VIDEO",
            "video_url": video_url,
            "access_token": self.access_token,
        }
        if is_carousel_item:
            params["is_carousel_item"] = "true"

        resp = await client.post(f"{GRAPH_API}/{self.ig_user_id}/media", data=params)
        resp.raise_for_status()
        container_id = resp.json()["id"]
        logger.info("Created video container %s for %s", container_id, video_url)
        return container_id

    async def _create_reel_container(
        self, client: httpx.AsyncClient, video_url: str, caption: str | None
    ) -> str:
        """Create a single REEL container (for 1-video publish)."""
        params = {
            "media_type": "REELS",
            "video_url": video_url,
            "access_token": self.access_token,
        }
        if caption:
            params["caption"] = caption

        resp = await client.post(f"{GRAPH_API}/{self.ig_user_id}/media", data=params)
        resp.raise_for_status()
        return resp.json()["id"]

    async def _poll_container(
        self, client: httpx.AsyncClient, container_id: str, timeout: int = 300
    ) -> str:
        """Poll until container status is FINISHED. Returns status."""
        for _ in range(timeout // 5):
            resp = await client.get(
                f"{GRAPH_API}/{container_id}",
                params={"fields": "status_code,status", "access_token": self.access_token},
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status_code", "UNKNOWN")

            if status == "FINISHED":
                logger.info("Container %s finished", container_id)
                return status
            elif status == "ERROR":
                error = data.get("status", "Unknown error")
                raise RuntimeError(f"Container {container_id} failed: {error}")

            await asyncio.sleep(5)

        raise TimeoutError(f"Container {container_id} timed out after {timeout}s")

    async def _create_carousel_container(
        self, client: httpx.AsyncClient, children_ids: list[str], caption: str | None
    ) -> str:
        """Create a carousel container referencing child containers."""
        params = {
            "media_type": "CAROUSEL",
            "children": ",".join(children_ids),
            "access_token": self.access_token,
        }
        if caption:
            params["caption"] = caption

        resp = await client.post(f"{GRAPH_API}/{self.ig_user_id}/media", data=params)
        resp.raise_for_status()
        return resp.json()["id"]

    async def _publish(self, client: httpx.AsyncClient, creation_id: str) -> str:
        """Publish a container. Returns the published media ID."""
        resp = await client.post(
            f"{GRAPH_API}/{self.ig_user_id}/media_publish",
            data={"creation_id": creation_id, "access_token": self.access_token},
        )
        resp.raise_for_status()
        return resp.json()["id"]

    # ------------------------------------------------------------------
    # High-level orchestrator
    # ------------------------------------------------------------------

    async def publish_carousel(
        self, video_urls: list[str], caption: str | None = None
    ) -> PublishResult:
        """Publish a carousel (or reel if single video) to Instagram.

        Args:
            video_urls: List of public HTTPS URLs to video files (1-10).
            caption: Post caption.

        Returns:
            PublishResult with ig_media_id and container IDs.
        """
        if not self.ig_user_id or not self.access_token:
            raise ValueError("Instagram credentials not configured (INSTAGRAM_USER_ID / INSTAGRAM_ACCESS_TOKEN)")
        if not video_urls:
            raise ValueError("At least one video URL required")
        if len(video_urls) > 10:
            raise ValueError("Maximum 10 videos per carousel")

        async with httpx.AsyncClient(timeout=30.0) as client:

            # Single video → publish as REEL
            if len(video_urls) == 1:
                container_id = await self._create_reel_container(client, video_urls[0], caption)
                await self._poll_container(client, container_id)
                ig_media_id = await self._publish(client, container_id)
                return PublishResult(
                    ig_media_id=ig_media_id,
                    container_ids=[container_id],
                    carousel_container_id=None,
                )

            # Multiple videos → carousel
            # Step 1: Create containers in parallel
            tasks = [
                self._create_video_container(client, url, is_carousel_item=True)
                for url in video_urls
            ]
            container_ids = await asyncio.gather(*tasks)
            logger.info("Created %d containers", len(container_ids))

            # Step 2: Poll all containers in parallel
            poll_tasks = [self._poll_container(client, cid) for cid in container_ids]
            await asyncio.gather(*poll_tasks)

            # Step 3: Create carousel container
            carousel_id = await self._create_carousel_container(
                client, list(container_ids), caption
            )
            await self._poll_container(client, carousel_id)

            # Step 4: Publish
            ig_media_id = await self._publish(client, carousel_id)
            logger.info("Published carousel %s → ig_media_id=%s", carousel_id, ig_media_id)

            return PublishResult(
                ig_media_id=ig_media_id,
                container_ids=list(container_ids),
                carousel_container_id=carousel_id,
            )
