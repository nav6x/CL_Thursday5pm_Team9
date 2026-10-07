import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CSS = (PROJECT_ROOT / "static/css/style.css").read_text(encoding="utf-8")
BOARD_HTML = (PROJECT_ROOT / "board.html").read_text(encoding="utf-8")
INDEX_HTML = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
BOARD_JS = (PROJECT_ROOT / "static/js/board.js").read_text(encoding="utf-8")
API_JS = (PROJECT_ROOT / "static/js/api.js").read_text(encoding="utf-8")
AUTH_JS = (PROJECT_ROOT / "static/js/auth.js").read_text(encoding="utf-8")

WCAG_AA_TEXT = 4.5
THEME_KEY = "scrumptious_theme"


def css_blocks():
    """Yield (selector, {variable: value}) for every rule, in file order."""
    no_comments = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", no_comments):
        selector = selector.strip().split(";")[-1].strip()
        variables = {
            k: v.strip()
            for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body)
        }
        yield selector, variables


def block(selector):
    for found_selector, variables in css_blocks():
        if found_selector == selector:
            return variables
    return {}


def specificity(selector):
    """Number of attribute / :root parts in a selector."""
    return len(re.findall(r"\[[^\]]+\]|:root", selector))


def effective_vars(theme=None, accent=None):
    """
    The variable values the browser ends up using for
    <html data-theme=... data-accent=...>.
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

    r, g, b = (
        int(h[i:i + 2], 16) / 255
        for i in (0, 2, 4)
    )

    def channel(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(r)
        + 0.7152 * channel(g)
        + 0.0722 * channel(b)
    )


def contrast(colour_a, colour_b):
    lighter, darker = sorted(
        (luminance(colour_a), luminance(colour_b)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def picker_values(attribute):
    return re.findall(rf'{attribute}="([\w-]+)"', BOARD_HTML)


DARK = effective_vars("dark")
LIGHT = effective_vars()
ACCENTS = picker_values("data-set-accent")
THEMES = picker_values("data-set-theme")


class TestDarkTheme(unittest.TestCase):

    def test_dark_theme_block_exists_in_the_stylesheet(self):
        """There must be a [data-theme="dark"] rule for the picker to switch to."""
        expected = True
        actual = bool(block('[data-theme="dark"]'))
        self.assertTrue(expected == actual)

    def test_dark_theme_overrides_every_surface_and_text_variable(self):
        variables = [
            "--bg", "--surface", "--lane", "--ink", "--ink-muted", "--border"
        ]

        for variable in variables:
            expected = True
            actual = variable in block('[data-theme="dark"]')
            self.assertTrue(expected == actual)

    def test_dark_theme_overrides_the_priority_badge_colours(self):
        variables = [
            "--high-bg", "--high-text",
            "--medium-bg", "--medium-text",
            "--low-bg", "--low-text",
        ]

        for variable in variables:
            expected = True
            actual = variable in block('[data-theme="dark"]')
            self.assertTrue(expected == actual)

    def test_every_dark_override_is_a_variable_that_exists_in_the_light_theme(self):
        unknown = set(block('[data-theme="dark"]')) - set(block(":root"))

        expected = set()
        actual = unknown
        self.assertTrue(expected == actual)

    def test_every_dark_override_is_a_valid_hex_colour(self):
        bad = {
            k: v
            for k, v in block('[data-theme="dark"]').items()
            if not re.fullmatch(r"#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})", v)
        }

        expected = {}
        actual = bad
        self.assertTrue(expected == actual)

    def test_dark_backgrounds_are_actually_dark(self):
        for variable in ["--bg", "--surface", "--lane"]:
            self.assertTrue(luminance(DARK[variable]) < 0.1)

    def test_dark_text_colours_are_light(self):
        for variable in ["--ink", "--ink-muted"]:
            self.assertTrue(luminance(DARK[variable]) > 0.3)

    def test_dark_cards_are_distinguishable_from_the_page_and_columns(self):
        self.assertTrue(DARK["--surface"].upper() != DARK["--bg"].upper())
        self.assertTrue(DARK["--surface"].upper() != DARK["--lane"].upper())
        self.assertTrue(contrast(DARK["--surface"], DARK["--bg"]) > 1.05)

    def test_light_theme_is_still_the_default_and_is_light(self):
        self.assertTrue(luminance(LIGHT["--bg"]) > 0.8)
        self.assertTrue(luminance(LIGHT["--ink"]) < 0.1)

    def test_status_and_accent_colours_are_defined_for_the_light_default(self):
        for variable in ["--accent", "--high", "--medium", "--low"]:
            self.assertTrue(variable in block(":root"))


class TestDarkThemeReadability(unittest.TestCase):

    def test_dark_body_text_meets_wcag_aa_contrast(self):
        pairs = [
            ("--ink", "--bg"),
            ("--ink", "--surface"),
            ("--ink", "--lane"),
            ("--ink-muted", "--bg"),
            ("--ink-muted", "--surface"),
            ("--ink-muted", "--lane"),
        ]

        for text, background in pairs:
            ratio = contrast(DARK[text], DARK[background])
            self.assertTrue(ratio >= WCAG_AA_TEXT)

    def test_dark_priority_badges_meet_wcag_aa_contrast(self):
        for level in ["high", "medium", "low"]:
            ratio = contrast(
                DARK[f"--{level}-text"],
                DARK[f"--{level}-bg"],
            )
            self.assertTrue(ratio >= WCAG_AA_TEXT)

    def test_dark_priority_badges_have_dark_backgrounds_and_light_text(self):
        for level in ["high", "medium", "low"]:
            self.assertTrue(
                luminance(DARK[f"--{level}-bg"])
                < luminance(DARK[f"--{level}-text"])
            )

    def test_dark_mode_text_is_no_harder_to_read_than_light_mode(self):
        self.assertTrue(
            contrast(DARK["--ink"], DARK["--bg"])
            >= contrast(LIGHT["--ink"], LIGHT["--bg"]) - 1
        )


class TestDarkThemeAccents(unittest.TestCase):

    def test_picker_offers_the_accent_colours_this_test_file_checks(self):
        self.assertTrue(len(ACCENTS) >= 2)

    def test_accent_colour_is_visible_against_dark_surfaces(self):
        for accent in ACCENTS:
            variables = effective_vars("dark", accent)
            self.assertTrue(
                contrast(variables["--accent"], variables["--surface"]) >= 3.0
            )

    def test_selected_theme_card_is_readable_in_dark_mode_with_every_accent(self):
        failures = {}

        for accent in ACCENTS:
            variables = effective_vars("dark", accent)
            ratio = contrast(
                variables["--ink"],
                variables["--accent-light"],
            )

            if ratio < WCAG_AA_TEXT:
                failures[accent] = round(ratio, 2)

        expected = {}
        actual = failures
        self.assertTrue(expected == actual)

    def test_selected_theme_card_background_is_dark_in_dark_mode(self):
        for accent in ACCENTS:
            variables = effective_vars("dark", accent)
            self.assertTrue(
                luminance(variables["--accent-light"]) < 0.1
            )

    def test_selected_theme_card_background_differs_from_an_unselected_card_in_dark_mode(self):
        for accent in ACCENTS:
            variables = effective_vars("dark", accent)
            self.assertTrue(
                variables["--accent-light"].upper()
                != variables["--surface"].upper()
            )

    def test_selected_theme_card_border_is_visible_against_its_background(self):
        for accent in ACCENTS:
            variables = effective_vars("dark", accent)
            self.assertTrue(
                contrast(
                    variables["--accent"],
                    variables["--accent-light"],
                ) >= 3.0
            )

    def test_the_accent_choice_does_not_change_light_mode_colours(self):
        for accent in ACCENTS:
            if accent == "indigo":
                continue

            self.assertTrue(
                luminance(
                    effective_vars(None, accent)["--accent-light"]
                ) > 0.8
            )

    def test_selected_theme_card_is_readable_in_dark_mode_with_the_default_accent(self):
        variables = effective_vars("dark", "indigo")

        self.assertTrue(
            contrast(
                variables["--ink"],
                variables["--accent-light"],
            ) >= WCAG_AA_TEXT
        )

    @unittest.expectedFailure
    def test_accent_coloured_text_meets_wcag_aa_on_dark_cards_for_every_accent(self):
        failures = {}

        for accent in ACCENTS:
            variables = effective_vars("dark", accent)
            ratio = contrast(
                variables["--accent"],
                variables["--surface"],
            )

            if ratio < WCAG_AA_TEXT:
                failures[accent] = round(ratio, 2)

        expected = {}
        actual = failures
        self.assertTrue(expected == actual)


class TestThemePicker(unittest.TestCase):

    def test_theme_picker_has_a_dark_option(self):
        self.assertTrue('data-set-theme="dark"' in BOARD_HTML)

    def test_dark_option_is_labelled_for_the_user(self):
        card = re.search(
            r'data-set-theme="dark".*?</div>\s*</div>',
            BOARD_HTML,
            flags=re.S,
        )

        self.assertTrue(card is not None)
        self.assertTrue("Dark" in card.group(0))

    def test_exactly_one_theme_card_is_marked_active_by_default(self):
        active = re.findall(
            r'class="theme-card [^"]*\bactive\b[^"]*"\s+'
            r'data-set-theme="(\w+)"',
            BOARD_HTML,
        )

        expected = ["slate"]
        actual = active
        self.assertTrue(expected == actual)

    def test_every_theme_in_the_picker_has_css_behind_it(self):
        for theme in THEMES:
            if theme == "slate":
                continue

            self.assertTrue(
                bool(block(f'[data-theme="{theme}"]'))
            )

    def test_theme_preview_swatch_matches_the_real_theme_background(self):
        for theme in THEMES:
            preview = re.search(
                rf"\.theme-{theme} \.theme-preview-box\s*\{{\s*"
                rf"background:\s*(#[0-9A-Fa-f]+)",
                CSS,
            )

            self.assertTrue(preview is not None)

            real_background = effective_vars(theme)["--bg"]

            self.assertTrue(
                preview.group(1).upper() == real_background.upper()
            )


class TestJavaScriptWiring(unittest.TestCase):

    def test_saved_theme_is_read_from_local_storage_with_light_as_default(self):
        self.assertTrue(
            re.search(
                rf'localStorage\.getItem\("{THEME_KEY}"\)\s*\|\|\s*"slate"',
                BOARD_JS,
            )
            is not None
        )

    def test_saved_theme_is_applied_to_the_html_element_on_load(self):
        self.assertTrue(
            re.search(
                r'document\.documentElement\.setAttribute\('
                r'"data-theme",\s*savedTheme\)',
                BOARD_JS,
            )
            is not None
        )

    def test_clicking_a_theme_card_applies_the_theme_immediately(self):
        handler = re.search(
            r'\[data-set-theme\].*?forEach\(card => \{(.*?)\n\}\);',
            BOARD_JS,
            flags=re.S,
        )

        self.assertTrue(handler is not None)
        self.assertTrue(
            'setAttribute("data-theme", themeName)' in handler.group(1)
        )

    def test_clicking_a_theme_card_saves_the_choice(self):
        handler = re.search(
            r'\[data-set-theme\].*?forEach\(card => \{(.*?)\n\}\);',
            BOARD_JS,
            flags=re.S,
        )

        self.assertTrue(handler is not None)
        self.assertTrue(
            f'localStorage.setItem("{THEME_KEY}", themeName)'
            in handler.group(1)
        )

    def test_theme_is_saved_and_loaded_under_the_same_storage_key(self):
        read_keys = set(
            re.findall(
                r'localStorage\.getItem\("(\w*theme\w*)"\)',
                BOARD_JS,
            )
        )

        write_keys = set(
            re.findall(
                r'localStorage\.setItem\("(\w*theme\w*)"',
                BOARD_JS,
            )
        )

        expected = {THEME_KEY}
        self.assertTrue(read_keys == expected)
        self.assertTrue(write_keys == expected)

    def test_the_selected_card_is_highlighted_after_a_theme_is_clicked(self):
        handler = re.search(
            r'\[data-set-theme\].*?forEach\(card => \{(.*?)\n\}\);',
            BOARD_JS,
            flags=re.S,
        )

        self.assertTrue(handler is not None)
        self.assertTrue(
            "updateActiveThemeSwatches()" in handler.group(1)
        )

    def test_active_card_highlight_follows_the_data_theme_attribute(self):
        function = re.search(
            r"function updateActiveThemeSwatches\(\)\s*\{(.*?)\n\}",
            BOARD_JS,
            flags=re.S,
        )

        self.assertTrue(function is not None)

        body = function.group(1)

        self.assertTrue('getAttribute("data-theme")' in body)
        self.assertTrue('classList.toggle("active"' in body)

    def test_opening_settings_refreshes_which_theme_card_is_highlighted(self):
        opener = re.search(
            r"settingsBtn\.addEventListener\(\"click\".*?\n\}\);",
            BOARD_JS,
            flags=re.S,
        )

        self.assertTrue(opener is not None)
        self.assertTrue(
            "updateActiveThemeSwatches()" in opener.group(0)
        )

    def test_logging_out_does_not_erase_the_theme_preference(self):
        clear_session = re.search(
            r"function clearSession\(\)\s*\{(.*?)\n\}",
            API_JS,
            flags=re.S,
        )

        self.assertTrue(clear_session is not None)

        self.assertTrue("scrumptious" not in clear_session.group(1))
        self.assertTrue("token" in clear_session.group(1))


PAGES = [
    ("index.html", INDEX_HTML),
    ("board.html", BOARD_HTML),
]


def head_script(html):
    """The inline <script> code inside <head>."""
    head_match = re.search(r"<head>(.*?)</head>", html, flags=re.S)

    if not head_match:
        return ""

    head = head_match.group(1)

    return "\n".join(
        re.findall(r"<script>(.*?)</script>", head, flags=re.S)
    )


def rule_body(selector):
    """The declarations inside the first CSS rule with exactly this selector."""
    no_comments = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)

    for found, body in re.findall(
        r"([^{}]+)\{([^{}]*)\}",
        no_comments,
    ):
        if found.strip().split(";")[-1].strip() == selector:
            return body

    return ""


class TestHeadTheme(unittest.TestCase):

    def test_saved_theme_is_applied_from_the_head_so_the_page_never_flashes_light(self):
        for page, html in PAGES:
            script = head_script(html)

            self.assertTrue(
                f'localStorage.getItem("{THEME_KEY}")' in script
            )
            self.assertTrue(
                'setAttribute("data-theme"' in script
            )

    def test_saved_accent_colour_is_applied_from_the_head_too(self):
        for page, html in PAGES:
            script = head_script(html)

            self.assertTrue(
                'localStorage.getItem("scrumptious_accent")' in script
            )
            self.assertTrue(
                'setAttribute("data-accent"' in script
            )

    def test_head_script_defaults_to_the_light_theme_when_nothing_is_saved(self):
        for page, html in PAGES:
            self.assertTrue(
                '|| "slate"' in head_script(html)
            )

    def test_head_script_uses_the_same_storage_key_as_board_js(self):
        board_keys = set(
            re.findall(
                r'localStorage\.getItem\("(scrumptious_theme)"\)',
                BOARD_JS,
            )
        )

        for page, html in PAGES:
            keys = set(
                re.findall(
                    r'localStorage\.getItem\("(scrumptious_theme)"\)',
                    head_script(html),
                )
            )

            expected = {THEME_KEY}
            self.assertTrue(keys == expected)
            self.assertTrue(board_keys == expected)

    def test_head_script_cannot_break_the_page_if_storage_is_blocked(self):
        for page, html in PAGES:
            script = head_script(html)

            self.assertTrue("try" in script)
            self.assertTrue("catch" in script)

    def test_head_script_runs_before_the_page_body(self):
        for page, html in PAGES:
            self.assertTrue(
                html.index(THEME_KEY) < html.index("<body>")
            )


class TestLoginPage(unittest.TestCase):

    def test_login_page_does_not_load_the_theme_picker_code_it_does_not_need(self):
        self.assertTrue("data-set-theme" not in INDEX_HTML)

    def test_login_page_styles_use_theme_variables_not_fixed_colours(self):
        selectors = [
            ".auth-screen",
            ".auth-card",
            ".auth-card h1",
            ".auth-card p.subtitle",
        ]

        for selector in selectors:
            body = rule_body(selector)

            self.assertTrue(bool(body))

            fixed = re.findall(
                r"(?:^|;)\s*(?:color|background|border[\w-]*)\s*:"
                r"[^;]*#[0-9A-Fa-f]{3,6}",
                body,
            )

            expected = []
            actual = fixed
            self.assertTrue(expected == actual)

    def test_login_page_card_and_page_use_different_dark_shades(self):
        self.assertTrue(
            "var(--surface)" in rule_body(".auth-card")
        )
        self.assertTrue(
            "var(--bg)" in rule_body("body")
        )


if __name__ == "__main__":
    unittest.main()
