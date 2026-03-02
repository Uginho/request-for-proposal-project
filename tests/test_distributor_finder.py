import pytest

from src.agents.distributor_finder import SEED_DISTRIBUTORS, run_distributor_finder


# ---------------------------------------------------------------------------
# SEED_DISTRIBUTORS data integrity
# ---------------------------------------------------------------------------

class TestSeedDistributors:
    def test_has_nine_distributors(self):
        assert len(SEED_DISTRIBUTORS) == 9

    def test_all_have_required_fields(self):
        required = {"name", "specialty", "address", "city", "state", "phone", "email", "website"}
        for d in SEED_DISTRIBUTORS:
            missing = required - d.keys()
            assert not missing, f"{d['name']} missing fields: {missing}"

    def test_no_empty_names(self):
        for d in SEED_DISTRIBUTORS:
            assert d["name"], "Distributor has empty name"

    def test_no_empty_emails(self):
        for d in SEED_DISTRIBUTORS:
            assert d["email"], f"{d['name']} has no email"

    def test_all_in_washington(self):
        for d in SEED_DISTRIBUTORS:
            assert d["state"] == "WA", f"{d['name']} is not in WA"

    def test_unique_names(self):
        names = [d["name"] for d in SEED_DISTRIBUTORS]
        assert len(names) == len(set(names)), "Duplicate distributor names in seed list"


# ---------------------------------------------------------------------------
# run_distributor_finder — integration with temp DB
# ---------------------------------------------------------------------------

class TestRunDistributorFinder:
    def test_persists_all_distributors(self, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")
        m.init_db()

        result = run_distributor_finder()
        assert len(result) == len(SEED_DISTRIBUTORS)

    def test_specialty_is_stored(self, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")
        m.init_db()

        result = run_distributor_finder()
        specialties = [d["specialty"] for d in result]
        assert "Broadline" in specialties
        assert "Seafood" in specialties

    def test_no_duplicates_on_rerun(self, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")
        m.init_db()

        run_distributor_finder()
        result = run_distributor_finder()

        assert len(result) == len(SEED_DISTRIBUTORS)  # not doubled

    def test_returns_correct_names(self, tmp_path):
        import src.db.models as m
        m.DB_PATH = str(tmp_path / "test.db")
        m.init_db()

        result = run_distributor_finder()
        names = [d["name"] for d in result]
        assert "Sysco Seattle" in names
        assert "Charlie's Produce" in names
        assert "Ocean Beauty Seafoods" in names
