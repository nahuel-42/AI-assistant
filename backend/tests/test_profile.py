from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

PROFILE = "# Profile\nName: Test Person\nExperience: built a CI/CD pipeline that cut deploys by 80%."


def make_client(tmp_path):
    return TestClient(create_app(Settings(data_dir=tmp_path, ai_provider="echo", audio_enabled=False, tts_enabled=False)))


def test_profile_is_saved_and_survives_restart(tmp_path):
    with make_client(tmp_path) as c:
        assert c.get("/api/profile").json() == {"text": ""}
        assert c.put("/api/profile", json={"text": PROFILE + "\n\n"}).json() == {"text": PROFILE}
    with make_client(tmp_path) as c:  # new app instance, same data folder
        assert c.get("/api/profile").json()["text"] == PROFILE


def test_profile_is_sent_as_personal_context(tmp_path):
    with make_client(tmp_path) as c:
        c.put("/api/profile", json={"text": PROFILE})
        manager = c.app.state.manager
        assert "cut deploys by 80%" in manager._context.build_system()
        c.post("/api/sessions", json={})  # a new session keeps the profile
        assert "cut deploys by 80%" in manager._context.build_system()
        c.put("/api/profile", json={"text": "Updated"})  # edits apply to the running session
        assert "Updated" in manager._context.build_system()
        c.post("/api/sessions/current/stop")


def test_answer_style_defaults_is_editable_and_resets(tmp_path):
    from app.services.context.manager import DEFAULT_ANSWER_STYLE

    with make_client(tmp_path) as c:
        manager = c.app.state.manager
        assert c.get("/api/style").json() == {"text": DEFAULT_ANSWER_STYLE, "is_default": True}
        system = manager._context.build_system()
        assert "<answer_style>" in system and "conviction" in system

        custom = c.put("/api/style", json={"text": "Be very brief."}).json()
        assert custom == {"text": "Be very brief.", "is_default": False}
        assert "Be very brief." in manager._context.build_system()
        c.post("/api/sessions", json={})  # new sessions keep the custom style
        assert "Be very brief." in manager._context.build_system()
        c.post("/api/sessions/current/stop")

        assert c.put("/api/style", json={"text": ""}).json()["is_default"] is True  # reset
    with make_client(tmp_path) as c:
        assert c.get("/api/style").json()["is_default"] is True
