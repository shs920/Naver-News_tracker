import os
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "crawler"))

readability_stub = types.ModuleType("readability")


class DocumentStub:
    def __init__(self, html: str):
        self.html = html

    def summary(self, html_partial: bool = True):
        return self.html


readability_stub.Document = DocumentStub
sys.modules.setdefault("readability", readability_stub)

from article_parser import fetch_article
from config import Settings


class FakeResponse:
    def __init__(self, status_code: int, text: str, url: str = "https://example.com/news/1"):
        self.status_code = status_code
        self.text = text
        self.url = url


class FakeClient:
    def __init__(self, response: FakeResponse):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return self.response


def settings() -> Settings:
    return Settings(
        supabase_url="https://example.supabase.co",
        supabase_key="service-role",
        naver_client_id="client",
        naver_client_secret="secret",
    )


class ArticleParserDeletionTests(unittest.TestCase):
    def test_deleted_phrase_outside_valid_body_does_not_mark_article_deleted(self):
        body = (
            "빙그레는 신제품 출시와 해외 사업 확대를 통해 식품 사업 경쟁력을 높이고 있다. "
            "이번 기사 본문은 정상적인 기사 내용이며 충분한 길이를 가진다. "
            "회사는 유통 채널과 브랜드 전략을 함께 조정하고 있다고 밝혔다."
        )
        html = f"""
        <html>
          <head><title>빙그레 신제품 출시</title></head>
          <body>
            <article id="dic_area">{body}</article>
            <aside>삭제된 기사 목록을 확인하세요</aside>
          </body>
        </html>
        """
        response = FakeResponse(200, html)

        with patch("article_parser.httpx.Client", return_value=FakeClient(response)):
            parsed = fetch_article("https://example.com/news/1", "테스트언론", settings())

        self.assertFalse(parsed.is_deleted)
        self.assertEqual(parsed.parse_quality, "ok")
        self.assertIn("빙그레", parsed.content_plain)

    def test_deleted_phrase_without_valid_body_marks_article_deleted(self):
        html = "<html><body>삭제된 기사입니다. 기사를 찾을 수 없습니다.</body></html>"
        response = FakeResponse(200, html)

        with patch("article_parser.httpx.Client", return_value=FakeClient(response)):
            parsed = fetch_article("https://example.com/news/1", "테스트언론", settings())

        self.assertTrue(parsed.is_deleted)


if __name__ == "__main__":
    unittest.main()
