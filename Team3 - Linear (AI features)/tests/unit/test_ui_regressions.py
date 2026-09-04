from pathlib import Path

from warrant.config import PROJECT_ROOT
from warrant.providers import FixtureProvider
from warrant.retrieval import titles_are_near_duplicates
from warrant.schemas import ExtractionResult
from warrant.seed import HEADLINE_ISSUES

STATIC = PROJECT_ROOT / "src" / "warrant" / "static"
TEMPLATES = PROJECT_ROOT / "src" / "warrant" / "templates"


def css() -> str:
    return (STATIC / "app.css").read_text()


def template(name: str) -> str:
    return (TEMPLATES / name).read_text()


def test_fixture_extracts_sentence_level_acceptance_criteria():
    issue = HEADLINE_ISSUES[0]
    response = FixtureProvider().extract(
        f"{issue['title']}\n{issue['body']}", list(issue["paths"]), []
    )
    assert isinstance(response.value, ExtractionResult)
    criteria = response.value.acceptance_criteria
    assert 2 <= len(criteria) <= 3
    assert criteria[0] == "Expected: a second retry must not create another charge."
    assert criteria[1].endswith("double-submit.")
    assert all(not item.endswith(" and") for item in criteria)


def test_near_duplicate_title_detection_is_token_based():
    assert titles_are_near_duplicates("Billing timeout after retry", "Billing: timeout after retry")
    assert not titles_are_near_duplicates(
        "Billing timeout after retry during renewal",
        "Billing duplicate notification during a bulk operation",
    )


# --- design system invariants ---------------------------------------------------------


def test_palette_is_dark_first_with_the_complete_token_set_on_bare_root():
    source = css()
    bare = source.split("@media (prefers-color-scheme: light)")[0]
    for token, value in (
        ("--ground", "#0d1014"),
        ("--surface", "#161b21"),
        ("--raised", "#1d232b"),
        ("--hover", "#20272f"),
        ("--line", "#272f38"),
        ("--ink", "#e6eaee"),
        ("--muted", "#8a95a1"),
        ("--faint", "#5d6873"),
        ("--accent", "#5fb3c9"),
        ("--allow", "#48a173"),
        ("--hold", "#c99331"),
        ("--deny", "#d06054"),
    ):
        assert f"{token}:{value}" in bare, f"{token} must be defined on bare :root"
    # the semantic triad keeps its own background and line variants, separate from the accent
    for token in (
        "--allow-bg",
        "--allow-line",
        "--hold-bg",
        "--hold-line",
        "--deny-bg",
        "--deny-line",
    ):
        assert f"{token}:" in bare


def test_light_theme_is_defined_for_both_the_system_preference_and_the_explicit_stamp():
    source = css()
    assert '@media (prefers-color-scheme: light){\n  :root:not([data-theme="dark"]){' in source
    assert ':root[data-theme="light"]{' in source
    # a light override must never be the only definition of a colour
    for block in source.split(':root[data-theme="light"]{')[1:]:
        overrides = block.split("}")[0]
        assert "--ground:" in overrides and "--ink:" in overrides


def test_body_paints_an_explicit_token_background_and_loads_the_type_stack():
    source = css()
    assert "body{margin:0;background:var(--ground);color:var(--ink)" in source
    assert '--sans:"IBM Plex Sans"' in source
    assert '--cond:"IBM Plex Sans Condensed"' in source
    assert '--mono:"IBM Plex Mono"' in source
    # real fallbacks, not a bare webfont name
    assert "ui-sans-serif,system-ui" in source
    assert "ui-monospace,SFMono-Regular,Menlo,monospace" in source
    shell = template("base.html")
    assert "fonts.googleapis.com/css2?family=IBM+Plex+Sans" in shell
    assert "IBM+Plex+Sans+Condensed" in shell and "IBM+Plex+Mono" in shell
    assert "preconnect" in shell and "fonts.gstatic.com" in shell


def test_layout_is_the_three_column_operator_shell_with_documented_breakpoints():
    source = css()
    assert "body.shell{height:100vh;display:flex;flex-direction:column;overflow:hidden}" in source
    assert 'class="shell"' in template("base.html")
    assert ".app{display:grid;grid-template-columns:236px minmax(0,1fr)" in source
    assert ".body{display:grid;grid-template-columns:minmax(0,1fr) 320px" in source
    assert ".view-head{" in source and "height:45px" in source
    assert ".row{" in source and "height:37px" in source
    # the rail collapses at 1180px and the sidebar at 900px
    rail_collapse = (
        "@media (max-width:1180px){.body{grid-template-columns:minmax(0,1fr)}.rail{display:none}}"
    )
    assert rail_collapse in source
    sidebar_collapse = (
        "@media (max-width:900px){\n"
        "  body.shell{height:auto;overflow:visible}\n"
        "  .app{grid-template-columns:1fr}\n"
        "  .side{display:none}\n"
    )
    assert sidebar_collapse in source


def test_wide_content_scrolls_inside_its_own_container_and_the_body_never_does():
    source = css()
    assert "html,body{max-width:100%;overflow-x:hidden}" in source
    for rule in (".table-wrap{overflow-x:auto", ".diff{", "pre.raw{"):
        assert rule in source
    assert source.count("overflow-x:auto") >= 4


def test_the_sufficiency_ring_and_semantic_row_vocabulary_are_styled():
    source = css()
    assert ".ring{width:15px;height:15px" in source
    assert ".ring .arc{fill:none;stroke-width:2.4" in source
    assert ".ring .tick{" in source
    for tone in ("allow", "hold", "deny"):
        assert f".ring.{tone} .arc{{stroke:var(--{tone})}}" in source
        assert f".code-chip.{tone}{{" in source
        assert f".group.{tone} .group-name{{color:var(--{tone})}}" in source
    assert ".meter u{" in source, "the meter needs a threshold marker"


def test_radii_stay_small_and_motion_and_focus_are_respected():
    source = css()
    assert "@media (prefers-reduced-motion: reduce){*{transition:none!important" in source
    assert ":focus-visible{outline:2px solid var(--accent)" in source
    radii = {int(value) for value in __import__("re").findall(r"border-radius:(\d+)px", source)}
    assert radii, "expected explicit radii"
    assert max(radii) <= 8, f"radii should stay small, found {sorted(radii)}"


def test_provider_kind_is_visually_distinct_so_a_mock_run_cannot_read_as_real():
    source = css()
    assert ".provider-kind.real{" in source and "var(--allow)" in source
    assert ".provider-kind.mock{" in source
    assert "var(--hold)" in source
    session = template("coding_session.html")
    assert 'class="provider-kind {{ s.provider_kind }}">{{ s.provider_kind|upper }}' in session
    assert "nothing in this session was produced by a real coding agent" in session


def test_the_editorial_theme_is_fully_gone():
    source = css()
    for stale in ("Georgia", "#f4f2ea", "--paper", "--green2", "backdrop-filter", ".topbar"):
        assert stale not in source, f"{stale} is left over from the previous theme"
    for name in sorted(path.name for path in TEMPLATES.glob("*.html")):
        body = template(name)
        assert "Georgia" not in body, name
        assert "Operator inbox" not in body, name


def test_every_page_template_extends_the_shell_except_the_standalone_sign_in():
    names = sorted(path.name for path in TEMPLATES.glob("*.html"))
    assert "base.html" in names and "_macros.html" in names
    for name in names:
        if name in {"base.html", "_macros.html", "login.html"}:
            continue
        body = template(name)
        assert body.startswith('{% extends "base.html" %}'), name
        assert "{% block content %}" in body, name
        assert "{% block view_title %}" in body, name
    # the sign-in page is standalone but still uses the same design system
    login = template("login.html")
    assert "<!doctype html>" in login
    assert "/static/app.css" in login
    assert "demo identity gate" in login
    assert 'class="table-wrap"' in login


def test_shell_keeps_the_shared_client_contract_and_integrity_surfaces():
    shell = template("base.html")
    assert "'X-CSRF-Token':window.WARRANT.csrf" in shell
    assert "class ApiError extends Error" in shell
    assert "function renderError(" in shell
    assert "401:'Authentication required'" in shell
    assert "403:'Authority prohibited'" in shell
    assert "409:'State conflict'" in shell
    assert "410:'Authority expired'" in shell
    assert "422:'Evidence or policy invalid'" in shell
    assert "function formatRelative(" in shell and ".relative-time" in shell
    assert "function toast(" in shell
    assert "fetch('/healthz')" in shell
    assert 'id="health-mode"' in shell and 'id="degraded-banner"' in shell
    assert "SIMULATED · FIXTURE AI" in shell
    # the acting-identity switcher and the signed-in footer both survive
    assert 'id="actor-switcher"' in shell
    assert "Signed in as <b>{{ current_user.display_name }}" in shell
    assert 'action="/logout"' in shell


def test_command_palette_and_shortcuts_are_wired_to_real_navigation():
    shell = template("base.html")
    assert 'id="palette-scrim"' in shell
    assert "(event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'" in shell
    assert "function registerCommand(" in shell and "function registerShortcut(" in shell
    for target in (
        "'/'",
        "'/delegations'",
        "'/coding-sessions'",
        "'/code'",
        "'/policy'",
        "'/evaluation'",
        "'/integrations'",
    ):
        assert f"location.href={target}" in shell
    queue = template("dashboard.html")
    for key in ("'1'", "'3'", "'h'", "'c'", "'enter'"):
        assert f"registerShortcut({key}" in queue
    assert "decide('approve')" in queue and "decide('deny')" in queue
    assert "decide('defer')" in queue
    assert "startCoding" in queue


def test_macros_compute_the_ring_from_real_values_and_never_invent_them():
    macros = template("_macros.html")
    assert 'stroke-dasharray="37.7"' in macros
    assert "37.7 * (1 - value)" in macros
    assert "threshold * 360" in macros
    assert 'role="img"' in macros
    assert Path(STATIC / "app.css").exists()
