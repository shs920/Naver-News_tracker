import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "crawler"))

from relevance import filter_by_relevance


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


if __name__ == "__main__":
    unittest.main()
