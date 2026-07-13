import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "crawler"))

from search import _extract_article_urls_from_search_html, _looks_like_article_url


class SearchExtractionTests(unittest.TestCase):
    def test_extracts_news_tab_article_urls_from_html_and_renderer_json(self):
        html = """
        <a href="https://thetracker.co.kr/View.aspx?No=4144652">article</a>
        <script>
          window.__data = {"contentHref":"https://n.news.naver.com/mnews/article/586/0000130372?sid=101"};
        </script>
        <link rel="stylesheet" href="https://ssl.pstatic.net/sstatic/search/pc/css/search2_260709.css">
        <img src="https://cdn.coenworks.com/Files/478/News/202607/8462_20260710132624263.jpg">
        """

        urls = _extract_article_urls_from_search_html(html)

        self.assertIn("https://thetracker.co.kr/View.aspx?No=4144652", urls)
        self.assertIn("https://n.news.naver.com/mnews/article/586/0000130372?sid=101", urls)
        self.assertNotIn("https://ssl.pstatic.net/sstatic/search/pc/css/search2_260709.css", urls)

    def test_static_assets_are_not_article_urls(self):
        self.assertFalse(_looks_like_article_url("https://ssl.pstatic.net/sstatic/search/pc/css/search2_260709.css"))
        self.assertFalse(_looks_like_article_url("https://cdn.coenworks.com/Files/478/News/202607/8462.jpg"))
        self.assertTrue(_looks_like_article_url("https://thetracker.co.kr/View.aspx?No=4144652"))


if __name__ == "__main__":
    unittest.main()
