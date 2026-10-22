"""Small, persistent accent preference outside the learning dataset/schema."""
from pathlib import Path

from . import locking, storage

DEFAULT = 'green'
# Every preset has a readable solid-button foreground and a darker ink/focus.
PALETTES = {
    'green': dict(label='绿色', accent='#25665c', hover='#1c5149', ink='#1c5149', text='#ffffff', soft='#e5efeb', control='#7d9187'),
    'black': dict(label='黑色', accent='#34383e', hover='#22262b', ink='#25292e', text='#ffffff', soft='#eaecee', control='#7b8188'),
    'purple': dict(label='紫色', accent='#7350b5', hover='#5c3b98', ink='#57388e', text='#ffffff', soft='#efeaf7', control='#8b76ac'),
    'blue': dict(label='蓝色', accent='#2c60a5', hover='#224d88', ink='#224b80', text='#ffffff', soft='#e9eff8', control='#778eae'),
    'yellow': dict(label='黄色', accent='#e5bd3f', hover='#d5aa2b', ink='#745b12', text='#302607', soft='#fbf5df', control='#9b7b22'),
    'orange': dict(label='橙色', accent='#b65624', hover='#97451b', ink='#8e411b', text='#ffffff', soft='#f8eee7', control='#a17e67'),
}


def load_theme(root):
    path = storage.safe_path(Path(root) / 'control' / 'ui-preferences.json', directory=False)
    if not path.exists():
        return DEFAULT
    value = storage.read_json(path, max_bytes=4096)
    if not isinstance(value, dict) or set(value) != {'version', 'accent'} or type(value['version']) is not int or value['version'] != 1 or not isinstance(value['accent'],str) or value['accent'] not in PALETTES:
        raise ValueError('主题设置格式无效')
    return value['accent']


def save_theme(root, accent):
    if not isinstance(accent,str) or accent not in PALETTES:
        raise ValueError('请选择提供的主题强调色')
    root = storage.safe_path(Path(root), must_exist=True, directory=True)
    storage.safe_path(root / 'control' / 'active.json', must_exist=True, directory=False)
    with locking.workspace_lock(root):
        storage.atomic_json(root / 'control' / 'ui-preferences.json', {'version': 1, 'accent': accent})


def theme_css(accent):
    p = PALETTES[accent]
    values = dict(accent=p['accent'], **{'accent-hover': p['hover'], 'accent-ink': p['ink'],
        'accent-text': p['text'], 'accent-soft': p['soft'], 'control': p['control'], 'focus': p['ink']})
    # Fixed keys/allowlisted colors only; backgrounds, surfaces and error colors
    # remain neutral/semantic and cannot be overwritten by a saved preference.
    return ':root,:host{' + ''.join('--plw-'+name+':'+color+';' for name, color in values.items()) + '}\n'
