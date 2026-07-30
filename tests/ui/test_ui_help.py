# Copyright 2026 the airflow-pytest-plugin contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Browser checks for the dependency-free user guide."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.ui


def test_help_button_replaces_dashboard_and_returns(dash):
    page = dash.page

    page.click("#links-btn")
    expect(page.locator("#links-menu")).to_be_visible()
    expect(page.locator("#help-btn svg")).to_have_attribute(
        "data-icon", "circle-question"
    )
    expect(page.locator('[data-api="docs"] svg')).to_have_attribute("data-icon", "code")
    page.click("#help-btn")
    page.wait_for_url("**/help")
    expect(page.locator("#help-content")).to_be_visible()
    expect(page.locator(".help-sidebar")).to_be_visible()

    page.click("#back-btn")
    expect(page.locator("#kpis")).to_be_visible()
    assert not page.url.rstrip("/").endswith("/help")
    assert dash.errors == []


@pytest.mark.parametrize(
    ("width", "sidebar_visible"),
    [(320, False), (375, False), (768, False), (1024, True), (1440, True)],
)
def test_help_layout_has_no_horizontal_scroll(page, base_url, width, sidebar_visible):
    page.set_viewport_size({"width": width, "height": 812})
    page.goto(base_url + "/help")

    if sidebar_visible:
        expect(page.locator(".help-sidebar")).to_be_visible()
        expect(page.locator(".mobile-toc")).to_be_hidden()
    else:
        expect(page.locator(".help-sidebar")).to_be_hidden()
        expect(page.locator(".mobile-toc")).to_be_visible()
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 2, f"horizontal overflow at {width}px: {overflow}px"


def test_help_back_button_content_is_vertically_centered(page, base_url):
    page.goto(base_url + "/help")

    offset = page.locator("#back-btn").evaluate(
        """button => {
          const outer = button.getBoundingClientRect();
          const label = button.querySelector(".btn-label").getBoundingClientRect();
          return Math.abs(
            (outer.top + outer.height / 2) - (label.top + label.height / 2)
          );
        }"""
    )
    assert offset <= 1, f"back-button label is {offset}px off centre"


def test_help_header_and_footer_links_are_available(page, base_url):
    page.goto(base_url + "/help")

    expect(page.locator("#help-github-link")).to_be_visible()
    expect(page.locator("#help-api-link")).to_be_visible()
    assert (
        page.locator("#help-api-link").evaluate("link => link.href")
        == base_url + "/api/docs"
    )
    expect(page.locator("#footer-github-link")).to_have_attribute(
        "href", "https://github.com/IKrysanov/airflow-pytest-plugin"
    )


def test_help_skip_link_only_expands_on_keyboard_focus(page, base_url):
    page.goto(base_url + "/help")
    skip_link = page.locator(".skip-link")

    hidden_size = skip_link.evaluate(
        "link => ({width: link.offsetWidth, height: link.offsetHeight})"
    )
    assert hidden_size["width"] <= 1
    assert hidden_size["height"] <= 1

    skip_link.focus()

    focused_size = skip_link.evaluate(
        "link => ({width: link.offsetWidth, height: link.offsetHeight})"
    )
    assert focused_size["width"] >= 44
    assert focused_size["height"] >= 44


# scroll-behavior is smooth and the guide is ~14000px tall, so a scroll assertion that
# does not wait for the animation asserts whatever chapter happened to be passing by. Wait
# for the position to stop moving instead.
_SETTLE = """() => new Promise(done => {
  let last = -1, still = 0;
  const tick = () => {
    if (scrollY === last) { if (++still > 8) return done(scrollY); }
    else { still = 0; last = scrollY; }
    requestAnimationFrame(tick);
  };
  tick();
})"""


def test_help_marks_the_last_chapter_current_at_page_end(page, base_url):
    # The bottom of the page cannot put every chapter's heading under the activation line,
    # so the last one is marked explicitly. Without that, scrolling to the end leaves the
    # contents highlighting a chapter the reader scrolled past minutes ago.
    page.goto(base_url + "/help")

    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    page.evaluate(_SETTLE)

    last = page.locator(".doc-section").last.get_attribute("id")
    current = page.evaluate(
        """() => [...document.querySelectorAll('.toc a')]
             .filter(a => a.getAttribute('aria-current') === 'true')
             .map(a => a.getAttribute('href'))"""
    )
    assert current == [f"#{last}"], current


def test_help_keeps_airflow_sidebar_icon_active_and_returns_from_nav(page, base_url):
    page.goto(base_url)
    page.set_content(
        f"""
        <button id="plugin-nav" type="button" aria-label="Pytest">
          <img id="plugin-icon" src="{base_url}/icon.svg" />
        </button>
        <iframe id="help-frame" src="{base_url}/help"></iframe>
        """
    )
    help_frame = page.frame_locator("#help-frame")
    help_frame.locator("#help-content").wait_for()

    expect(page.locator("#apx-nav-style")).to_have_count(1)
    icon_filter = page.locator("#plugin-icon").evaluate(
        "icon => getComputedStyle(icon).filter"
    )
    assert icon_filter != "none"

    page.click("#plugin-nav")

    expect(help_frame.locator("#kpis")).to_be_visible()
    expect(help_frame.locator("#help-content")).to_have_count(0)


@pytest.mark.parametrize(
    ("locale", "heading"),
    [
        ("en", "Understand every test run at a glance"),
        ("ru", "Разберитесь в любом прогоне с первого взгляда"),
    ],
)
def test_help_follows_airflow_locale(page, base_url, locale, heading):
    page.goto(base_url + "/help")
    page.evaluate("(value) => localStorage.setItem('i18nextLng', value)", locale)
    page.reload()

    expect(page.locator("html")).to_have_attribute("lang", locale)
    expect(page.locator("h1")).to_have_text(heading)


# Every width the guide is read at, including the one where the contents bar is a SECOND
# sticky strip under the header: an anchor jump that only clears the header parks the
# section kicker behind the contents bar, which is how the reader loses their place.
@pytest.mark.parametrize("width", [375, 768, 1280])
def test_help_anchor_jump_clears_every_sticky_bar(page, base_url, width):
    page.set_viewport_size({"width": width, "height": 812})
    page.goto(base_url + "/help")

    if width < 901:
        page.click(".mobile-toc summary")  # the contents dropdown starts collapsed
        page.click('.mobile-links a[href="#ai-triage"]')
    else:
        page.click('.toc a[href="#ai-triage"]')
    # scroll-behavior is smooth and this page is ~14000px tall, so the animation runs for
    # seconds: measure once the position stops moving, never on a fixed timeout.
    page.evaluate(
        """() => new Promise(done => {
          let last = -1, still = 0;
          const tick = () => {
            if (scrollY === last) { if (++still > 6) return done(scrollY); }
            else { still = 0; last = scrollY; }
            requestAnimationFrame(tick);
          };
          tick();
        })"""
    )

    clearance = page.evaluate(
        """() => {
          const kicker = document.querySelector("#ai-triage .section-kicker");
          const bars = [...document.querySelectorAll("header, .mobile-toc")]
            .filter(el => getComputedStyle(el).position === "sticky")
            .map(el => el.getBoundingClientRect().bottom);
          return kicker.getBoundingClientRect().top - Math.max(0, ...bars);
        }"""
    )
    assert clearance >= 0, f"section kicker sits {-clearance}px behind a sticky bar"
    assert clearance <= 40, f"jump landed {clearance}px short of the section"


def test_help_documents_the_three_run_list_marks(page, base_url):
    page.goto(base_url + "/help")
    page.evaluate("() => localStorage.setItem('i18nextLng', 'en')")
    page.reload()

    rows = page.locator("#ai-triage table").nth(1).locator("tbody tr")
    expect(rows).to_have_count(3)
    expect(rows.nth(0)).to_contain_text("Blue")
    expect(rows.nth(0)).to_contain_text("claude-sonnet-5")  # tooltip names the model
    expect(rows.nth(1)).to_contain_text("Red")
    expect(rows.nth(2)).to_contain_text("Grey")


@pytest.mark.parametrize(
    ("locale", "comment"),
    [("en", "# max model calls per run"), ("ru", "# предел вызовов модели за прогон")],
)
def test_help_config_sample_is_translated(page, base_url, locale, comment):
    page.goto(base_url + "/help")
    page.evaluate("(value) => localStorage.setItem('i18nextLng', value)", locale)
    page.reload()

    sample = page.locator("#ai-triage pre").first
    expect(sample).to_contain_text("triage_provider=")
    expect(sample).to_contain_text(comment)


def test_help_footer_shows_a_selectable_plugin_version(page, base_url):
    page.goto(base_url + "/help")

    version = page.locator("#help-version")
    expect(version).to_be_visible()
    assert re.match(r"^v\d+\.\d+", version.inner_text()), version.inner_text()
    # Selectable in one gesture: this string exists to be pasted into an issue.
    assert version.evaluate("el => getComputedStyle(el).userSelect") == "all"
    expect(version).to_have_attribute("aria-label", re.compile(r"version|версия", re.I))


@pytest.mark.parametrize("width", [640, 768, 1024, 1440])
def test_help_table_names_and_defaults_never_break_mid_token(page, base_url, width):
    # "Fals / e" is not a default and "logs_only_f / ail" is not a name: both columns hold
    # literals the reader copies. Whether the browser splits them depends on how wide the
    # monospace font resolves -- it does not on a default headless Chromium, and does on a
    # machine with a wider fallback -- so the font is widened here to force the condition
    # the reader actually hit.
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(base_url + "/help")
    page.wait_for_selector("#setup table")
    page.add_style_tag(content="#help-content td code { font-size: 26px; }")

    broken = page.evaluate(
        """() => [...document.querySelectorAll('#help-content tbody tr')]
             .flatMap(tr => [tr.cells[0], tr.cells[1]])
             .filter(Boolean)
             .flatMap(td => [...td.querySelectorAll('code')])
             .filter(c => c.getClientRects().length > 1)
             .map(c => c.textContent.trim())"""
    )
    # The retention env vars are the one exception, and only on a phone: the table is a
    # stack of cards there, so a 36-character name either wraps or is clipped out of sight.
    assert [b for b in broken if not b.startswith("AIRFLOW_")] == [], broken


def test_help_parameter_and_retention_tables_stay_readable_on_a_phone(page, base_url):
    # Both tables carry long identifiers -- parser options and RETENTION env vars. A name
    # split across lines stops being a name, and one clipped past the edge cannot be read
    # or copied at all.
    page.set_viewport_size({"width": 320, "height": 812})
    page.goto(base_url + "/help")
    page.wait_for_selector("#setup table")

    assert (
        page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 2
    )
    clipped = page.evaluate(
        """() => [...document.querySelectorAll('#setup *')]
             .filter(e => e.getBoundingClientRect().right > innerWidth + 1).length"""
    )
    assert clipped == 0, f"{clipped} cells reach past the screen edge"

    page.set_viewport_size({"width": 1440, "height": 900})
    page.reload()
    split = page.evaluate(
        """() => [...document.querySelectorAll('#setup td:first-child code')]
             .filter(c => c.getClientRects().length > 1).map(c => c.textContent)"""
    )
    assert split == [], f"option names broken across lines: {split}"


def test_help_role_table_renders_in_both_languages(page, base_url):
    for locale, heading in (
        ("en", "What your Airflow role lets you do here"),
        ("ru", "Что доступно в плагине при вашей роли в Airflow"),
    ):
        page.goto(base_url + "/help")
        page.evaluate("(v) => localStorage.setItem('i18nextLng', v)", locale)
        page.reload()
        section = page.locator("#access")
        expect(section.get_by_role("heading", name=heading)).to_be_visible()
        # Five actions, each with what it needs and the role that usually carries it.
        rows = section.locator("table tbody tr")
        expect(rows).to_have_count(5)
        assert all(rows.nth(i).locator("td").count() == 3 for i in range(5))


def test_help_release_section_is_last_and_opens_the_notes(page, base_url):
    page.goto(base_url + "/help")
    page.wait_for_selector("#help-content")

    # Last chapter, last entry in the contents: an upgrade note is what you look up after
    # reading the guide, not before it.
    sections = page.locator(".doc-section")
    assert sections.last.get_attribute("id") == "whats-new"
    assert page.locator(".toc a").last.get_attribute("href") == "#whats-new"
    expect(page.locator("#whats-new .section-kicker")).to_contain_text("13")

    for link in ("#rel-current-link", "#rel-all-link"):
        href = page.locator(link).get_attribute("href")
        assert href.startswith(
            "https://github.com/IKrysanov/airflow-pytest-plugin/releases"
        )
        # Outward links must not be plain _blank: Airflow's iframe sandbox blocks that.
        expect(page.locator(link)).to_have_attribute("rel", "noopener noreferrer")
    assert re.search(r"v\d+\.\d+", page.locator("#whats-new").inner_text())
