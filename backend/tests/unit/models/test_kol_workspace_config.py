from app.models.kol_workspace_config import _DEFAULT_TABS


def test_default_workspace_tabs_include_full_video_film_review():
    assert "film-review" in _DEFAULT_TABS
