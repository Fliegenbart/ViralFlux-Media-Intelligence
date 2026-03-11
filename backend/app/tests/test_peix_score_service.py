import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from app.services.media.peix_score_service import PeixEpiScoreService


class PeixScoreServiceTests(unittest.TestCase):
    def test_search_signal_handles_decimal_averages(self) -> None:
        config_query = MagicMock()
        config_query.filter_by.return_value.first.return_value = None

        recent_query = MagicMock()
        recent_query.filter.return_value.scalar.return_value = Decimal("130.0")

        previous_query = MagicMock()
        previous_query.filter.return_value.scalar.return_value = Decimal("100.0")

        db = MagicMock()
        db.query.side_effect = [config_query, recent_query, previous_query]

        score = PeixEpiScoreService(db)._search_signal()

        self.assertIsInstance(score, float)
        self.assertAlmostEqual(score, 0.8)
