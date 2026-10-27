"""Structural checks that also run on GitHub without private local skills."""
from pathlib import Path
import re
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]


class SkillManifestTests(unittest.TestCase):
    def test_frontmatter_and_release_consistency(self):
        text=(ROOT.parents[1]/'SKILL.md').read_text();front=yaml.safe_load(text.split('---',2)[1])
        self.assertEqual(front['name'],'podcast-post-production')
        self.assertIsInstance(front['description'],str)
        version=re.search(r'Current release: `([^`]+)`',(ROOT/'workflow.md').read_text()).group(1)
        self.assertEqual(version,'v1.7.0')
        self.assertIn(f'Skill release: `{version}`',(ROOT/'references/version-history.md').read_text())

    def test_local_reference_links_resolve(self):
        for file in [ROOT/'workflow.md',*(ROOT/'references').glob('*.md')]:
            for target in re.findall(r'\]\(([^)]+)\)',file.read_text()):
                target=target.split('#',1)[0]
                if target and not re.match(r'\w+://',target):
                    self.assertTrue((file.parent/target).exists(),f'{file.name}: {target}')

    def test_ui_metadata_retains_skill_entrypoint(self):
        value=yaml.safe_load((ROOT.parents[1]/'agents/openai.yaml').read_text())
        self.assertIn('$podcast-post-production',value['interface']['default_prompt'])


if __name__=='__main__':unittest.main()
