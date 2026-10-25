from app.roboflow import configuration_status


def test_placeholder_workflow_is_not_reported_as_configured(monkeypatch):
    monkeypatch.setenv("ROBOFLOW_ENABLED", "true")
    monkeypatch.setenv("ROBOFLOW_WORKSPACE", "visionfit")
    monkeypatch.setenv("ROBOFLOW_API_KEY", "test-key")
    monkeypatch.setenv("ROBOFLOW_KEYPOINT_WORKFLOW_ID", "first-workflow-id")

    status = configuration_status()

    assert status["configured"] is False
    assert status["ready"] is False
    assert "placeholder" in status["reason"].lower()
