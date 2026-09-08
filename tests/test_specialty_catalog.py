import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.tenants.pbsaude.catalog import get_specialty_catalog
from app.tenants.pbsaude.specialty_aliases import DEFAULT_SPECIALTY_ALIASES


class SpecialtyCatalogTests(unittest.TestCase):
    def test_every_default_alias_resolves_to_its_canonical_value(self) -> None:
        catalog = get_specialty_catalog(Settings(_env_file=None))
        for canonical, aliases in DEFAULT_SPECIALTY_ALIASES.items():
            with self.subTest(canonical=canonical):
                self.assertEqual(canonical, catalog.resolve(canonical))
            for alias in aliases:
                with self.subTest(canonical=canonical, alias=alias):
                    self.assertEqual(canonical, catalog.resolve(alias))

    def test_default_catalog_normalizes_professional_titles_and_colloquial_terms(self) -> None:
        catalog = get_specialty_catalog(Settings(_env_file=None))
        self.assertTrue(catalog.is_enabled)
        self.assertEqual("DERMATOLOGIA", catalog.resolve("médico de pele"))
        self.assertEqual("CARDIOLOGIA", catalog.resolve("médico do coração"))
        self.assertEqual("CIRURGIA BUCOMAXILOFACIAL", catalog.resolve("cirurgião bucomaxilofacial"))

    def test_eye_consultation_aliases_do_not_resolve_ambiguous_exam(self):
        catalog = get_specialty_catalog(Settings(_env_file=None))
        for query in ('oculista', 'oculistas'):
            self.assertEqual('OFTALMOLOGIA', catalog.resolve(query))
        self.assertIsNone(catalog.resolve('exame de vista'))

    def test_default_catalog_normalizes_services_and_exams(self) -> None:
        catalog = get_specialty_catalog(Settings(_env_file=None))
        self.assertEqual("LABORATORIO", catalog.resolve("exame de sangue"))
        self.assertEqual("LABORATORIO", catalog.resolve("exames de sangue"))
        self.assertEqual("RESSONANCIA MAGNETICA", catalog.resolve("ressonância"))
        self.assertEqual("RADIOLOGIA", catalog.resolve("raio-X"))

    def test_ambiguous_terms_are_not_resolved_arbitrarily(self) -> None:
        catalog = get_specialty_catalog(Settings(_env_file=None))
        for raw_value in ("neuro", "vascular", "terapeuta", "médico da coluna"):
            with self.subTest(raw_value=raw_value):
                self.assertIsNone(catalog.resolve(raw_value))

    def test_partial_or_misspelled_alias_is_not_substituted_as_a_medical_specialty(self) -> None:
        catalog = get_specialty_catalog(Settings(_env_file=None))
        self.assertEqual("cardiolog", catalog.resolve("cardiolog"))
        self.assertEqual("cardiologai", catalog.resolve("cardiologai"))

    def test_unknown_term_is_preserved_without_external_authoritative_catalog(self) -> None:
        catalog = get_specialty_catalog(Settings(_env_file=None))
        self.assertEqual("especialidade futura", catalog.resolve("  especialidade futura  "))

    def test_missing_external_catalog_falls_back_to_default_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog = get_specialty_catalog(Settings(_env_file=None, specialties_csv_path=temp_dir))
        self.assertEqual("DERMATOLOGIA", catalog.resolve("dermatologista"))

    def test_external_csv_aliases_extend_default_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "especialidades.csv"
            path.write_text("BAQ_DESCRI,ALIASES\nMEDICINA ESPORTIVA,medico do esporte|esportiva\n", encoding="utf-8")
            catalog = get_specialty_catalog(Settings(_env_file=None, specialties_csv_path=str(path)))
        self.assertEqual("MEDICINA ESPORTIVA", catalog.resolve("médico do esporte"))
        self.assertEqual("DERMATOLOGIA", catalog.resolve("dermatologista"))
        self.assertIsNone(catalog.resolve("especialidade futura"))


if __name__ == "__main__":
    unittest.main()
