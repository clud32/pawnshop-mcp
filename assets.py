"""游戏主体 .assets（无类型树）里的 MonoBehaviour：按 MonoScript 识别类名，读公共头（m_Name 等）。
调用方从筛选的对象中读取游戏数值。"""
import os
import struct
from functools import lru_cache

import gamedata
import unityfs

FILES = ('resources.assets', 'sharedassets0.assets', 'sharedassets1.assets', 'level0', 'level1')


def _str(b, p):
    n = struct.unpack_from('<i', b, p)[0]; p += 4
    s = bytes(b[p:p + n]).decode('utf-8', 'replace'); p += n
    return s, (p + 3) // 4 * 4


@lru_cache(None)
def open_file(name):
    return unityfs.open_assets(os.path.join(gamedata.DATA_DIR, name))


@lru_cache(None)
def scripts():
    """globalgamemanagers.assets 里的 MonoScript：pathID -> (命名空间, 类名, 程序集)。"""
    sf = open_file('globalgamemanagers.assets')
    out = {}
    for o in sf.objects:
        if sf.class_id(o) != 115:
            continue
        b, p = sf.b, o[1]
        _name, p = _str(b, p)
        p += 4 + 16  # m_ExecutionOrder, m_PropertiesHash
        cls, p = _str(b, p)
        ns, p = _str(b, p)
        asm, p = _str(b, p)
        out[o[0]] = (ns, cls, asm)
    return out


def header(sf, o):
    """MonoBehaviour 公共头 → (类全名, 程序集, m_Name, 字段数据起点)。"""
    b, p = sf.b, o[1]
    p += 12  # m_GameObject
    p += 4   # m_Enabled + 对齐
    fid, pid = struct.unpack_from('<iq', b, p); p += 12
    name, p = _str(b, p)
    ns, cls, asm = ('', '?', '')
    if fid == 0 or (fid <= len(sf.externals) and sf.externals[fid - 1] == 'globalgamemanagers.assets'):
        ns, cls, asm = scripts().get(pid, ('', '?', ''))
    full = f'{ns}.{cls}' if ns else cls
    return full, asm, name, p


def iter_behaviours(files=FILES, classes=None):
    """逐个产出 (文件, 对象, 类全名, 程序集, m_Name, 字段起点)。classes 给集合时只要这些类。"""
    for fn in files:
        sf = open_file(fn)
        for o in sf.objects:
            if sf.class_id(o) != 114:
                continue
            full, asm, name, p = header(sf, o)
            if classes and full not in classes:
                continue
            yield fn, sf, o, full, asm, name, p
