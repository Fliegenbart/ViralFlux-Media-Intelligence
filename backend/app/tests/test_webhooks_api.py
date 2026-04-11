import unittest
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_admin
from app.api.webhooks import router
from app.db.session import get_db
from app.models.database import Base, GanzimmunData


class WebhooksApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine, tables=[GanzimmunData.__table__])
        self.db = TestingSessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine, tables=[GanzimmunData.__table__])
        self.engine.dispose()

    def _build_app(self, *, admin_override: bool) -> FastAPI:
        app = FastAPI()
        app.include_router(router)

        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        if admin_override:
            app.dependency_overrides[get_current_admin] = lambda: {"role": "admin"}
        return app

    def test_integration_status_requires_admin_authentication(self) -> None:
        app = self._build_app(admin_override=False)
        client = TestClient(app)

        try:
            response = client.get("/api/webhooks/integrations/status")
            self.assertEqual(response.status_code, 401)
        finally:
            client.close()

    def test_integration_status_returns_latest_syncs_for_admins(self) -> None:
        self.db.add_all(
            [
                GanzimmunData(
                    datum=datetime(2026, 4, 10, 9, 0, 0),
                    test_typ="erp-sales",
                    extra_data={"source": "erp_sales_sync", "source_system": "sap"},
                ),
                GanzimmunData(
                    datum=datetime(2026, 4, 10, 12, 30, 0),
                    test_typ="erp-sales",
                    extra_data={"source": "erp_sales_sync", "source_system": "ims"},
                ),
                GanzimmunData(
                    datum=datetime(2026, 4, 10, 8, 15, 0),
                    test_typ="erp-sales",
                    extra_data={"source": "erp_sales_sync"},
                ),
            ]
        )
        self.db.commit()

        app = self._build_app(admin_override=True)
        client = TestClient(app)

        try:
            response = client.get("/api/webhooks/integrations/status")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(),
                {
                    "sap": {"last_sync_at": "2026-04-10T09:00:00Z"},
                    "ims": {"last_sync_at": "2026-04-10T12:30:00Z"},
                    "unknown": {"last_sync_at": "2026-04-10T08:15:00Z"},
                    "any": {"last_sync_at": "2026-04-10T12:30:00Z"},
                },
            )
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
