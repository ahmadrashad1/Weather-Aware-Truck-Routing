from django.test import Client, override_settings


@override_settings(APP_VERSION="abc123")
def test_health_reports_the_running_version(client: Client) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    # The deploy workflow waits for this version to confirm a deployment finished.
    assert response.json() == {"status": "ok", "version": "abc123"}
