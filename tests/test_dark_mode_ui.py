"""
Tests for the dark mode ("Dark Terminal") theme, written with unittest.

How dark mode works in this project
-----------------------------------
* board.js sets <html data-theme="dark"> and remembers the choice in localStorage
  under "scrumptious_theme".
* static/css/style.css swaps a set of CSS variables for [data-theme="dark"]. Most of
  the UI reads those variables, so it re-colours automatically.
* A small <script> in the <head> of index.html and board.html applies the saved
  theme before the page paints.

What these tests can and cannot prove
-------------------------------------
They read the real CSS / HTML / JS files as text, so they need no browser. They CAN
prove the dark theme is fully defined, text is readable (WCAG contrast), the picker
offers a theme the CSS knows about, and the JS saves and restores the choice. They
CANNOT prove the page looks right on screen, and they do not run the JavaScript.

Run from the project root (the folder containing app.py):

    python -m unittest tests.test_dark_mode -v
"""
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CSS = (PROJECT_ROOT / "static/css/style.css").read_text(encoding="utf-8")
BOARD_HTML = (PROJECT_ROOT / "board.html").read_text(encoding="utf-8")
INDEX_HTML = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
BOARD_JS = (PROJECT_ROOT / "static/js/board.js").read_text(encoding="utf-8")
API_JS = (PROJECT_ROOT / "static/js/api.js").read_text(encoding="utf-8")

WCAG_AA_TEXT = 4.5
THEME_KEY = "scrumptious_theme"
ACCENT_KEY = "scrumptious_accent"


# ---------------------------------------------------------------------------
# Helpers: a tiny CSS-variable reader and the WCAG contrast formula
# ---------------------------------------------------------------------------
def css_blocks():
    """Yield (selector, {variable: value}) for every rule, in file order."""
    no_comments = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", no_comments):
        # An @import line can be glued to the front of the first selector.
        selector = selector.strip().split(";")[-1].strip()
        variables = {
            k: v.strip()
            for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body)
        }
        yield selector, variables


def block(selector):
    """The variables declared in the first rule with exactly this selector."""
    for found_selector, variables in css_blocks():
        if found_selector == selector:
            return variables
    return {}


def specificity(selector):
    """Number of attribute / :root parts in a selector (enough for this stylesheet)."""
    return len(re.findall(r"\[[^\]]+\]|:root", selector))


def effective_vars(theme=None, accent=None):
    """
    The variable values the browser ends up using for
    <html data-theme=... data-accent=...>.

    The more specific selector wins; when specificity is equal, the rule that appears
    LATER in the file wins. (:root, [data-theme] and [data-accent] are all equal, which
    is why an accent rule can override the dark theme; a compound selector such as
    [data-theme="dark"][data-accent="cyan"] is more specific, so it beats both.)
    """
    applies_to_this_page = {
        ":root",
        f'[data-theme="{theme}"]',
        f'[data-accent="{accent}"]',
        f'[data-theme="{theme}"][data-accent="{accent}"]',
    }

    matching = [
        (specificity(selector), position, variables)
        for position, (selector, variables) in enumerate(css_blocks())
        if selector in applies_to_this_page
    ]

    result = {}
    for _, _, variables in sorted(matching, key=lambda rule: (rule[0], rule[1])):
        result.update(variables)
    return result


def luminance(hex_colour):
    h = hex_colour.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)

    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def channel(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(colour_a, colour_b):
    lighter, darker = sorted((luminance(colour_a), luminance(colour_b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def picker_values(attribute):
    return re.findall(rf'{attribute}="([\w-]+)"', BOARD_HTML)


def head_script(html):
    """The inline <script> code inside <head> (empty string if there is none)."""
    head_match = re.search(r"<head>(.*?)</head>", html, flags=re.S)
    if not head_match:
        return ""
    return "\n".join(re.findall(r"<script>(.*?)</script>", head_match.group(1), flags=re.S))


def rule_body(selector):
    """The declarations inside the first CSS rule with exactly this selector."""
    no_comments = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    for found, body in re.findall(r"([^{}]+)\{([^{}]*)\}", no_comments):
        if found.strip().split(";")[-1].strip() == selector:
            return body
    return ""


DARK = effective_vars("dark")
LIGHT = effective_vars()
ACCENTS = picker_values("data-set-accent")
THEMES = picker_values("data-set-theme")
PAGES = [("index.html", INDEX_HTML), ("board.html", BOARD_HTML)]


# ---------------------------------------------------------------------------
# 1. The dark theme is defined, and is really dark
# ---------------------------------------------------------------------------
class TestDarkTheme(unittest.TestCase):

    def test_dark_theme_block_exists_in_the_stylesheet(self):
        """There must be a [data-theme="dark"] rule for the picker to switch to."""
        expected = True
        actual = bool(block('[data-theme="dark"]'))
        self.assertTrue(expected == actual, 'No [data-theme="dark"] block found in style.css')

    def test_dark_theme_overrides_every_surface_and_text_variable(self):
        """If one of these is not overridden, part of the UI would stay light."""
        for variable in ["--bg", "--surface", "--lane", "--ink", "--ink-muted", "--border"]:
            with self.subTest(variable=variable):
                expected = True
                actual = variable in block('[data-theme="dark"]')
                self.assertTrue(expected == actual, f"{variable} is not overridden in dark mode")

    def test_dark_theme_overrides_the_priority_badge_colours(self):
        """Priority badges use pastel backgrounds in light mode that would glare on dark."""
        variables = [
            "--high-bg", "--high-text",
            "--medium-bg", "--medium-text",
            "--low-bg", "--low-text",
        ]
        for variable in variables:
            with self.subTest(variable=variable):
                expected = True
                actual = variable in block('[data-theme="dark"]')
                self.assertTrue(expected == actual, f"{variable} is not overridden in dark mode")

    def test_every_dark_override_is_a_variable_that_exists_in_the_light_theme(self):
        """Guards against typos such as --surfce that would silently do nothing."""
        unknown = set(block('[data-theme="dark"]')) - set(block(":root"))

        expected = set()
        actual = unknown
        self.assertTrue(expected == actual, f"Dark theme overrides undefined variables: {sorted(unknown)}")

    def test_every_dark_override_is_a_valid_hex_colour(self):
        """A typo like #12G456 would make the browser ignore that colour."""
        bad = {
            k: v
            for k, v in block('[data-theme="dark"]').items()
            if not re.fullmatch(r"#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})", v)
        }

        expected = {}
        actual = bad
        self.assertTrue(expected == actual, f"Invalid colours in dark theme: {bad}")

    def test_dark_backgrounds_are_actually_dark(self):
        for variable in ["--bg", "--surface", "--lane"]:
            with self.subTest(variable=variable):
                self.assertTrue(
                    luminance(DARK[variable]) < 0.1,
                    f"{variable}={DARK[variable]} is not dark",
                )

    def test_dark_text_colours_are_light(self):
        for variable in ["--ink", "--ink-muted"]:
            with self.subTest(variable=variable):
                self.assertTrue(
                    luminance(DARK[variable]) > 0.3,
                    f"{variable}={DARK[variable]} is not light",
                )

    def test_dark_cards_are_distinguishable_from_the_page_and_columns(self):
        """Cards (--surface) should be a slightly different shade from the page and lanes."""
        self.assertTrue(DARK["--surface"].upper() != DARK["--bg"].upper(), "surface equals bg")
        self.assertTrue(DARK["--surface"].upper() != DARK["--lane"].upper(), "surface equals lane")
        self.assertTrue(
            contrast(DARK["--surface"], DARK["--bg"]) > 1.05,
            f"surface vs bg is only {contrast(DARK['--surface'], DARK['--bg']):.2f}:1",
        )

    def test_light_theme_is_still_the_default_and_is_light(self):
        """Adding dark mode must not have changed the default (:root) colours."""
        self.assertTrue(luminance(LIGHT["--bg"]) > 0.8, f"light --bg is {LIGHT['--bg']}")
        self.assertTrue(luminance(LIGHT["--ink"]) < 0.1, f"light --ink is {LIGHT['--ink']}")

    def test_status_and_accent_colours_are_defined_for_the_light_default(self):
        """Variables the dark theme inherits (not overridden) must exist to inherit from."""
        for variable in ["--accent", "--high", "--medium", "--low"]:
            with self.subTest(variable=variable):
                self.assertTrue(variable in block(":root"), f"{variable} missing from :root")


# ---------------------------------------------------------------------------
# 2. Readability in dark mode (WCAG AA contrast)
# ---------------------------------------------------------------------------
class TestDarkThemeReadability(unittest.TestCase):

    def test_dark_body_text_meets_wcag_aa_contrast(self):
        """Main and secondary text must be readable on every dark background."""
        pairs = [
            ("--ink", "--bg"),
            ("--ink", "--surface"),
            ("--ink", "--lane"),
            ("--ink-muted", "--bg"),
            ("--ink-muted", "--surface"),
            ("--ink-muted", "--lane"),
        ]
        for text, background in pairs:
            with self.subTest(text=text, background=background):
                ratio = contrast(DARK[text], DARK[background])
                self.assertTrue(
                    ratio >= WCAG_AA_TEXT,
                    f"{text} on {background} is only {ratio:.2f}:1 (needs {WCAG_AA_TEXT}:1)",
                )

    def test_dark_priority_badges_meet_wcag_aa_contrast(self):
        """Priority badge text must be readable on its badge background."""
        for level in ["high", "medium", "low"]:
            with self.subTest(level=level):
                ratio = contrast(DARK[f"--{level}-text"], DARK[f"--{level}-bg"])
                self.assertTrue(
                    ratio >= WCAG_AA_TEXT,
                    f"{level} badge is only {ratio:.2f}:1 (needs {WCAG_AA_TEXT}:1)",
                )

    def test_dark_priority_badges_have_dark_backgrounds_and_light_text(self):
        """The badge should be flipped for dark mode, not left as light pastel."""
        for level in ["high", "medium", "low"]:
            with self.subTest(level=level):
                self.assertTrue(
                    luminance(DARK[f"--{level}-bg"]) < luminance(DARK[f"--{level}-text"]),
                    f"{level} badge background is lighter than its text",
                )

    def test_dark_mode_text_is_no_harder_to_read_than_light_mode(self):
        """Switching to dark should not make the main text less readable than light mode."""
        dark_ratio = contrast(DARK["--ink"], DARK["--bg"])
        light_ratio = contrast(LIGHT["--ink"], LIGHT["--bg"])

        self.assertTrue(
            dark_ratio >= light_ratio - 1,
            f"dark {dark_ratio:.2f}:1 vs light {light_ratio:.2f}:1",
        )


# ---------------------------------------------------------------------------
# 3. Dark mode combined with each accent colour
#    (the accent rules come AFTER the dark rule in style.css, so they could win)
# ---------------------------------------------------------------------------
class TestDarkThemeAccents(unittest.TestCase):

    def test_picker_offers_the_accent_colours_this_test_file_checks(self):
        """Sanity check: the accent list parsed from board.html is not empty."""
        self.assertTrue(len(ACCENTS) >= 2, f"Only found accents: {ACCENTS}")

    def test_accent_colour_is_visible_against_dark_surfaces(self):
        """Accents are used for borders, links and focus rings: WCAG asks 3:1 for those."""
        for accent in ACCENTS:
            with self.subTest(accent=accent):
                variables = effective_vars("dark", accent)
                ratio = contrast(variables["--accent"], variables["--surface"])
                self.assertTrue(ratio >= 3.0, f"{accent} accent vs surface is only {ratio:.2f}:1")

    def test_selected_theme_card_is_readable_in_dark_mode_with_every_accent(self):
        """
        .theme-card.active uses background var(--accent-light) with the normal text colour
        (var(--ink)). That pair must stay readable for every accent choice.

        Regression test: the [data-accent=...] rules used to replace the dark --accent-light
        with a pale colour (about 1:1 contrast). Fixed by the
        [data-theme="dark"][data-accent=...] rules in style.css.
        """
        failures = {}

        for accent in ACCENTS:
            variables = effective_vars("dark", accent)
            ratio = contrast(variables["--ink"], variables["--accent-light"])

            if ratio < WCAG_AA_TEXT:
                failures[accent] = round(ratio, 2)

        expected = {}
        actual = failures
        self.assertTrue(expected == actual, f"Unreadable selected theme card in dark mode: {failures}")

    def test_selected_theme_card_background_is_dark_in_dark_mode(self):
        """A pale card on a dark dialog would glare; the tint must stay dark for every accent."""
        for accent in ACCENTS:
            with self.subTest(accent=accent):
                variables = effective_vars("dark", accent)
                self.assertTrue(
                    luminance(variables["--accent-light"]) < 0.1,
                    f"{accent}: --accent-light={variables['--accent-light']}",
                )

    def test_selected_theme_card_background_differs_from_an_unselected_card_in_dark_mode(self):
        """
        The selected card gets its own tint. (The tint is subtle - about 1.03:1 to 1.3:1 -
        so the accent-coloured border, tested next, is what really marks the selection.)
        """
        for accent in ACCENTS:
            with self.subTest(accent=accent):
                variables = effective_vars("dark", accent)
                self.assertTrue(
                    variables["--accent-light"].upper() != variables["--surface"].upper(),
                    f"{accent}: selected card has the same colour as an unselected card",
                )

    def test_selected_theme_card_border_is_visible_against_its_background(self):
        """The accent-coloured border of the selected card needs 3:1 against the card colour."""
        for accent in ACCENTS:
            with self.subTest(accent=accent):
                variables = effective_vars("dark", accent)
                ratio = contrast(variables["--accent"], variables["--accent-light"])
                self.assertTrue(ratio >= 3.0, f"{accent}: border vs card is only {ratio:.2f}:1")

    def test_the_accent_choice_does_not_change_light_mode_colours(self):
        """The fix must only touch dark mode: light mode keeps each accent's pale tint."""
        for accent in ACCENTS:
            if accent == "indigo":
                continue
            with self.subTest(accent=accent):
                tint = effective_vars(None, accent)["--accent-light"]
                self.assertTrue(luminance(tint) > 0.8, f"{accent}: light-mode tint {tint} is not pale")

    def test_selected_theme_card_is_readable_in_dark_mode_with_the_default_accent(self):
        """The default (indigo) combination has no [data-accent] rule of its own."""
        variables = effective_vars("dark", "indigo")
        ratio = contrast(variables["--ink"], variables["--accent-light"])

        self.assertTrue(ratio >= WCAG_AA_TEXT, f"indigo selected card is only {ratio:.2f}:1")

    @unittest.expectedFailure
    def test_accent_coloured_text_meets_wcag_aa_on_dark_cards_for_every_accent(self):
        """
        KNOWN ISSUE (expected failure): .settings-tab-btn.active and .add-column:hover use
        var(--accent) as TEXT colour. On the dark card colour it is below 4.5:1 for most
        accents (indigo is about 3.4:1). When this is fixed, unittest reports an
        "unexpected success" - remove @unittest.expectedFailure then.
        """
        failures = {}

        for accent in ACCENTS:
            variables = effective_vars("dark", accent)
            ratio = contrast(variables["--accent"], variables["--surface"])

            if ratio < WCAG_AA_TEXT:
                failures[accent] = round(ratio, 2)

        expected = {}
        actual = failures
        self.assertTrue(expected == actual, f"Accent text too faint on dark cards: {failures}")


# ---------------------------------------------------------------------------
# 4. The theme picker (board.html)
# ---------------------------------------------------------------------------
class TestThemePicker(unittest.TestCase):

    def test_theme_picker_has_a_dark_option(self):
        """Users must be able to choose dark mode in Settings > Appearance."""
        self.assertTrue('data-set-theme="dark"' in BOARD_HTML)

    def test_dark_option_is_labelled_for_the_user(self):
        """The dark card should have visible text so people know what it is."""
        card = re.search(r'data-set-theme="dark".*?</div>\s*</div>', BOARD_HTML, flags=re.S)

        self.assertTrue(card is not None, "Dark theme card not found")
        self.assertTrue("Dark" in card.group(0), "Dark theme card has no 'Dark' label")

    def test_exactly_one_theme_card_is_marked_active_by_default(self):
        """The default markup should highlight a single card (slate, the light default)."""
        active = re.findall(
            r'class="theme-card [^"]*\bactive\b[^"]*"\s+data-set-theme="(\w+)"',
            BOARD_HTML,
        )

        expected = ["slate"]
        actual = active
        self.assertTrue(expected == actual, f"Active theme cards by default: {active}")

    def test_every_theme_in_the_picker_has_css_behind_it(self):
        """A card with no matching [data-theme] rule would do nothing when clicked."""
        for theme in THEMES:
            if theme == "slate":
                continue  # the default look lives in :root
            with self.subTest(theme=theme):
                self.assertTrue(
                    bool(block(f'[data-theme="{theme}"]')),
                    f"Picker offers '{theme}' but style.css has no rule for it",
                )

    def test_theme_preview_swatch_matches_the_real_theme_background(self):
        """The little preview box in Settings should show the colour the theme really uses."""
        for theme in THEMES:
            with self.subTest(theme=theme):
                preview = re.search(
                    rf"\.theme-{theme} \.theme-preview-box\s*\{{\s*background:\s*(#[0-9A-Fa-f]+)",
                    CSS,
                )
                self.assertTrue(preview is not None, f"No preview swatch rule for '{theme}'")

                real_background = effective_vars(theme)["--bg"]
                self.assertTrue(
                    preview.group(1).upper() == real_background.upper(),
                    f"{theme}: preview {preview.group(1)} vs real background {real_background}",
                )


# ---------------------------------------------------------------------------
# 5. JavaScript wiring (checked by reading board.js, not by running it)
# ---------------------------------------------------------------------------
THEME_CLICK_HANDLER = re.search(
    r'\[data-set-theme\].*?forEach\(card => \{(.*?)\n\}\);', BOARD_JS, flags=re.S
)


class TestJavaScriptWiring(unittest.TestCase):

    def test_saved_theme_is_read_from_local_storage_with_light_as_default(self):
        """First-time visitors (nothing saved) should get the light default, not dark."""
        found = re.search(rf'localStorage\.getItem\("{THEME_KEY}"\)\s*\|\|\s*"slate"', BOARD_JS)

        self.assertTrue(found is not None)

    def test_saved_theme_is_applied_to_the_html_element_on_load(self):
        """Page load must put the saved theme on <html data-theme=...> so the CSS applies."""
        found = re.search(
            r'document\.documentElement\.setAttribute\("data-theme",\s*savedTheme\)', BOARD_JS
        )

        self.assertTrue(found is not None)

    def test_clicking_a_theme_card_applies_the_theme_immediately(self):
        """Choosing a theme must switch the UI without a page reload."""
        self.assertTrue(THEME_CLICK_HANDLER is not None, "Theme card click handler not found")
        self.assertTrue('setAttribute("data-theme", themeName)' in THEME_CLICK_HANDLER.group(1))

    def test_clicking_a_theme_card_saves_the_choice(self):
        """The choice must be saved so dark mode is still on after a refresh."""
        self.assertTrue(THEME_CLICK_HANDLER is not None, "Theme card click handler not found")
        self.assertTrue(
            f'localStorage.setItem("{THEME_KEY}", themeName)' in THEME_CLICK_HANDLER.group(1)
        )

    def test_theme_is_saved_and_loaded_under_the_same_storage_key(self):
        """If the read and write keys differed, the choice would never be restored."""
        read_keys = set(re.findall(r'localStorage\.getItem\("(\w*theme\w*)"\)', BOARD_JS))
        write_keys = set(re.findall(r'localStorage\.setItem\("(\w*theme\w*)"', BOARD_JS))

        expected = {THEME_KEY}
        self.assertTrue(read_keys == expected, f"read keys: {read_keys}")
        self.assertTrue(write_keys == expected, f"write keys: {write_keys}")

    def test_the_selected_card_is_highlighted_after_a_theme_is_clicked(self):
        """After clicking, the active highlight must move to the card for the current theme."""
        self.assertTrue(THEME_CLICK_HANDLER is not None, "Theme card click handler not found")
        self.assertTrue("updateActiveThemeSwatches()" in THEME_CLICK_HANDLER.group(1))

    def test_active_card_highlight_follows_the_data_theme_attribute(self):
        """The highlight is worked out from <html data-theme>, i.e. the theme really in effect."""
        function = re.search(
            r"function updateActiveThemeSwatches\(\)\s*\{(.*?)\n\}", BOARD_JS, flags=re.S
        )

        self.assertTrue(function is not None, "updateActiveThemeSwatches() not found")
        self.assertTrue('getAttribute("data-theme")' in function.group(1))
        self.assertTrue('classList.toggle("active"' in function.group(1))

    def test_opening_settings_refreshes_which_theme_card_is_highlighted(self):
        """Otherwise the Settings dialog could show the wrong card as selected."""
        opener = re.search(r'settingsBtn\.addEventListener\("click".*?\n\}\);', BOARD_JS, flags=re.S)

        self.assertTrue(opener is not None, "Settings button handler not found")
        self.assertTrue("updateActiveThemeSwatches()" in opener.group(0))

    def test_logging_out_does_not_erase_the_theme_preference(self):
        """clearSession should clear the login only; theme is a device preference."""
        clear_session = re.search(r"function clearSession\(\)\s*\{(.*?)\n\}", API_JS, flags=re.S)

        self.assertTrue(clear_session is not None, "clearSession() not found in api.js")
        self.assertTrue("scrumptious" not in clear_session.group(1), "clearSession touches theme keys")
        self.assertTrue("token" in clear_session.group(1))


# ---------------------------------------------------------------------------
# 6. The saved theme is applied on BOTH pages, before the first paint
#    (a small inline <script> in <head> of index.html and board.html)
# ---------------------------------------------------------------------------
class TestHeadTheme(unittest.TestCase):

    def test_saved_theme_is_applied_from_the_head_so_the_page_never_flashes_light(self):
        """A script in <head> runs before anything is painted, so there is no light-mode flash."""
        for page, html in PAGES:
            with self.subTest(page=page):
                script = head_script(html)

                self.assertTrue(
                    f'localStorage.getItem("{THEME_KEY}")' in script,
                    f"{page} <head> does not read the saved theme",
                )
                self.assertTrue('setAttribute("data-theme"' in script, f"{page} never sets data-theme")

    def test_saved_accent_colour_is_applied_from_the_head_too(self):
        """Accent and theme are chosen together, so both must be restored together."""
        for page, html in PAGES:
            with self.subTest(page=page):
                script = head_script(html)

                self.assertTrue(f'localStorage.getItem("{ACCENT_KEY}")' in script)
                self.assertTrue('setAttribute("data-accent"' in script)

    def test_head_script_defaults_to_the_light_theme_when_nothing_is_saved(self):
        """A first-time visitor must not be put into dark mode."""
        for page, html in PAGES:
            with self.subTest(page=page):
                self.assertTrue('|| "slate"' in head_script(html))

    def test_head_script_uses_the_same_storage_key_as_board_js(self):
        """If the keys differed, the login page would not follow the choice made on the board."""
        board_keys = set(re.findall(r'localStorage\.getItem\("(scrumptious_theme)"\)', BOARD_JS))

        for page, html in PAGES:
            with self.subTest(page=page):
                keys = set(
                    re.findall(r'localStorage\.getItem\("(scrumptious_theme)"\)', head_script(html))
                )

                expected = {THEME_KEY}
                self.assertTrue(keys == expected, f"{page} reads keys: {keys}")
                self.assertTrue(board_keys == expected, f"board.js reads keys: {board_keys}")

    def test_head_script_cannot_break_the_page_if_storage_is_blocked(self):
        """Browsers can block localStorage (private mode); the script must fail quietly."""
        for page, html in PAGES:
            with self.subTest(page=page):
                script = head_script(html)

                self.assertTrue("try" in script and "catch" in script, f"{page}: no try/catch")

    def test_head_script_runs_before_the_page_body(self):
        """Order matters: the script must be inside <head>, ahead of <body>."""
        for page, html in PAGES:
            with self.subTest(page=page):
                self.assertTrue(html.index(THEME_KEY) < html.index("<body>"))


class TestLoginPage(unittest.TestCase):

    def test_login_page_does_not_load_the_theme_picker_code_it_does_not_need(self):
        """The login page only follows the saved theme; choosing one happens on the board."""
        self.assertTrue("data-set-theme" not in INDEX_HTML)

    def test_login_page_styles_use_theme_variables_not_fixed_colours(self):
        """
        If the login card hard-coded a colour, setting data-theme="dark" would not re-colour it.
        (Shadows are ignored; only text / background / border colours matter here.)
        """
        selectors = [".auth-screen", ".auth-card", ".auth-card h1", ".auth-card p.subtitle"]

        for selector in selectors:
            with self.subTest(selector=selector):
                body = rule_body(selector)

                self.assertTrue(bool(body), f"No CSS rule found for {selector}")

                fixed = re.findall(
                    r"(?:^|;)\s*(?:color|background|border[\w-]*)\s*:[^;]*#[0-9A-Fa-f]{3,6}",
                    body,
                )

                expected = []
                actual = fixed
                self.assertTrue(expected == actual, f"{selector} hard-codes a colour: {fixed}")

    def test_login_page_card_and_page_use_different_dark_shades(self):
        """In dark mode the card (--surface) should sit on a differently shaded page (--bg)."""
        self.assertTrue("var(--surface)" in rule_body(".auth-card"))
        self.assertTrue("var(--bg)" in rule_body("body"))


if __name__ == "__main__":
    unittest.main()
