from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, Category
from backend.services import scraper


def _listing_html(projects, next_href=None):
    rows = "".join(
        f'<tr class="project-row"><td><h2><a href="{url}">{title}</a></h2></td></tr>'
        for title, url in projects
    )
    next_link = f'<a rel="next" href="{next_href}">التالي</a>' if next_href else ""
    return (
        '<html><tbody data-filter="collection">'
        f"{rows}</tbody>{next_link}</html>"
    ).encode("utf-8")


class _Response:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_scrape_category_collects_paginated_projects_and_keeps_same_minute_urls(
    monkeypatch,
):
    first_url = "https://mostaql.test/projects?category=development&sort=latest"
    second_url = "https://mostaql.test/projects?category=development&page=2"
    responses = {
        first_url: _Response(
            _listing_html(
                [
                    ("مطلوب مبرمج", "/project/100-first"),
                    ("مطلوب مبرمج", "/project/101-second"),
                ],
                "/projects?category=development&page=2",
            )
        ),
        second_url: _Response(
            _listing_html([("مطلوب مبرمج", "/project/102-third")])
        ),
    }

    monkeypatch.setattr(scraper.requests, "get", lambda url, **kwargs: responses[url])
    monkeypatch.setattr(scraper.settings, "mostaql_base_url", "https://mostaql.test")
    monkeypatch.setattr(scraper.settings, "scraper_max_pages", 3)

    jobs = scraper.scrape_category(1, first_url)

    assert [job["url"] for job in jobs] == [
        "https://mostaql.test/project/100-first",
        "https://mostaql.test/project/101-second",
        "https://mostaql.test/project/102-third",
    ]


def test_scrape_category_stops_after_an_already_known_page(monkeypatch):
    first_url = "https://mostaql.test/projects?category=development&sort=latest"
    second_url = "https://mostaql.test/projects?category=development&page=2"
    requested = []
    responses = {
        first_url: _Response(
            _listing_html(
                [
                    ("مشروع جديد", "/project/new"),
                    ("مشروع قديم", "/project/known-1"),
                ],
                "/projects?category=development&page=2",
            )
        ),
        second_url: _Response(
            _listing_html([("مشروع قديم", "/project/known-2")])
        ),
    }

    def get(url, **kwargs):
        requested.append(url)
        return responses[url]

    monkeypatch.setattr(scraper.requests, "get", get)
    monkeypatch.setattr(scraper.settings, "mostaql_base_url", "https://mostaql.test")

    jobs = scraper.scrape_category(
        1,
        first_url,
        known_urls={
            "https://mostaql.test/project/known-1",
            "https://mostaql.test/project/known-2",
        },
    )

    assert len(jobs) == 3
    assert requested == [first_url, second_url]


def test_same_title_projects_are_not_deduplicated(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(
        Category(
            id=1,
            name="برمجة",
            mostaql_url="https://mostaql.test/projects?category=development",
        )
    )
    session.commit()
    monkeypatch.setattr(scraper, "SessionLocal", Session)

    saved = scraper.save_new_jobs(
        1,
        [
            {"title": "مطلوب مبرمج", "url": "https://mostaql.test/project/200"},
            {"title": "مطلوب مبرمج", "url": "https://mostaql.test/project/201"},
        ],
    )

    assert len(saved) == 2
    assert {job.url for job in saved} == {
        "https://mostaql.test/project/200",
        "https://mostaql.test/project/201",
    }


def test_poll_category_always_scans_listing_instead_of_trusting_first_row(
    monkeypatch,
):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(
        Category(
            id=1,
            name="برمجة",
            mostaql_url="https://mostaql.test/projects?category=development",
        )
    )
    session.commit()
    monkeypatch.setattr(scraper, "SessionLocal", Session)

    expected = [object(), object()]
    monkeypatch.setattr(
        scraper,
        "scrape_category_with_logging",
        lambda category_id: expected,
    )
    monkeypatch.setattr(
        scraper,
        "quick_check_category",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("polling must not use the single-row quick check")
        ),
    )

    assert scraper.poll_category(1) is expected
