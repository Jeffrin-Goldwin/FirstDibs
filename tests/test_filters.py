import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.filters import matches  # noqa: E402
from core.normalize import make_job  # noqa: E402

FILTERS = {
    "title_keywords": ["engineer", "developer"],
    "locations": ["remote", "india"],
    "exclude": ["intern", "manager"],
}


def j(title, location):
    return make_job(id="1", company="acme", title=title, location=location)


def test_match_keyword_and_location():
    assert matches(j("Backend Engineer", "Remote - India"), FILTERS) is True


def test_reject_wrong_location():
    assert matches(j("Backend Engineer", "New York"), FILTERS) is False


def test_reject_wrong_title():
    assert matches(j("Sales Lead", "Remote"), FILTERS) is False


def test_exclude_wins_over_match():
    assert matches(j("Engineering Manager", "Remote"), FILTERS) is False
    assert matches(j("Engineer Intern", "India"), FILTERS) is False


def test_empty_axis_is_unconstrained():
    assert matches(j("Anything", "Anywhere"), {}) is True
