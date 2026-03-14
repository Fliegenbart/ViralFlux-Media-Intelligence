import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, BrandProduct, WastewaterAggregated
from app.services.media.business_validation_service import BusinessValidationService
from app.services.media.v2_service import MediaV2Service


class BusinessValidationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self.media_service = MediaV2Service(self.db)
        self.validation_service = BusinessValidationService(self.db)
        self._seed_brand_products()
        self._seed_truth_reference(datetime(2026, 3, 9))

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _seed_brand_products(self) -> None:
        now = datetime.utcnow()
        self.db.add_all([
            BrandProduct(
                brand="gelo",
                product_name="GeloProsed",
                source_url="manual://seed",
                source_hash="seed-geloprosed",
                active=True,
                created_at=now,
                updated_at=now,
            ),
            BrandProduct(
                brand="gelo",
                product_name="GeloRevoice",
                source_url="manual://seed",
                source_hash="seed-gelorevoice",
                active=True,
                created_at=now,
                updated_at=now,
            ),
        ])
        self.db.commit()

    def _seed_truth_reference(self, latest_week: datetime) -> None:
        self.db.add(
            WastewaterAggregated(
                datum=latest_week,
                available_time=latest_week,
                virus_typ="Influenza A",
                n_standorte=12,
                anteil_bev=0.6,
                viruslast=1.2,
                viruslast_normalisiert=58.0,
            )
        )
        self.db.commit()

    def _import_outcomes(self, *, with_holdout: bool, with_lift: bool) -> None:
        start = datetime(2025, 8, 11)
        records = []
        for offset in range(30):
            cycle = "wave-1" if offset < 15 else "wave-2"
            extra_data = {
                "activation_cycle": cycle,
                "channel": "meta" if offset % 2 == 0 else "programmatic",
            }
            if with_holdout:
                extra_data["holdout_group"] = "test" if offset % 2 == 0 else "control"
            if with_lift:
                extra_data["incremental_lift_pct"] = 12.5 if offset >= 15 else 8.0

            records.append({
                "week_start": (start + timedelta(days=7 * offset)).isoformat(),
                "product": "GeloProsed" if offset % 2 == 0 else "GeloRevoice",
                "region_code": "SH" if offset % 3 == 0 else "HH",
                "media_spend_eur": 10000 + offset * 50,
                "sales_units": 120 + offset * 2,
                "revenue_eur": 15000 + offset * 120,
                "extra_data": extra_data,
            })

        result = self.media_service.import_outcomes(
            source_label="manual_csv",
            brand="gelo",
            records=records,
        )
        self.assertEqual(result["imported"], 30)

    def test_business_validation_requires_holdout_before_budget_activation(self) -> None:
        self._import_outcomes(with_holdout=False, with_lift=False)

        coverage = self.media_service.get_truth_coverage(brand="gelo", virus_typ="Influenza A")
        truth_gate = self.media_service.truth_gate_service.evaluate(coverage)
        outcome_learning = self.media_service.outcome_signal_service.build_learning_bundle(
            brand="gelo",
            truth_coverage=coverage,
            truth_gate=truth_gate,
        )["summary"]

        result = self.validation_service.evaluate(
            brand="gelo",
            virus_typ="Influenza A",
            truth_coverage=coverage,
            truth_gate=truth_gate,
            outcome_learning_summary=outcome_learning,
        )

        self.assertEqual(result["operator_context"]["operator"], "peix")
        self.assertEqual(result["operator_context"]["truth_partner"], "gelo")
        self.assertEqual(result["coverage_weeks"], 30)
        self.assertEqual(result["activation_cycles"], 2)
        self.assertFalse(result["holdout_ready"])
        self.assertFalse(result["validated_for_budget_activation"])
        self.assertEqual(result["validation_status"], "pending_holdout_design")
        self.assertEqual(result["decision_scope"], "decision_support_only")
        self.assertEqual(result["evidence_tier"], "truth_backed")

    def test_business_validation_passes_with_holdout_and_lift_metrics(self) -> None:
        self._import_outcomes(with_holdout=True, with_lift=True)

        coverage = self.media_service.get_truth_coverage(brand="gelo", virus_typ="Influenza A")
        truth_gate = self.media_service.truth_gate_service.evaluate(coverage)
        outcome_learning = self.media_service.outcome_signal_service.build_learning_bundle(
            brand="gelo",
            truth_coverage=coverage,
            truth_gate=truth_gate,
        )["summary"]

        result = self.validation_service.evaluate(
            brand="gelo",
            virus_typ="Influenza A",
            truth_coverage=coverage,
            truth_gate=truth_gate,
            outcome_learning_summary=outcome_learning,
        )

        self.assertTrue(result["holdout_ready"])
        self.assertTrue(result["lift_metrics_available"])
        self.assertTrue(result["validated_for_budget_activation"])
        self.assertEqual(result["validation_status"], "passed_holdout_validation")
        self.assertEqual(result["decision_scope"], "validated_budget_activation")
        self.assertEqual(result["evidence_tier"], "commercially_validated")
        self.assertTrue(result["expected_units_lift_enabled"])
        self.assertIn("business_gate", result["field_contracts"])


if __name__ == "__main__":
    unittest.main()
