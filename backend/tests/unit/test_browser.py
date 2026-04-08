"""Tests for neo.tools.browser — mock Playwright, no real browser."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neo.tools.browser import (
    BrowserConfig,
    BrowserController,
    browse_url,
    download_file,
    fill_form,
    monitor_page,
    research_pipeline,
    take_screenshot,
)

# ---------------------------------------------------------------------------
# Helpers — mock Playwright objects
# ---------------------------------------------------------------------------


def _make_mock_page(title="Test Page", inner_text="Hello World", content="<html><body>Hello World</body></html>"):
    """Create a mock Playwright page."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.title = AsyncMock(return_value=title)
    page.content = AsyncMock(return_value=content)
    page.close = AsyncMock()
    page.screenshot = AsyncMock()
    page.fill = AsyncMock()
    page.click = AsyncMock()
    page.wait_for_load_state = AsyncMock()

    element = AsyncMock()
    element.inner_text = AsyncMock(return_value=inner_text)
    page.query_selector = AsyncMock(return_value=element)

    return page


def _make_mock_context(page=None):
    """Create a mock browser context."""
    if page is None:
        page = _make_mock_page()
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    context.set_default_timeout = MagicMock()
    return context


def _make_mock_browser(context=None):
    """Create a mock browser."""
    if context is None:
        context = _make_mock_context()
    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    return browser


def _make_mock_playwright(browser=None):
    """Create a mock Playwright instance."""
    if browser is None:
        browser = _make_mock_browser()
    pw = AsyncMock()
    pw.chromium = AsyncMock()
    pw.chromium.launch = AsyncMock(return_value=browser)
    pw.stop = AsyncMock()
    return pw


# ---------------------------------------------------------------------------
# BrowserConfig tests
# ---------------------------------------------------------------------------


class TestBrowserConfig:
    def test_defaults(self):
        config = BrowserConfig()
        assert config.headless is True
        assert config.timeout_ms == 30_000
        assert "Chrome" in config.user_agent

    def test_custom(self):
        config = BrowserConfig(headless=False, timeout_ms=5000)
        assert config.headless is False
        assert config.timeout_ms == 5000


# ---------------------------------------------------------------------------
# BrowserController tests
# ---------------------------------------------------------------------------


class TestBrowserController:
    @pytest.mark.asyncio
    async def test_navigate(self):
        page = _make_mock_page(title="Example Page")
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)

            controller = BrowserController()
            await controller.start()
            result = await controller.navigate("https://example.com")
            await controller.stop()

            assert result == "Example Page"
            page.goto.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_content(self):
        page = _make_mock_page(inner_text="Extracted content here")
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)

            controller = BrowserController()
            await controller.start()
            result = await controller.extract_content("https://example.com", "main")
            await controller.stop()

            assert result == "Extracted content here"
            page.query_selector.assert_called_with("main")

    @pytest.mark.asyncio
    async def test_extract_content_no_element(self):
        page = _make_mock_page()
        page.query_selector = AsyncMock(return_value=None)
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)

            controller = BrowserController()
            await controller.start()
            result = await controller.extract_content("https://example.com", "#nonexistent")
            await controller.stop()

            assert "No element found" in result

    @pytest.mark.asyncio
    async def test_bot_challenge_detection(self):
        page = _make_mock_page(content="<html><body>Checking your browser before accessing...</body></html>")
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)

            controller = BrowserController()
            await controller.start()
            result = await controller.navigate("https://protected.com")
            await controller.stop()

            assert "BOT CHALLENGE DETECTED" in result

    @pytest.mark.asyncio
    async def test_cloudflare_detection(self):
        page = _make_mock_page(content="<html><body>Just a moment... Cloudflare</body></html>")
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)

            controller = BrowserController()
            await controller.start()
            result = await controller.extract_content("https://cf-site.com")
            await controller.stop()

            assert "BOT CHALLENGE DETECTED" in result

    @pytest.mark.asyncio
    async def test_fill_form(self):
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)

            controller = BrowserController()
            await controller.start()
            result = await controller.fill_form(
                "https://form.com",
                {"#name": "John", "#email": "john@test.com"},
                submit_selector="#submit",
            )
            await controller.stop()

            assert "Form filled" in result
            assert page.fill.call_count == 2
            page.click.assert_called_once_with("#submit")

    @pytest.mark.asyncio
    async def test_screenshot(self, tmp_path):
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        output = str(tmp_path / "shot.png")

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)

            controller = BrowserController()
            await controller.start()
            result = await controller.screenshot("https://example.com", output)
            await controller.stop()

            assert result == output
            page.screenshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_monitor_page_changed(self):
        """monitor_page detects content change."""
        call_count = 0

        async def _dynamic_inner_text():
            nonlocal call_count
            call_count += 1
            return "old value" if call_count <= 1 else "new value"

        page = _make_mock_page(inner_text="old value")
        element = AsyncMock()
        element.inner_text = _dynamic_inner_text
        page.query_selector = AsyncMock(return_value=element)
        page.reload = AsyncMock()
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)
            with patch("neo.tools.browser.asyncio.sleep", new_callable=AsyncMock):
                controller = BrowserController()
                await controller.start()
                result = await controller.monitor_page(
                    "https://example.com",
                    selector="#price",
                    condition="changed",
                    check_interval_s=10,
                    max_checks=5,
                )
                await controller.stop()

        assert result["triggered"] is True
        assert result["final_value"] == "new value"
        assert result["checks_performed"] >= 1

    @pytest.mark.asyncio
    async def test_monitor_page_contains(self):
        """monitor_page detects when element contains a value."""
        call_count = 0

        async def _dynamic_inner_text():
            nonlocal call_count
            call_count += 1
            return "Loading..." if call_count <= 1 else "In Stock - Buy Now"

        page = _make_mock_page(inner_text="Loading...")
        element = AsyncMock()
        element.inner_text = _dynamic_inner_text
        page.query_selector = AsyncMock(return_value=element)
        page.reload = AsyncMock()
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)
            with patch("neo.tools.browser.asyncio.sleep", new_callable=AsyncMock):
                controller = BrowserController()
                await controller.start()
                result = await controller.monitor_page(
                    "https://store.com",
                    selector="#availability",
                    condition="contains",
                    reference_value="In Stock",
                    check_interval_s=10,
                    max_checks=5,
                )
                await controller.stop()

        assert result["triggered"] is True

    @pytest.mark.asyncio
    async def test_monitor_page_timeout(self):
        """monitor_page returns triggered=False when max_checks reached."""
        page = _make_mock_page(inner_text="same value")
        page.reload = AsyncMock()
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)
            with patch("neo.tools.browser.asyncio.sleep", new_callable=AsyncMock):
                controller = BrowserController()
                await controller.start()
                result = await controller.monitor_page(
                    "https://example.com",
                    selector="#status",
                    condition="changed",
                    check_interval_s=10,
                    max_checks=3,
                )
                await controller.stop()

        assert result["triggered"] is False
        assert result["checks_performed"] == 3

    @pytest.mark.asyncio
    async def test_start_stop_idempotent(self):
        pw = _make_mock_playwright()

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)

            controller = BrowserController()
            await controller.start()
            await controller.start()  # Second start should be no-op
            await controller.stop()
            await controller.stop()  # Second stop should be no-op


# ---------------------------------------------------------------------------
# High-level tool function tests
# ---------------------------------------------------------------------------


class TestBrowseUrl:
    def test_browse_url(self):
        page = _make_mock_page(inner_text="Page content")
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)
            result = browse_url("https://example.com")
            assert result == "Page content"

    def test_browse_url_with_selector(self):
        page = _make_mock_page(inner_text="Article text")
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)
            result = browse_url("https://example.com", extract_selector="article")
            assert result == "Article text"


class TestTakeScreenshot:
    def test_take_screenshot(self, tmp_path):
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        output = str(tmp_path / "test.png")

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)
            result = take_screenshot("https://example.com", output)
            assert result == output


class TestFillFormWrapper:
    def test_fill_form(self):
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)
            result = fill_form(
                "https://form.com",
                {"#name": "John", "#email": "john@test.com"},
                submit_selector="#submit",
            )
            assert "Form filled" in result
            assert page.fill.call_count == 2
            page.click.assert_called_once_with("#submit")

    def test_fill_form_no_submit(self):
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)
            result = fill_form("https://form.com", {"#name": "Jane"})
            assert "Form filled" in result
            page.click.assert_not_called()


class TestDownloadFileWrapper:
    def test_download_file(self):
        """Sync wrapper delegates to BrowserController.download_file."""
        with patch("neo.tools.browser.BrowserController") as MockCtrl:
            instance = MockCtrl.return_value
            instance.start = AsyncMock()
            instance.stop = AsyncMock()
            instance.download_file = AsyncMock(return_value="/tmp/downloads/report.pdf")

            result = download_file("https://example.com/report.pdf", "/tmp/downloads")
            assert "report.pdf" in result
            instance.download_file.assert_called_once_with(
                "https://example.com/report.pdf", "/tmp/downloads",
            )


class TestMonitorPageWrapper:
    def test_monitor_page_returns_json(self):
        """Sync wrapper returns a JSON string."""
        call_count = 0

        async def _dynamic_inner_text():
            nonlocal call_count
            call_count += 1
            return "old" if call_count <= 1 else "new"

        page = _make_mock_page(inner_text="old")
        element = AsyncMock()
        element.inner_text = _dynamic_inner_text
        page.query_selector = AsyncMock(return_value=element)
        page.reload = AsyncMock()
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)
            with patch("neo.tools.browser.asyncio.sleep", new_callable=AsyncMock):
                result = monitor_page(
                    "https://example.com",
                    selector="#price",
                    condition="changed",
                    check_interval_s=10,
                    max_checks=3,
                )

        import json
        data = json.loads(result)
        assert data["triggered"] is True
        assert data["final_value"] == "new"

    def test_monitor_page_timeout_json(self):
        """Returns triggered=False as JSON when max_checks reached."""
        page = _make_mock_page(inner_text="same")
        page.reload = AsyncMock()
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)
            with patch("neo.tools.browser.asyncio.sleep", new_callable=AsyncMock):
                result = monitor_page(
                    "https://example.com",
                    selector="#status",
                    condition="changed",
                    check_interval_s=10,
                    max_checks=2,
                )

        import json
        data = json.loads(result)
        assert data["triggered"] is False
        assert data["checks_performed"] == 2


# ---------------------------------------------------------------------------
# Research pipeline tests
# ---------------------------------------------------------------------------


class TestResearchPipeline:
    @pytest.mark.asyncio
    async def test_research_pipeline(self):
        """Research pipeline extracts from multiple URLs and synthesizes."""
        # Create pages with different content
        pages = [
            _make_mock_page(inner_text="Content from site 1 about AI"),
            _make_mock_page(inner_text="Content from site 2 about ML"),
        ]
        page_iter = iter(pages)

        context = AsyncMock()
        context.new_page = AsyncMock(side_effect=lambda: next(page_iter))
        context.close = AsyncMock()
        context.set_default_timeout = MagicMock()

        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        # Mock provider
        provider = AsyncMock()
        provider.complete = AsyncMock(return_value="Synthesized research about AI and ML")

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)

            result = await research_pipeline(
                urls=["https://site1.com", "https://site2.com"],
                query="What is AI?",
                provider=provider,
            )

            assert "Synthesized research" in result
            provider.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_research_pipeline_empty_urls(self):
        provider = AsyncMock()

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            pw = _make_mock_playwright()
            mock_apw.return_value.start = AsyncMock(return_value=pw)

            result = await research_pipeline(
                urls=[],
                query="test",
                provider=provider,
            )

            assert "No content" in result

    @pytest.mark.asyncio
    async def test_research_pipeline_truncation(self):
        """Content is truncated to max_chars_per_url."""
        long_text = "A" * 10000
        page = _make_mock_page(inner_text=long_text)
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)
        pw = _make_mock_playwright(browser)

        provider = AsyncMock()
        provider.complete = AsyncMock(return_value="Summary")

        with patch("neo.tools.browser.async_playwright") as mock_apw:
            mock_apw.return_value.start = AsyncMock(return_value=pw)

            await research_pipeline(
                urls=["https://example.com"],
                query="test",
                provider=provider,
                max_chars_per_url=100,
            )

            # Check that the content passed to provider was truncated
            call_args = provider.complete.call_args
            user_prompt = call_args.kwargs.get("user", call_args[1].get("user", ""))
            # The 100-char truncated content should be in the prompt, not 10000
            assert "A" * 100 in user_prompt
            assert "A" * 10000 not in user_prompt
