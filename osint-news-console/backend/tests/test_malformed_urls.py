import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import collector, crud
from app.database import Base
from app.models import NewsArticle
from app.router import router


@pytest.mark.parametrize("bad_url", ["https://[broken", "https://example.com\uff0fpath"])
def test_bad_link_does_not_roll_back_other_feed_entries(monkeypatch, bad_url):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(collector, "get_session", sessions)
    try:
        count = collector._insert_entries({"name": "Test feed"}, [
            {"title": "First", "link": "https://example.com/first"},
            {"title": "Broken", "link": bad_url},
            {"title": "Last", "link": "https://example.com/last"},
        ])
        assert count == 2
        with sessions() as session:
            assert {row.title for row in session.query(NewsArticle).all()} == {"First", "Last"}
    finally:
        engine.dispose()


@pytest.mark.parametrize("bad_url", ["https://[broken", "https://example.com\uff0fpath"])
def test_legacy_bad_link_does_not_break_news_endpoints(monkeypatch, bad_url):
    broken = NewsArticle(id="broken", title="Broken link", url=bad_url, source_name="Feed")
    valid = NewsArticle(id="valid", title="Valid link", url="https://example.com/read", source_name="Feed")
    monkeypatch.setattr(crud, "list_articles", lambda **kwargs: ([broken, valid], 2))
    monkeypatch.setattr(crud, "get_article", lambda article_id: broken)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get("/api/news")
        assert response.status_code == 200
        assert response.json()["total"] == 2
        assert response.json()["items"][0]["url"] == ""
        assert response.json()["items"][1]["url"] == valid.url
        detail = client.get("/api/news/broken")
        assert detail.status_code == 200
        assert detail.json()["title"] == broken.title
        assert detail.json()["url"] == ""
