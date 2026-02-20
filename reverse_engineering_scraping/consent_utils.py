"""
Google consent gate handling: cookie seeding, detection, button clicks.
"""

from typing import List

# Pre-seed cookies that usually suppress the "Before you continue" gate
GOOGLE_CONSENT_COOKIES = [
    {
        "name": "CONSENT",
        "value": "YES+cb.20210328-17-p0.en+FX+667",
        "domain": ".google.com",
        "path": "/",
    },
    {
        "name": "SOCS",
        "value": "CAISHAgCEhJnd3NfMjAyNTAxMDctMF9SQzEaAmVuIAEaBgiA8t23Bg",
        "domain": ".google.com",
        "path": "/",
    },
]


async def seed_google_consent(context) -> None:
    """Add consent cookies to browser context before first navigation."""
    await context.add_cookies(GOOGLE_CONSENT_COOKIES)


async def _looks_like_consent(page) -> bool:
    try:
        title = (await page.title()) or ""
    except Exception:
        title = ""
    if "before you continue" in title.lower():
        return True
    try:
        body = await page.locator("body").inner_text(timeout=2000)
        b = body.lower()
        return ("before you continue" in b) or ("we use cookies" in b)
    except Exception:
        return False


async def _click_button_like(frame_or_page, names: List[str], timeout_ms: int) -> bool:
    for name in names:
        try:
            loc = frame_or_page.get_by_role("button", name=name)
            if await loc.count() > 0:
                btn = loc.first
                await btn.scroll_into_view_if_needed(timeout=timeout_ms)
                await btn.click(timeout=timeout_ms, force=True)
                return True
        except Exception:
            pass
    for name in names:
        try:
            loc = frame_or_page.locator(f"button:has-text('{name}')")
            if await loc.count() > 0:
                btn = loc.first
                await btn.scroll_into_view_if_needed(timeout=timeout_ms)
                await btn.click(timeout=timeout_ms, force=True)
                return True
        except Exception:
            pass
    return False


async def handle_google_consent_any_frame(page, timeout_ms: int = 20000, accept: bool = True) -> bool:
    """
    Detect consent gate and try to click Accept/Reject in main page or iframes.
    """
    if not await _looks_like_consent(page):
        return False
    primary = "Accept all" if accept else "Reject all"
    candidates = [primary, "Reject all", "Accept all", "I agree", "Agree", "Accept", "OK"]
    if await _click_button_like(page, candidates, timeout_ms):
        await page.wait_for_timeout(1200)
        return True
    for fr in page.frames:
        try:
            if await _click_button_like(fr, candidates, timeout_ms):
                await page.wait_for_timeout(1200)
                return True
        except Exception:
            continue
    return False
