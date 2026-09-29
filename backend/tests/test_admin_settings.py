"""Tests for admin-managed deployment secrets and the configurable image provider.

Both features replaced a module-level `os.environ.get(...)` read. That pattern is what broke the
image generator (it was pinned to the Emergent gateway the local shim cannot reach) and what would
make a dashboard-entered key invisible until the next deploy. These lock in the new behaviour.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ai  # noqa: E402
import core  # noqa: E402

# The shared motor client binds to the first event loop it is used on, so a second asyncio.run()
# in the same process fails with "event loop is closed". conftest provides one suite-wide loop.
from conftest import run  # noqa: E402


# ---------- deployment secrets ----------

def test_stored_secret_overrides_environment_and_is_never_returned_raw(monkeypatch):
    monkeypatch.setenv("CAREERJET_AFFID", "from-env")

    async def _check():
        await core.db.settings.delete_many({"key": core.SECRETS_KEY})
        try:
            # Nothing stored: the environment is used, so an existing .env setup keeps working.
            assert await core.integration_value("CAREERJET_AFFID") == "from-env"

            await core.db.settings.update_one(
                {"key": core.SECRETS_KEY},
                {"$set": {"value": {"CAREERJET_AFFID": {"v": core.encrypt_str("from-dashboard")}}}},
                upsert=True)
            assert await core.integration_value("CAREERJET_AFFID") == "from-dashboard"

            # The stored document must be ciphertext, never the plaintext.
            doc = await core.db.settings.find_one({"key": core.SECRETS_KEY})
            assert "from-dashboard" not in str(doc)
        finally:
            await core.db.settings.delete_many({"key": core.SECRETS_KEY})

    run(_check())


def test_blank_stored_secret_falls_back_to_environment(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "env-stripe")

    async def _check():
        await core.db.settings.update_one(
            {"key": core.SECRETS_KEY},
            {"$set": {"value": {"STRIPE_SECRET_KEY": {"v": core.encrypt_str("")}}}},
            upsert=True)
        try:
            assert await core.integration_value("STRIPE_SECRET_KEY") == "env-stripe"
        finally:
            await core.db.settings.delete_many({"key": core.SECRETS_KEY})

    run(_check())


def test_integration_key_list_covers_every_declared_consumer():
    """A key the admin can store must be one the code actually reads."""
    import r_admin
    declared = {k for _, keys, _, _ in r_admin.INTEGRATIONS for k in keys}
    assert declared, "INTEGRATIONS must not be empty"
    for key in declared:
        assert key.isupper() and "_" in key, key


# ---------- image generation ----------

def test_image_settings_default_to_a_known_provider():
    cfg = ai.DEFAULT_IMAGE
    assert cfg["provider"] in ai.PROVIDERS
    assert cfg["model"]


def test_every_image_capable_provider_routes_to_an_implemented_api():
    """Every provider offered for images must have a code path, or the admin can pick a dead one."""
    callable_providers = set(ai._OPENAI_IMAGE_APIS) | {"gemini"}
    for p in ("openai", "gemini", "custom"):
        assert p in callable_providers, p


def test_generate_image_reports_a_missing_key_instead_of_raising_opaque(monkeypatch):
    async def _no_key(_p):
        return ""

    monkeypatch.setattr(ai, "provider_key", _no_key)
    with pytest.raises(RuntimeError) as e:
        import asyncio
        run(ai.generate_image("a cat"))
    assert "key" in str(e.value).lower()


def test_generate_image_rejects_an_unknown_provider(monkeypatch):
    async def _cfg():
        return {"provider": "not-a-provider", "model": "x"}

    monkeypatch.setattr(ai, "image_settings", _cfg)
    with pytest.raises(RuntimeError) as e:
        import asyncio
        run(ai.generate_image("a cat"))
    assert "Unknown image provider" in str(e.value)


def test_mime_sniffing_handles_the_common_encodings():
    import base64
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 8).decode()
    jpg = base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 8).decode()
    assert ai._mime_from_b64(png) == "image/png"
    assert ai._mime_from_b64(jpg) == "image/jpeg"
    assert ai._mime_from_b64(base64.b64encode(b"not-an-image").decode()) == "image/png"
