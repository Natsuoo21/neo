"""Browser tool — Web automation via Playwright.

Provides both high-level tool functions for LLM invocation (browse_url,
take_screenshot) and a lower-level BrowserController class for automation
scripts and the research pipeline.
"""

import asyncio
import concurrent.futures
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


@dataclass
class BrowserConfig:
    """Configuration for the browser controller."""

    headless: bool = True
    timeout_ms: int = 30_000
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )


# Known bot challenge indicators
_BOT_CHALLENGE_INDICATORS: list[str] = [
    "cf-challenge",
    "cloudflare",
    "recaptcha",
    "hcaptcha",
    "just a moment",
    "checking your browser",
    "verify you are human",
]


class BrowserController:
    """Async browser controller using Playwright."""

    def __init__(self, config: BrowserConfig | None = None):
        self._config = config or BrowserConfig()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None

    async def start(self) -> None:
        """Launch the browser (lazy initialization)."""
        if self._browser is not None:
            return

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._config.headless,
        )
        self._context = await self._browser.new_context(
            user_agent=self._config.user_agent,
        )
        self._context.set_default_timeout(self._config.timeout_ms)

    async def stop(self) -> None:
        """Close the browser and cleanup."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def _ensure_started(self) -> None:
        """Ensure the browser is running."""
        if self._browser is None:
            await self.start()

    async def navigate(self, url: str) -> str:
        """Navigate to a URL and return the page title."""
        await self._ensure_started()
        page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
            if await self._detect_bot_challenge(page):
                return f"[BOT CHALLENGE DETECTED] Could not access {url}"
            return await page.title() or url
        finally:
            await page.close()

    async def extract_content(self, url: str, selector: str = "body") -> str:
        """Extract text content from a URL using a CSS selector."""
        await self._ensure_started()
        page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
            if await self._detect_bot_challenge(page):
                return f"[BOT CHALLENGE DETECTED] Could not access {url}"

            element = await page.query_selector(selector)
            if element is None:
                return f"No element found matching selector: {selector}"

            text = await element.inner_text()
            return text.strip()
        finally:
            await page.close()

    async def fill_form(
        self,
        url: str,
        fields: dict[str, str],
        submit_selector: str | None = None,
    ) -> str:
        """Fill form fields on a page and optionally submit."""
        await self._ensure_started()
        page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
            if await self._detect_bot_challenge(page):
                return f"[BOT CHALLENGE DETECTED] Could not access {url}"

            for selector, value in fields.items():
                await page.fill(selector, value)

            if submit_selector:
                await page.click(submit_selector)
                await page.wait_for_load_state("domcontentloaded")

            return f"Form filled on {url} with {len(fields)} fields"
        finally:
            await page.close()

    async def screenshot(self, url: str, output_path: str | None = None) -> str:
        """Take a full-page screenshot of a URL."""
        await self._ensure_started()
        page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")

            if output_path is None:
                output_path = str(Path.home() / "Documents" / "Neo" / "screenshots" / "screenshot.png")

            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=output_path, full_page=True)
            return output_path
        finally:
            await page.close()

    async def download_file(self, url: str, target_dir: str | None = None) -> str:
        """Download a file from a URL."""
        await self._ensure_started()
        page = await self._context.new_page()
        try:
            if target_dir is None:
                target_dir = str(Path.home() / "Downloads")

            Path(target_dir).mkdir(parents=True, exist_ok=True)

            async with page.expect_download() as download_info:
                await page.goto(url)

            download = await download_info.value
            filename = download.suggested_filename or "download"
            save_path = str(Path(target_dir) / filename)
            await download.save_as(save_path)
            return save_path
        finally:
            await page.close()

    async def monitor_page(
        self,
        url: str,
        selector: str,
        condition: str = "changed",
        reference_value: str = "",
        check_interval_s: int = 30,
        max_checks: int = 60,
    ) -> dict[str, Any]:
        """Monitor a page element for a condition change.

        Args:
            url: URL to monitor.
            selector: CSS selector for the element to watch.
            condition: One of 'changed', 'contains', 'not_contains',
                       'appeared', 'disappeared'.
            reference_value: Value to compare against (for contains/not_contains).
            check_interval_s: Seconds between checks (min 10).
            max_checks: Maximum number of checks before giving up.

        Returns:
            Dict with keys: triggered (bool), final_value (str),
            checks_performed (int), elapsed_s (float).
        """
        await self._ensure_started()
        check_interval_s = max(10, check_interval_s)

        page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")

            # Capture initial state
            initial_value = await self._get_element_text(page, selector)

            for i in range(max_checks):
                await asyncio.sleep(check_interval_s)
                await page.reload(wait_until="domcontentloaded")
                current_value = await self._get_element_text(page, selector)

                triggered = False
                if condition == "changed":
                    triggered = current_value != initial_value
                elif condition == "contains":
                    triggered = reference_value.lower() in current_value.lower()
                elif condition == "not_contains":
                    triggered = reference_value.lower() not in current_value.lower()
                elif condition == "appeared":
                    triggered = bool(current_value) and not bool(initial_value)
                elif condition == "disappeared":
                    triggered = not bool(current_value) and bool(initial_value)

                if triggered:
                    return {
                        "triggered": True,
                        "final_value": current_value,
                        "initial_value": initial_value,
                        "checks_performed": i + 1,
                        "elapsed_s": (i + 1) * check_interval_s,
                    }

            return {
                "triggered": False,
                "final_value": current_value,
                "initial_value": initial_value,
                "checks_performed": max_checks,
                "elapsed_s": max_checks * check_interval_s,
            }
        finally:
            await page.close()

    async def _get_element_text(self, page: Any, selector: str) -> str:
        """Get text content of an element, returning empty string if not found."""
        try:
            element = await page.query_selector(selector)
            if element is None:
                return ""
            return (await element.inner_text()).strip()
        except Exception:
            return ""

    async def _detect_bot_challenge(self, page: Any) -> bool:
        """Detect if the page is showing a bot challenge."""
        try:
            content = await page.content()
            content_lower = content.lower()
            return any(indicator in content_lower for indicator in _BOT_CHALLENGE_INDICATORS)
        except Exception:
            return False


# ---------------------------------------------------------------------------
# High-level tool functions (sync wrappers for orchestrator dispatch)
# ---------------------------------------------------------------------------


def _run_async_in_thread(coro_fn):
    """Run an async coroutine in a separate thread with its own event loop.

    This avoids "Cannot run the event loop while another one is running"
    when called from inside an already-running loop (e.g. _execute_sync).
    """
    def _thread_target():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro_fn())
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_thread_target)
        return future.result(timeout=60)


def browse_url(url: str, extract_selector: str = "body") -> str:
    """Navigate to a URL and extract text content.

    Sync wrapper for use by the orchestrator's tool dispatch.
    """
    async def _run() -> str:
        controller = BrowserController()
        try:
            await controller.start()
            return await controller.extract_content(url, extract_selector)
        finally:
            await controller.stop()

    return _run_async_in_thread(_run)


def take_screenshot(url: str, output_path: str = "") -> str:
    """Take a full-page screenshot of a URL.

    Sync wrapper for use by the orchestrator's tool dispatch.
    """
    async def _run() -> str:
        controller = BrowserController()
        try:
            await controller.start()
            return await controller.screenshot(url, output_path or None)
        finally:
            await controller.stop()

    return _run_async_in_thread(_run)


# ---------------------------------------------------------------------------
# Research pipeline
# ---------------------------------------------------------------------------


async def research_pipeline(
    urls: list[str],
    query: str,
    provider: Any,
    max_chars_per_url: int = 5000,
) -> str:
    """Extract content from multiple URLs and synthesize with LLM.

    Args:
        urls: List of URLs to research.
        query: The research question/topic.
        provider: LLM provider for synthesis.
        max_chars_per_url: Max characters to extract per URL.

    Returns:
        Synthesized research document.
    """
    controller = BrowserController()
    contents: list[str] = []

    try:
        await controller.start()

        for url in urls:
            try:
                text = await controller.extract_content(url)
                truncated = text[:max_chars_per_url]
                contents.append(f"## Source: {url}\n{truncated}\n")
            except Exception:
                logger.warning("Failed to extract content from %s", url)
                contents.append(f"## Source: {url}\n[Failed to extract content]\n")
    finally:
        await controller.stop()

    if not contents:
        return "No content could be extracted from the provided URLs."

    combined = "\n---\n".join(contents)

    synthesis_prompt = (
        f"Based on the following web content, provide a comprehensive synthesis "
        f"addressing this query: {query}\n\n"
        f"Content:\n{combined}\n\n"
        f"Provide a well-structured summary with key findings."
    )

    return await provider.complete(
        system="You are a research analyst. Synthesize the provided content into a clear, structured report.",
        user=synthesis_prompt,
    )
