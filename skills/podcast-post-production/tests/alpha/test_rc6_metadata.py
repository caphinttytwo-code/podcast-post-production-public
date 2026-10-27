import contextlib, io, json, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from shared.project_index import build_index
from shared.package_identity import verify
from shared import setup

class RC6MetadataTests(unittest.TestCase):
    def test_index_identifies_actual_package_and_beta_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();source=root/'source.txt';source.write_text('synthetic')
            spec={'workflow':'project-audit','module_version':'synthetic-module','inputs':[{'role':'source','path':str(source)}]}
            result=build_index(spec,root)
            self.assertEqual(result['skill_version'],verify(ROOT)['version'])
            self.assertEqual(result['skill_channel'],'beta')
            self.assertFalse(result['approval_generated'])
    def test_installation_report_declares_public_beta_without_media_authorization(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            work=Path(tmp).resolve()/'inspect';code=setup.main(['inspect','--work-dir',str(work),'--features','project-audit:inventory'])
            self.assertEqual(code,0)
            result=json.loads((work/'installation-report.json').read_text())
            self.assertEqual(result['channel'],'beta')
            self.assertEqual(result['distribution'],'public-beta')
            self.assertTrue(result['public_distribution_ready'])
            self.assertEqual(result['public_distribution_blockers'], [])
            self.assertIn('Beta',(work/'installation-report.md').read_text())
            self.assertFalse(result['release_ready'])
            self.assertEqual(result['host_routing'], 'NOT RUN')
            self.assertEqual(result['human_full_review'], 'NOT RUN')

    def test_report_templates_match_the_frozen_beta_identity(self):
        identity=verify(ROOT)
        result=json.loads((ROOT/'templates/results.json').read_text())
        self.assertEqual(result['version'],identity['version'])
        self.assertEqual(result['channel'],'beta')
        self.assertEqual(result['distribution'],'public-beta')
        self.assertTrue(result['public_distribution_ready'])
        text=(ROOT/'templates/test-report.md').read_text()
        self.assertIn(identity['version'],text)
        self.assertIn('Beta',text.splitlines()[0])
