import pytest

from app.config import Settings


def production(**changes):
    values = dict(_env_file=None, app_env="production", demo_mode=False,
                  secret_key="release-test-secret-" * 3, patient_otp_provider="disabled",
                  cookie_secure=True, public_app_url="https://example.test")
    return Settings(**(values | changes))


@pytest.mark.parametrize("changes", [
    {"patient_otp_provider": "development"}, {"demo_mode": True},
    {"secret_key": "short"}, {"cookie_secure": False},
    {"public_app_url": "http://example.test"},
])
def test_rejects_unsafe_production_configuration(changes):
    with pytest.raises(RuntimeError):
        production(**changes).validate_for_startup()


def test_accepts_secure_production_configuration():
    production().validate_for_startup()


@pytest.mark.parametrize("environment,demo", [("production", True), ("development", False)])
def test_seed_entrypoint_never_accesses_database_when_disabled(monkeypatch, environment, demo):
    from app import seed
    monkeypatch.setattr(seed.settings, "app_env", environment)
    monkeypatch.setattr(seed.settings, "demo_mode", demo)
    def forbidden():
        raise AssertionError("Disabled seeding accessed the database")
    monkeypatch.setattr(seed, "SessionLocal", forbidden)
    seed.main()
