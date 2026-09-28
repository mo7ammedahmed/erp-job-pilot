#!/usr/bin/env python3
"""
Unit tests for the sources.py module focusing on the functions that were modified.
"""

import os
import sys

# Set dummy environment variables to avoid import errors
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017/test")
os.environ.setdefault("DB_NAME", "test_db")
# Fernet keys are 32 url-safe base64-encoded bytes, not 32 raw characters, so generate a
# real one here instead of a placeholder literal that core.Fernet rejects at import time.
os.environ.setdefault("ENCRYPTION_KEY", "OaQ6YNEfoClXw2ZzB1uY8WV3P5bWos5U5igStzDPPcs=")
os.environ.setdefault("CAREERJET_AFFID", "test")
os.environ.setdefault("JOOBLE_API_KEY", "test")
os.environ.setdefault("ADZUNA_APP_ID", "test")
os.environ.setdefault("ADZUNA_APP_KEY", "test")

# Add the backend directory to the path so we can import sources
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sources


def test_normalize_city_basic():
    """Test basic city normalization functionality."""
    # Test exact matches
    assert sources.normalize_city("Riyadh") == "riyadh"
    assert sources.normalize_city("الرياض") == "riyadh"
    assert sources.normalize_city("Jeddah") == "jeddah"
    assert sources.normalize_city("جدة") == "jeddah"

    # Test case insensitivity
    assert sources.normalize_city("riyadh") == "riyadh"
    assert sources.normalize_city("RIYADH") == "riyadh"

    # Test with extra whitespace
    assert sources.normalize_city("  Riyadh  ") == "riyadh"
    assert sources.normalize_city("  الرياض  ") == "riyadh"

    # Test empty string
    assert sources.normalize_city("") == ""
    assert sources.normalize_city(None) == ""


def test_normalize_city_aliases():
    """Test that aliases are properly normalized to canonical keys."""
    # Test various aliases for the same city
    assert sources.normalize_city("al khobar") == "khobar"
    assert sources.normalize_city("الخبر") == "khobar"
    assert sources.normalize_city("Al-Khobar") == "khobar"

    assert sources.normalize_city("abu dhabi") == "abu-dhabi"
    assert sources.normalize_city("أبوظبي") == "abu-dhabi"

    assert sources.normalize_city("kuwait city") == "kuwait-city"
    assert sources.normalize_city("الكويت") == "kuwait-city"


def test_normalize_city_substring_matching():
    """Test substring matching for cities."""
    # Test that partial matches work
    assert sources.normalize_city("new york, ny") == "new-york"
    assert sources.normalize_city("London, UK") == "london"
    assert sources.normalize_city("Paris, France") == "paris"


def test_normalize_city_unknown_city():
    """Test that unknown cities are slugified."""
    # Test that unknown cities are converted to slugs
    assert sources.normalize_city("Unknown City") == "unknown-city"
    assert sources.normalize_city("Some Unknown Place") == "some-unknown-place"

    # Test with special characters
    assert sources.normalize_city("New York!!!") == "new-york"
    # Only the part before the first comma is used, so a trailing state/country code is
    # dropped rather than folded into the key -- same as "new york, ny" above.
    assert sources.normalize_city("San Francisco, CA") == "san-francisco"


def test_mk_function_includes_city_key():
    """Test that the mk function properly sets city_key."""
    job = sources.mk(
        source="test",
        source_ref="123",
        title="Test Job",
        company="Test Company",
        location="Riyadh, Saudi Arabia",
        url="http://example.com/job",
        description="Test description"
    )

    assert job["city"] == "Riyadh"
    assert job["city_key"] == "riyadh"
    assert job["country"] == "SA"
    assert job["title"] == "Test Job"
    assert job["company"] == "Test Company"
    assert job["location"] == "Riyadh, Saudi Arabia"


def test_mk_function_with_arabic_city():
    """Test that the mk function works with Arabic city names."""
    job = sources.mk(
        source="test",
        source_ref="123",
        title="Test Job",
        company="Test Company",
        location="الرياض, السعودية",
        url="http://example.com/job",
        description="Test description"
    )

    assert job["city"] == "الرياض"
    assert job["city_key"] == "riyadh"
    assert job["country"] == "SA"


def test_detect_country_function():
    """Test the country detection function."""
    # Test Saudi Arabia detection
    assert sources.detect_country("Riyadh, Saudi Arabia") == "SA"
    assert sources.detect_country("الرياض") == "SA"
    assert sources.detect_country("Jeddah") == "SA"
    assert sources.detect_country("Neom") == "SA"

    # Test UAE detection
    assert sources.detect_country("Dubai, UAE") == "AE"
    assert sources.detect_country("دبي") == "AE"
    assert sources.detect_country("Abu Dhabi") == "AE"

    # Test Egypt detection
    assert sources.detect_country("Cairo, Egypt") == "EG"
    assert sources.detect_country("القاهرة") == "EG"

    # Test unknown location
    assert sources.detect_country("Unknown City") is None
    assert sources.detect_country("") is None


if __name__ == "__main__":
    # Run the tests
    test_normalize_city_basic()
    print("✓ test_normalize_city_basic passed")

    test_normalize_city_aliases()
    print("✓ test_normalize_city_aliases passed")

    test_normalize_city_substring_matching()
    print("✓ test_normalize_city_substring_matching passed")

    test_normalize_city_unknown_city()
    print("✓ test_normalize_city_unknown_city passed")

    test_mk_function_includes_city_key()
    print("✓ test_mk_function_includes_city_key passed")

    test_mk_function_with_arabic_city()
    print("✓ test_mk_function_with_arabic_city passed")

    test_detect_country_function()
    print("✓ test_detect_country_function passed")

    print("\nAll unit tests passed! 🎉")