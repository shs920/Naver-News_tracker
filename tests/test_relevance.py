import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "crawler"))

from relevance import filter_by_relevance, select_primary_keyword


class RelevanceTests(unittest.TestCase):
    def test_ambiguous_food_companies_require_company_context(self):
        self.assertFalse(filter_by_relevance("오뚜기", "실패해도 다시 일어서는 오뚜기 정신", "청년 창업가의 도전기"))
        self.assertFalse(filter_by_relevance("농심", "농심 레드포스, LCK 경기 승리", "프로게임단이 시즌 첫 승을 거뒀다"))
        self.assertFalse(filter_by_relevance("하림", "가수 하림, 새 공연 개최", "싱어송라이터 하림이 무대에 오른다"))
        self.assertFalse(filter_by_relevance("대상", "지원 대상 확대", "정부가 청년 지원 대상자를 늘렸다"))

    def test_ambiguous_food_companies_pass_with_food_company_context(self):
        self.assertTrue(filter_by_relevance("오뚜기", "오뚜기 라면 가격 인상", "식품업계가 원가 부담을 겪고 있다"))
        self.assertTrue(filter_by_relevance("농심", "농심, 라면 수출 호조", "농심의 해외 매출과 식품 사업이 성장했다"))
        self.assertTrue(filter_by_relevance("하림", "하림 닭고기 제품 출시", "하림의 식품 브랜드가 신제품을 내놨다"))
        self.assertTrue(filter_by_relevance("대상", "대상 종가 김치 수출 확대", "대상그룹 식품 사업이 해외 시장을 공략한다"))


class PrimaryKeywordTests(unittest.TestCase):
    def test_primary_keyword_uses_strongest_company_focus(self):
        binggrae = "\ube59\uadf8\ub808"
        haitai = "\ud574\ud0dc"
        seoul_milk = "\uc11c\uc6b8\uc6b0\uc720"

        title = "\ube59\uadf8\ub808 3\uc138 \uacbd\uc601\uad8c \uc2b9\uacc4 \ubcf8\uaca9\ud654"
        body = (
            "\ube59\uadf8\ub808\ub294 \ud574\ud0dc\uc544\uc774\uc2a4\ud06c\ub9bc \ud569\ubcd1 \ud6c4 "
            "\uc544\uc774\uc2a4\ud06c\ub9bc \uc0ac\uc5c5\uacfc \uc720\ud1b5 \uc804\ub7b5\uc744 \uc870\uc815\ud588\ub2e4. "
            "\uc11c\uc6b8\uc6b0\uc720 \ub4f1 \uacbd\uc7c1\uc0ac\ub3c4 \uae30\uc0ac\uc5d0 \uc5b8\uae09\ub410\ub2e4."
        )

        self.assertEqual(
            select_primary_keyword([haitai, seoul_milk, binggrae], haitai, title, body),
            binggrae,
        )

    def test_primary_keyword_breaks_close_tie_with_search_keyword(self):
        bbq = "BBQ"
        bhc = "BHC"
        title = "BBQ\u00b7BHC \uce58\ud0a8 \ud504\ub79c\ucc28\uc774\uc988 \uacbd\uc7c1 \uc2ec\ud654"
        body = "BBQ\uc640 BHC\uac00 \ub3d9\uc2dc\uc5d0 \uc2e0\uba54\ub274\ub97c \ucd9c\uc2dc\ud588\ub2e4."

        self.assertEqual(
            select_primary_keyword([bbq, bhc], bbq, title, body),
            bbq,
        )


if __name__ == "__main__":
    unittest.main()
