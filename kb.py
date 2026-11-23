"""深空当铺 自用 RAG：游戏本地化文本（中英对照）+ 人工经验种子，BM25 检索。

纯标准库：中文按单字 + 二字切分，名字加权；检索内核与苏丹的游戏 MCP 使用相同算法。
语料（docs 的 kind）：
  item:<stem>     物品：名称、描述、风味文本（Item 表按 key 去掉 _name/_desc/_flavor 等后缀归并）
  book:<topic>    游戏内手册（UI 表 book_*）：生产链、配方、机制说明
  mech:<group>    机制文本（Mechanic 表，按前两段归并）：模组、事件、结局、日志
  perk:<stem> / rep:<stem> / network:<stem>   开局天赋 / 声望天赋 / 人脉网络升级
  dialog:<conv>   对白（Dialogue、PhoneDialogue 表，按去掉末尾序号归并成一段对话）
  ui:<group>      其余界面文本；name:<group> 顾客名
  seed:<文件>#<序号>  人工经验（kb_seeds/*.md，按 ## 标题切块）
基础价、难度表和开局参数等数值由 gamenums 从本地游戏程序集和资源中读取。
语料缓存在状态目录的 kb_cache.json.gz，本地化包/种子文件变化或 KB_VERSION 升级后自动重建。
"""

import math
import os
import local_state
import re
from collections import Counter, defaultdict

import gamedata
import gamenums
import loc

KB_VERSION = '0.5.0'  # 升版本 = 强制重建索引

SUFFIX = re.compile(r'_(name|desc|flavor|short|effect|yield|prefix|pristine|title|bought|body\d*|info|intro|'
                    r'example|issues)$')
# 表名 -> (kind, 归并方式)
TABLES = {'Item': ('item', 'suffix'), 'PerkTable': ('perk', 'suffix'), 'RepPerkTable': ('rep', 'suffix'),
          'NetworkUpgrade': ('network', 'suffix'), 'Dialogue': ('dialog', 'num'), 'PhoneDialogue': ('dialog', 'num'),
          'Mechanic': ('mech', 'two'), 'UI': ('ui', 'two'), 'ClientName': ('name', 'two'),
          'Hint': ('ui', 'two'), 'Tutorial': ('ui', 'two'), 'Interactable': ('ui', 'two')}
# 经验种子最可信；手册是游戏自己的说明；对白多为闲聊，降权免得挤掉规则文本
KIND_WEIGHT = {'seed': 1.6, 'num': 1.3, 'start': 1.3, 'table': 1.1, 'book': 1.2, 'dialog': 0.8}


def _stem(key, how):
    if how == 'suffix':
        return SUFFIX.sub('', key)
    if how == 'num':
        return re.sub(r'_?\d+$', '', key)
    return '_'.join(key.split('_')[:2])


def _line(key, tr):
    zh, en = tr.get('zh', ''), tr.get('en', '')
    zh, filled = gamenums.fill_text(key, zh)  # {0}{1} 代成代码里传入的实际数值
    en, _ = gamenums.fill_text(key, en)
    return f'{key}：{zh}' + (f'（{en}）' if en and en != zh else '') + ('〔数值已按代码代入〕' if filled else '')


def build_docs():
    docs = []
    for table, entries in loc.load_tables().items():
        kind, how = TABLES.get(table, ('ui', 'two'))
        groups = defaultdict(list)
        for key, tr in entries.items():
            k = kind
            if table == 'UI' and key.startswith('book_'):
                k = 'book'
            groups[(k, _stem(key, how))].append((key, tr))
        for (k, stem), rows in groups.items():
            name_row = next((tr for key, tr in rows if key.endswith(('_name', '_title'))), rows[0][1])
            name = name_row.get('zh') or name_row.get('en') or stem
            label = {'item': '物品', 'book': '手册', 'mech': '机制', 'perk': '开局天赋', 'rep': '声望天赋',
                     'network': '人脉升级', 'dialog': '对白', 'ui': '界面', 'name': '顾客名', 'num': '数值'}.get(k, k)
            head = f'{label}「{name}」（{k}:{stem}，表 {table}）'
            extra = (gamenums.item_lines(stem) + gamenums.const_lines(stem) + gamenums.ref_lines(stem) if k == 'item'
                     else gamenums.network_lines(stem) if k == 'network'
                     else gamenums.perk_lines(stem) if k == 'perk' else [])
            text = '\n'.join([head] + extra + [_line(key, tr) for key, tr in rows])
            docs.append({'id': f'{k}:{stem}', 'kind': k, 'name': name[:40], 'text': text, 'flags': []})
    for sid in gamenums.scenarios():
        text = gamenums.scenario_doc(sid)
        docs.append({'id': f'start:{sid}', 'kind': 'start', 'name': text.split('「')[1].split('」')[0] + ' 开局身份',
                     'text': text, 'flags': []})
    for tid, tname, ttext in gamenums.table_docs():
        docs.append({'id': tid, 'kind': 'table', 'name': tname, 'text': ttext, 'flags': []})
    docs.append({'id': 'num:difficulty', 'kind': 'num', 'name': '难度参数 买断价 租金涨幅 按揭',
                 'text': gamenums.difficulty_doc(), 'flags': []})
    docs.extend(seed_docs())
    return docs


def seed_docs():
    out = []
    for p, stem in local_state.seed_files():
        chunks = re.split(r'\n(?=## )', p.read_text(encoding='utf-8'))
        for i, ch in enumerate(chunks):
            ch = ch.strip()
            if not ch or not ch.startswith('## '):
                continue
            title = ch.splitlines()[0][3:].strip()
            out.append({'id': f'seed:{stem}#{i}', 'kind': 'seed', 'name': title, 'text': ch, 'flags': []})
    return out


# ---------------- BM25（与 sultan-mcp 相同） ----------------

def tokens(s):
    s = s.lower()
    out = re.findall(r'[a-z]+|\d+', s)
    for run in re.findall(r'[一-鿿]+', s):
        out.extend(run)                                        # 单字
        out.extend(run[i:i + 2] for i in range(len(run) - 1))  # 二字
    return out


class Index:
    def __init__(self, docs):
        self.docs = docs
        self.tf, lens, df = [], [], Counter()
        for d in docs:
            t = Counter(tokens((d['name'] + '\n') * 3 + d['text']))  # 名字重复 3 次加权
            self.tf.append(t)
            lens.append(sum(t.values()))
            df.update(t.keys())
        self.n = len(docs)
        self.avg = sum(lens) / max(1, self.n)
        self.lens = lens
        self.idf = {w: math.log(1 + (self.n - c + 0.5) / (c + 0.5)) for w, c in df.items()}

    def search(self, query, k=8, kinds=None, k1=1.4, b=0.75):
        q = Counter(tokens(query))
        scores = []
        for i, d in enumerate(self.docs):
            if kinds and d['kind'] not in kinds:
                continue
            tf, sc = self.tf[i], 0.0
            for w in q:
                f = tf.get(w)
                if f:
                    sc += self.idf.get(w, 0) * f * (k1 + 1) / (f + k1 * (1 - b + b * self.lens[i] / self.avg))
            if sc:
                sc *= KIND_WEIGHT.get(d['kind'], 1.0)
                if d['name'] and d['name'] in query:
                    sc *= 1.5
                scores.append((sc, i))
        scores.sort(reverse=True)
        return [(s, self.docs[i]) for s, i in scores[:k]]


def snippet(doc, query, width=3):
    q = set(tokens(query))
    lines = doc['text'].splitlines()
    ranked = sorted(range(len(lines)), key=lambda i: -len(q & set(tokens(lines[i]))))
    pinned = [i for i, ln in enumerate(lines[:3]) if ln.startswith(('基础价值', '费用', '天赋点', '数值', '开局现金'))]  # 数值行总是带上
    keep = sorted(set([0] + pinned + ranked[:width]))
    return '\n'.join(lines[i][:260] for i in keep)


def _signature():
    sig = [('aa', p, os.path.getmtime(os.path.join(gamedata.AA_DIR, p)))
           for p in sorted(os.listdir(gamedata.AA_DIR)) if p.startswith('localization')]
    sig.append(('root', os.path.abspath(gamedata.GAME_DIR)))
    sig.append(('dll', os.path.getmtime(gamenums.itemdb.DLL)))  # 数值来自程序集，游戏更新就重建
    sig.extend(('seed', stem, p.stat().st_mtime_ns) for p, stem in local_state.seed_files())
    return (KB_VERSION, tuple(sig))


_INDEX = {'sig': None, 'idx': None}


def get_index(force=False):
    sig = _signature()
    if not force and _INDEX['sig'] == sig:
        return _INDEX['idx']
    docs = None if force else local_state.read_docs(sig)
    if docs is None:
        docs = build_docs()
        local_state.write_docs(sig, docs)
    idx = Index(docs)
    _INDEX.update(sig=sig, idx=idx)
    return idx
