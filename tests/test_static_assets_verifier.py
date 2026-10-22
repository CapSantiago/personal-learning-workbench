from pathlib import Path
import runpy

import pytest


entry_asset_path = runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/verify_static_assets_hotfix.py'))['entry_asset_path']


def test_verifier_selects_html_entry_instead_of_first_index_chunk(tmp_path):
    scripts = tmp_path/'static/js'
    scripts.mkdir(parents=True)
    (scripts/'index.AAAAAAAA.js').write_text('decoy chunk')
    (scripts/'index.BBBBBBBB.js').write_text('real entry')
    (tmp_path/'index.html').write_text('''<script src="./static/js/index.AAAAAAAA.js"></script>
        <script crossorigin type="module" src="./static/js/index.BBBBBBBB.js"></script>''')
    assert entry_asset_path(tmp_path) == '/static/js/index.BBBBBBBB.js'


@pytest.mark.parametrize('html', [
    '<script type="module" src="https://evil.example/index.AAAAAAAA.js"></script>',
    '<script type="module" src="./static/js/index.AAAAAAAA.js"></script>'*2,
])
def test_verifier_rejects_missing_or_ambiguous_module_entry(tmp_path,html):
    (tmp_path/'index.html').write_text(html)
    with pytest.raises(AssertionError):
        entry_asset_path(tmp_path)
