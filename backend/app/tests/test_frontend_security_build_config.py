from pathlib import Path


def test_frontend_production_build_disables_source_maps() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    env_file = repo_root / "frontend" / ".env.production"

    assert env_file.exists(), "frontend/.env.production is missing"
    lines = {
        line.strip()
        for line in env_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert "GENERATE_SOURCEMAP=false" in lines
