from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
REMOVED_LEGACY_SURFACE_FILES = (
    REPO_ROOT / "frontend" / "src" / "features" / "media" / "usePilotSurfaceData.ts",
    REPO_ROOT / "frontend" / "src" / "components" / "cockpit" / "PilotSurface.tsx",
    REPO_ROOT / "frontend" / "src" / "pages" / "media" / "PilotPage.tsx",
    REPO_ROOT / "frontend" / "src" / "pages" / "media" / "DecisionPage.tsx",
    REPO_ROOT / "frontend" / "src" / "pages" / "media" / "OperationalDashboardPage.tsx",
    REPO_ROOT / "frontend" / "src" / "pages" / "MediaCockpit.tsx",
    REPO_ROOT / "frontend" / "src" / "pages" / "WeeklyReport.tsx",
)


class CustomerSurfaceContractTests(unittest.TestCase):
    def test_removed_legacy_customer_surfaces_stay_deleted(self) -> None:
        offenders = [str(path) for path in REMOVED_LEGACY_SURFACE_FILES if path.exists()]
        self.assertEqual(
            offenders,
            [],
            msg=f"Removed legacy customer surfaces unexpectedly exist again: {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
