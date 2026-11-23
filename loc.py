"""本地化字符串表：Addressables 包里的 StringTable + SharedTableData → {表名: {key: {语言: 文本}}}。"""
import os
import unityfs
import gamedata

LANGS = {'zh': 'chinese(simplified)(zh)', 'en': 'english(en)'}


def _objs(path):
    for name, data in unityfs.read_bundle(path).items():
        if '.res' in name:
            continue
        sf = unityfs.SerializedFile(data)
        for o in sf.objects:
            if sf.class_id(o) != 114:
                continue
            try:
                yield sf.read(o)
            except Exception:
                continue  # 个别带 ManagedReference 的对象读不了，跳过


def load_tables():
    aa = gamedata.AA_DIR
    shared = {}  # 表名 -> {id: key}
    for v in _objs(os.path.join(aa, 'localization-assets-shared_assets_all.bundle')):
        if 'm_TableCollectionName' in v:
            shared[v['m_TableCollectionName']] = {e['m_Id']: e['m_Key'] for e in v.get('m_Entries', [])}
    out = {t: {} for t in shared}
    for lang, tag in LANGS.items():
        p = os.path.join(aa, f'localization-string-tables-{tag}_assets_all.bundle')
        for v in _objs(p):
            if 'm_TableData' not in v:
                continue
            table = v['m_Name'].rsplit('_', 1)[0]
            ids = shared.get(table, {})
            for e in v['m_TableData']:
                key = ids.get(e['m_Id'], str(e['m_Id']))
                out.setdefault(table, {}).setdefault(key, {})[lang] = e['m_Localized']
    return out
