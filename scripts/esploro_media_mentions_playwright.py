from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse

from dotenv import load_dotenv
from playwright.sync_api import Page, sync_playwright

LOGIN_URL = "https://umassd-researchmanagement.esploro.exlibrisgroup.com/mng/login"
HOME_URL = "https://umassd-researchmanagement.esploro.exlibrisgroup.com/ng;u=%2Fmng%2Faction%2Fhome.do%3FngHome%3Dtrue"


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_markdown_table_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []

    lines = [ln.rstrip("\n") for ln in path.read_text(encoding="utf-8").splitlines()]
    table_lines = [ln.strip() for ln in lines if ln.strip().startswith("|") and ln.strip().endswith("|")]
    if len(table_lines) < 3:
        return []

    headers = [h.strip() for h in table_lines[0].strip("|").split("|")]
    data_lines = table_lines[2:]

    rows: List[Dict[str, str]] = []
    for line in data_lines:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(headers):
            continue
        rows.append(dict(zip(headers, cells)))
    return rows


def source_from_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "umassd.edu" in host:
        return "UMass Dartmouth News"
    if host.startswith("www."):
        host = host[4:]
    return host or "N/A"


def load_media_mentions(data_file: str) -> List[Dict[str, object]]:
    rows = parse_markdown_table_rows(Path(data_file))
    items: List[Dict[str, object]] = []
    for row in rows:
        title = (row.get("News Archive Title") or "").strip()
        date = (row.get("Date (dd/mm/yyyy)") or "").strip()
        url = (row.get("News Archive URL") or "").strip()
        if not title or not date or not url:
            continue

        reporter = (row.get("Reporter") or "").strip()
        if reporter.upper() == "N/A":
            reporter = ""

        topics_raw = (row.get("Research Topics") or "").strip()
        tags = [x.strip() for x in topics_raw.split(";") if x.strip()]

        items.append(
            {
                "title": title,
                "date": date,
                "reporter": reporter,
                "source": source_from_url(url),
                "url": url,
                "tags": tags,
            }
        )
    return items


def select_autocomplete(page: Page, label: str, value: str) -> None:
    candidates = [
        page.get_by_role("combobox", name=re.compile(re.escape(label), re.I)).first,
        page.get_by_role("textbox", name=re.compile(re.escape(label), re.I)).first,
        page.locator(f"label:has-text('{label}')").locator("xpath=following::input[1]").first,
    ]
    last_error = None
    for field in candidates:
        try:
            field.click(timeout=2000)
            field.fill(value)
            time.sleep(0.2)
            page.keyboard.press("ArrowDown")
            page.keyboard.press("Enter")
            return
        except Exception as err:
            last_error = err
    raise last_error if last_error else RuntimeError(f"Could not set autocomplete: {label}")


def add_tags(page: Page, tags: List[str]) -> None:
    tag_input = page.locator(".bootstrap-tagsinput input")
    seen = set()
    for tag in tags:
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tag_input.fill(tag)
        tag_input.press("Enter")


def login(page: Page, username: str, password: str) -> None:
    page.goto(LOGIN_URL)
    page.get_by_role("textbox", name="User Name").fill(username)
    page.get_by_role("textbox", name="Password").fill(password)
    page.get_by_role("button", name="Login").click()
    page.wait_for_load_state("networkidle")


def click_add_media_mentions(page: Page) -> None:
    title_field = page.get_by_role("textbox", name=re.compile(r"Media mention title", re.I)).first
    page.goto(HOME_URL)
    page.wait_for_load_state("networkidle")

    # Keep this simple but reliable: retry opening the form a few times.
    for _ in range(3):
        add_link = page.get_by_role("link", name=re.compile(r"Add Media Mention", re.I))
        add_link.first.click()
        page.wait_for_load_state("networkidle")
        try:
            title_field.wait_for(timeout=5000)
            return
        except Exception:
            page.goto(HOME_URL)
            page.wait_for_load_state("networkidle")

    raise RuntimeError("Could not open Add Media Mentions form")


def wait_for_media_mention_form(page: Page, timeout_ms: int = 180000) -> None:
    title_field = page.get_by_role("textbox", name=re.compile(r"Media mention title", re.I)).first
    title_field.wait_for(timeout=timeout_ms)


def add_researcher(page: Page, researcher_query: str) -> None:
    page.get_by_role("button", name="Add researcher").click()
    search = page.get_by_role("textbox", name="Choose researcher *")
    search.fill(researcher_query)
    page.get_by_text("Williams, Brian G. -").first.click()
    page.get_by_role("button", name="Add and Close").click()


def add_link(
    page: Page,
    url: str,
    title: str,
    *,
    stop_at_link_modal: bool,
    link_modal_wait_ms: int,
) -> None:
    page.locator("a", has_text="Add a Link").click()
    page.get_by_role("textbox", name="URL *").fill(url)
    page.get_by_role("textbox", name="Link title").fill(title)
    if stop_at_link_modal:
        print("Paused at Add Link modal (URL and Link title filled). Waiting for your manual saves...")
        return
    page.get_by_role("button", name="Save", exact=True).click()


def wait_for_manual_saves(page: Page, timeout_ms: int) -> None:
    # 1) Wait for user to click Save in Add Link modal (URL textbox disappears).
    link_url_box = page.get_by_role("textbox", name="URL *").first
    link_url_box.wait_for(state="hidden", timeout=timeout_ms)

    # 2) Wait for user to click final sub-save (media mention form leaves screen).
    title_input = page.get_by_role("textbox", name=re.compile(r"Media mention title", re.I)).first
    title_input.wait_for(state="hidden", timeout=timeout_ms)


def fill_media_mention_form(
    page: Page,
    item: Dict[str, object],
    researcher_query: str,
    *,
    stop_at_link_modal: bool,
    link_modal_wait_ms: int,
) -> None:
    title = str(item["title"])
    date = str(item["date"])
    reporter = str(item.get("reporter", "") or "")
    source = str(item.get("source", "") or "")
    url = str(item["url"])
    tags = [str(t) for t in (item.get("tags", []) or [])]

    title_input = page.get_by_role("textbox", name=re.compile(r"Media mention title", re.I)).first
    title_input.wait_for(timeout=8000)
    title_input.fill(title)
    page.get_by_placeholder("From").fill(date)
    page.get_by_role("textbox", name=re.compile(r"Reporter", re.I)).first.click()

    select_autocomplete(page, "Media mention type", "Expert")
    select_autocomplete(page, "Media platform", "Web")
    select_autocomplete(page, "Language", "English")
    select_autocomplete(page, "Coverage", "Local")
    select_autocomplete(page, "Country", "United States")

    if reporter:
        page.get_by_role("textbox", name="Reporter").fill(reporter)
    if source:
        page.get_by_role("textbox", name="Media source").fill(source)

    add_researcher(page, researcher_query)
    add_tags(page, tags)
    add_link(
        page,
        url,
        title,
        stop_at_link_modal=stop_at_link_modal,
        link_modal_wait_ms=link_modal_wait_ms,
    )
    if stop_at_link_modal:
        wait_for_manual_saves(page, timeout_ms=link_modal_wait_ms)


def main() -> None:
    load_dotenv()

    username = os.getenv("ESPLORO_USERNAME", "").strip()
    password = os.getenv("ESPLORO_PASSWORD", "").strip()
    if not username or not password:
        raise RuntimeError("Set ESPLORO_USERNAME and ESPLORO_PASSWORD in environment or .env")

    researcher_query = os.getenv("ESPLORO_RESEARCHER_QUERY", "Williams, Brian").strip()
    # User workflow: assistant must never click final Save Draft/Save.
    # Only the link modal "Save" inside add_link() is allowed.
    save_draft = False
    start_index = int(os.getenv("ESPLORO_START_INDEX", "0"))
    headless = env_bool("ESPLORO_HEADLESS", False)
    slow_mo_ms = int(os.getenv("ESPLORO_SLOW_MO_MS", "80"))
    between_citations_ms = int(os.getenv("ESPLORO_BETWEEN_CITATIONS_MS", "800"))
    manual_after_login = env_bool("ESPLORO_MANUAL_AFTER_LOGIN", True)
    stop_at_link_modal = env_bool("ESPLORO_STOP_AT_LINK_MODAL", True)
    link_modal_wait_ms = int(os.getenv("ESPLORO_LINK_MODAL_WAIT_MS", "900000"))
    wait_for_user = env_bool("ESPLORO_WAIT_FOR_USER", True)
    data_file = os.getenv(
        "ESPLORO_DATA_FILE",
        str(Path(__file__).resolve().parents[1] / "src" / "Media Mentions Data.md"),
    )

    media_mentions = load_media_mentions(data_file)
    if start_index > 0:
        media_mentions = media_mentions[start_index:]
    if not media_mentions:
        print("No media mentions to process.")
        return

    with sync_playwright() as p:
        # Non-persistent, history-less run: fresh browser + fresh isolated context each time.
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo_ms)
        context = browser.new_context()
        context.clear_cookies()
        page = context.new_page()

        login(page, username, password)
        if manual_after_login:
            print('Waiting for you to click "X" and then "Add Media Mention"...')
            wait_for_media_mention_form(page)
        else:
            if wait_for_user:
                input("Close popup (X), then press Enter to continue...")
            click_add_media_mentions(page)

        for idx, item in enumerate(media_mentions):
            fill_media_mention_form(
                page,
                item,
                researcher_query,
                stop_at_link_modal=stop_at_link_modal,
                link_modal_wait_ms=link_modal_wait_ms,
            )
            print(f"Filled (not saved): {item['title']}")
            if idx < len(media_mentions) - 1:
                if wait_for_user:
                    input("Open Add Media Mentions for next citation, then press Enter...")
                elif manual_after_login:
                    print('Waiting for you to open "Add Media Mention" for the next citation...')
                    wait_for_media_mention_form(page)
                else:
                    page.wait_for_timeout(between_citations_ms)
                    click_add_media_mentions(page)

        print("Done.")
        page.wait_for_timeout(1000)
        context.close()
        browser.close()


if __name__ == "__main__":
    main()

