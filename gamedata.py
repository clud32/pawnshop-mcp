"""路径和存档读取。路径可用环境变量 PS_GAME_DIR / PS_SAVE_DIR 改。"""
import glob
import json
import os
from pathlib import Path
import es3

def _default_game():
    steam = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Steam' / 'steamapps'
    for apps in (steam, Path('D:/SteamLibrary/steamapps')):
        candidate = apps / 'common' / 'Probably Stolen'
        if candidate.is_dir():
            return candidate
    return steam / 'common' / 'Probably Stolen'


GAME_DIR = os.getenv('PS_GAME_DIR') or str(_default_game())
DATA_DIR = os.path.join(GAME_DIR, 'Probably Stolen_Data')
AA_DIR = os.path.join(DATA_DIR, 'StreamingAssets', 'aa', 'StandaloneWindows64')
SAVE_DIR = os.environ.get('PS_SAVE_DIR', os.path.expandvars(
    r'%USERPROFILE%\AppData\LocalLow\Questing Goose Studio\Probably Stolen'))


def val(x):
    """ES3 把对象包成 {"__type":..., "value":...}，取里面的值。"""
    return x['value'] if isinstance(x, dict) and '__type' in x and 'value' in x else x


def index():
    return es3.load(os.path.join(SAVE_DIR, 'saves_index.es3'))


def list_saves():
    """各存档位预览，按最后保存时间倒序。"""
    idx = index()
    out = []
    for k, v in idx.items():
        if k.startswith('preview_'):
            v = val(v)
            p = os.path.join(SAVE_DIR, f"save_{v['slotId']}.es3")
            out.append({'slot': v['slotId'], 'day': v['dayCount'], 'credit': v['credit'], 'start': v['startName'],
                        'version': v['version'], 'file': p, 'mtime': os.path.getmtime(p) if os.path.exists(p) else 0})
    return sorted(out, key=lambda s: -s['mtime'])


def load_save(slot='auto'):
    """slot='auto' 取最近保存的存档位。返回去掉 __type 包装的顶层字典。"""
    if slot == 'auto':
        saves = list_saves()
        if not saves:
            raise FileNotFoundError('没有存档')
        path = saves[0]['file']
    else:
        path = os.path.join(SAVE_DIR, f'save_{int(slot)}.es3')
    d = es3.load(path)
    return {k: val(v) for k, v in d.items()}


def game_logs():
    return sorted(glob.glob(os.path.join(SAVE_DIR, 'GameLog_*.txt')))


FLAG_WORDS = ('FAKE', 'BROKEN', 'ISSUE', 'STOLEN', 'CONTRABAND', 'COUNTERFEIT', 'DAMAGED', 'EXPIRED', 'STUCK',
              'RESTRICTED', 'ILLEGAL', 'UNUSABLE', 'BOUGHT_PRICE')


def _tag_value(t):
    for k in ('internalValueString', 'valueInt', 'valueFloat', 'valueLong', 'valueDouble'):
        v = t.get(k)
        if v not in (None, '', 0, 0.0):
            return v
    return True if t.get('valueBool') or t.get('valueEnabled') else None


KEEP_TAGS = {'backpack': '背包（装拾荒的东西用）', 'equippable': '可装备', 'IMPORTANT_TAG': '重要物品',
             'IS_OWNED_TAG': None}
KEEP_TYPES = {'TOOL': '工具', 'MACHINE': '机器', 'STORAGE': '储藏设施', 'DOCUMENT': '证件/文件'}


def keep_reason(tag_keys, types):
    """这件东西是自用的工具/设备而不是货时，返回原因（「勿卖」提示）；否则 None。"""
    why = [v for k, v in KEEP_TAGS.items() if v and k in tag_keys] + [v for k, v in KEEP_TYPES.items() if k in types]
    return '勿卖：' + '、'.join(dict.fromkeys(why)) if why else None


def inventory(save='auto', where=None, query=None):
    """各库存（mainInv、showcaseInv、hiddenInv…）里的物品：存档里的实际 unitValue（已含品相、真伪），
    以及状态类标签（假货、损坏、偷来的、违禁、买入价……）。存档把每个库存存成一段 JSON 字符串。"""
    s = load_save(save)
    ps = s.get('playerStore') or {}
    out = {}
    for key, raw in ps.items():
        if not (key.endswith('InvJSON') and isinstance(raw, str)):
            continue
        inv = key[:-len('InvJSON')]
        if where and where not in inv:
            continue
        try:
            items = json.loads(es3._quote_bare_keys(raw)).get('saveItems', [])
        except Exception as e:
            out[inv] = [{'error': f'解析失败：{e}'}]
            continue
        rows = []
        for it in items:
            ident = it.get('identifier', '')
            if ident.endswith('save_bag') or ident in ('save_bag', 'trashcan', 'dossier'):
                continue
            tags = dict(zip(it.get('_keys') or [], it.get('_values') or []))
            flags = {k: _tag_value(v) for k, v in tags.items() if any(w in k.upper() for w in FLAG_WORDS)}
            # 数值型标签值为 0 时不算状态（STOLEN_VALUE_INT=0 不是赃物；赃物看 STOLEN_TAG）
            flags = {k: v for k, v in flags.items() if not (k.endswith(('_INT', '_FLOAT')) and v is True)}
            row = {'id': ident, 'name': it.get('name'), 'count': it.get('unitCount'), 'unitValue': it.get('unitValue'),
                   'flags': flags, 'types': it.get('itemTypes')}
            keep = keep_reason(tags.keys(), it.get('itemTypes') or [])
            if keep:
                row['keep'] = keep  # 保留自用背包、工具和机器
            if query and query.lower() not in json.dumps(row, ensure_ascii=False).lower():
                continue
            rows.append(row)
        if rows:
            out[inv] = rows
    return out
