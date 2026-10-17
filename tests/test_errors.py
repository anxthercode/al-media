from al_media.core.errors import classify_engine_error
from al_media.core.metadata import available_selections
from al_media.models import Task


def test_youtube_challenge_has_actionable_category_without_leaking_output():
    lines = [
        "WARNING: [youtube] No title found; use cookies if needed",
        "ERROR: [youtube] abc: Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies token=secret",
    ]
    assert classify_engine_error(lines) == "error_youtube_verification"


def test_final_error_takes_priority_over_cookie_warning():
    lines = ["WARNING: Cookies may help", "ERROR: Network timed out"]
    assert classify_engine_error(lines) == "error_network"


def test_browser_cookie_failure_is_distinct_from_site_auth():
    assert classify_engine_error(["ERROR: Could not copy Chrome cookie database"]) == "error_cookies_unreadable"


def test_private_and_unavailable_are_distinct():
    assert classify_engine_error(["ERROR: Private video"]) == "error_private_media"
    assert classify_engine_error(["ERROR: This video is unavailable"]) == "error_unavailable"


def test_malformed_formats_do_not_crash_selector():
    assert available_selections({"formats": {"bad": "shape"}}) == []
    assert available_selections({"formats": [None, "not a format"]}) == []


def test_previous_authorization_error_loads_as_actionable_code():
    data = Task("https://example.test/video").to_dict()
    data["error"] = "Access requires authorization / Требуется разрешённая авторизация"
    assert Task.from_dict(data).error == "error_auth_required"
