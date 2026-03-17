from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CUSTOMER_SURFACE_FILES = (
    REPO_ROOT / "backend" / "app" / "api" / "media.py",
    REPO_ROOT / "backend" / "app" / "services" / "media" / "pilot_readout_service.py",
    REPO_ROOT / "frontend" / "src" / "types" / "media" / "pilotReadout.ts",
    REPO_ROOT / "frontend" / "src" / "features" / "media" / "usePilotSurfaceData.ts",
    REPO_ROOT / "frontend" / "src" / "components" / "cockpit" / "PilotSurface.tsx",
    REPO_ROOT / "frontend" / "src" / "pages" / "media" / "PilotPage.tsx",
)


class CustomerSurfaceContractTests(unittest.TestCase):
    def test_customer_facing_pilot_surface_does_not_expose_impact_probability(self) -> None:
        offenders: list[str] = []
        for path in CUSTOMER_SURFACE_FILES:
            content = path.read_text()
            if "impact_probability" in content:
                offenders.append(str(path))
        self.assertEqual(
            offenders,
            [],
            msg=f"Forbidden legacy probability alias found in customer-facing surface files: {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
