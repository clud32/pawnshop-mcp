"""深空当铺（Probably Stolen）只读 MCP 服务（stdio，纯标准库）。

读存档（ES3 明文 JSON）、游戏日志和本地化文本知识库，供 Claude 陪玩时查局面、查规则。不写任何游戏文件。
"""

import datetime
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gamedata  # noqa: E402
import local_state
import kb  # noqa: E402
import weekly  # noqa: E402

ROOT = Path(__file__).resolve().parent
JOURNAL = local_state.STATE / 'reports' / 'journal.md'
PROTOCOL = '2025-06-18'
MAX_CHARS = 60000


# ---------------- 工具实现 ----------------

def _scalars(d):
    summary = {}
    for key, value in d.items():
        if isinstance(value, str) and len(value) > 400:
            summary[key] = f'<长文本，共 {len(value)} 字符>'
        elif isinstance(value, (int, float, str, bool)):
            summary[key] = value
    return summary


def t_saves():
    return {'save_dir': gamedata.SAVE_DIR, 'saves': gamedata.list_saves(),
            'notes': '版本号以 VERSION 049 开头的是 Demo 存档；正式版存档也写在同一目录。'}


def t_overview(save='auto'):
    s = gamedata.load_save(save)
    ps, st = s.get('playerStore') or {}, s.get('storeStation') or {}
    return {'day': st.get('dayCounter'), 'store': _scalars(st), 'player': _scalars(ps),
            'nested_keys': sorted(k for k, v in ps.items() if isinstance(v, (dict, list))),
            'notes': '库存明细用 inventory，其他嵌套结构和长文本用 save_get 按路径取。'}


def t_save_get(path='', query=None, save='auto', limit=200):
    node = gamedata.load_save(save)
    for part in [p for p in path.split('.') if p]:
        node = gamedata.val(node)
        node = node[int(part)] if isinstance(node, list) else node[part]
    node = gamedata.val(node)
    if isinstance(node, dict):
        items = [(k, v) for k, v in node.items() if not query or str(query).lower() in str(k).lower()]
        return {'path': path, 'type': 'dict', 'size': len(node), 'items': {
            k: (gamedata.val(v) if not isinstance(gamedata.val(v), (dict, list))
                else f'<{type(gamedata.val(v)).__name__} {len(gamedata.val(v))}>')
            for k, v in items[:int(limit)]}}
    if isinstance(node, list):
        return {'path': path, 'type': 'list', 'size': len(node), 'items': node[:int(limit)]}
    return {'path': path, 'value': node}


def t_inventory(where=None, query=None, save='auto'):
    import itemdb
    inv = gamedata.inventory(save, where, query)
    base = {}
    for rows in inv.values():
        for r in rows:
            it = itemdb.items().get(f"item_{r['id']}")
            if it:
                v = itemdb.summarize(r['id'], it).get('value')
                if v is not None:
                    r['baseValue'] = v
    return {'inventories': inv,
            'notes': '报价以 unitValue 为准：它已经算进品相和真伪。baseValue 是代码里的基础价，只能当上限参考。'
                     'flags 里是状态类标签，比如 BOUGHT_PRICE_TAG=买入价，带 FAKE/BROKEN/ISSUE/STOLEN 的要特别留意。'}


def t_weekly_report(rent_day=None, regenerate=False, save='auto'):
    if rent_day is None and not regenerate:
        weekly.ensure(save)
    md, made = weekly.generate(save, int(rent_day) if rent_day else None, bool(regenerate))
    return {'file': str(md), 'generated_now': made, 'text': md.read_text(encoding='utf-8'),
            'notes': '读完后用 weekly_plan 写【短线】【长线】两节。'}


def t_weekly_plan(rent_day, text):
    return {'saved': str(weekly.save_plan(rent_day, text))}


def _ensure_weekly():
    try:
        weekly.ensure()
    except Exception:
        traceback.print_exc(file=sys.stderr)


def t_gamelog(query=None, last=80, file=None):
    logs = gamedata.game_logs()
    if not logs:
        return {'error': '没有 GameLog'}
    names = {Path(item).name: Path(item).resolve() for item in logs}
    if file:
        request = Path(file)
        p = request.resolve() if request.is_absolute() else names.get(str(request))
        if p not in names.values() or p.parent != Path(gamedata.SAVE_DIR).resolve():
            raise ValueError("请选择存档目录中已有的 GameLog 文件名")
    else:
        p = Path(logs[-1]).resolve()
        if p.parent != Path(gamedata.SAVE_DIR).resolve():
            raise ValueError("日志不在存档目录内")
    lines = p.read_text(encoding='utf-8', errors='replace').splitlines()
    if query:
        lines = [ln for ln in lines if str(query).lower() in ln.lower()]
    return {'file': str(p), 'all_logs': [Path(x).name for x in logs[-5:]], 'lines': lines[-int(last):]}


def t_kb_search(query, kinds=None, k=8, full=False):
    idx = kb.get_index()
    hits = idx.search(str(query), k=int(k), kinds=set(kinds) if kinds else None)
    return {'query': query, 'kb_version': kb.KB_VERSION, 'hits': [
        {'id': d['id'], 'kind': d['kind'], 'name': d['name'], 'score': round(sc, 2),
         'text': d['text'] if full else kb.snippet(d, str(query))} for sc, d in hits],
        'notes': 'kb_get 取整篇。区分攻略经验、游戏文本与代码常量；核对报价请读取当前库存的 unitValue。'}


def t_kb_get(id):
    d = next((d for d in kb.get_index().docs if d['id'] == id), None)
    return d or {'error': f'没有文档 {id}（格式如 item:item_furnace、book:book_ingot、seed:经验#1）'}


def t_kb_add_seed(title, text, file='经验'):
    """维护会话专用：追加一条人工经验到本地状态目录的 kb_seeds/<file>.md，并登记 CHANGELOG「未发布」。"""
    p = local_state.note_path(file)
    with p.open('a', encoding='utf-8') as f:
        f.write(f'\n## {title.strip()}\n{text.strip()}\n')
    _log_kb_event(f'种子 +「{title.strip()}」（{file}.md）')
    return {'appended_to': str(p), 'title': title, 'logged_in': str(local_state.STATE / 'CHANGELOG.md')}


def _log_kb_event(line):
    p = local_state.STATE / 'CHANGELOG.md'
    t = p.read_text(encoding='utf-8') if p.exists() else '# 更新记录\n\n## 未发布\n'
    head, sep, rest = t.partition('## 未发布\n')
    if not sep:
        head, sep, rest = t + '\n', '## 未发布\n', ''
    p.write_text(head + sep + f'- {datetime.date.today():%Y-%m-%d} {line}\n' + rest, encoding='utf-8')


def t_kb_rebuild():
    from collections import Counter
    idx = kb.get_index(force=True)
    return {'kb_version': kb.KB_VERSION, 'docs': len(idx.docs), 'by_kind': dict(Counter(d['kind'] for d in idx.docs))}


def t_journal(text=None, last=30):
    """决策日志。不依赖存档：读不到存档（比如一局刚结束）也能记。"""
    if text:
        try:
            sv = gamedata.load_save('auto')
            day = (sv.get('storeStation') or {}).get('dayCounter')
            run = ((sv.get('playerStore') or {}).get('runID') or '')[:8]
        except Exception:
            day, run = None, ''
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        # 标上局号：周报按局筛本周条目，免得新局混进旧局的日志
        stamp = (f'{datetime.datetime.now():%Y-%m-%d %H:%M}' + (f' 第{day}天' if day is not None else '')
                 + (f' 局{run}' if run else ''))
        with JOURNAL.open('a', encoding='utf-8') as f:
            f.write(f'\n### {stamp}\n{text.strip()}\n')
        return {'appended_to': str(JOURNAL)}
    if not JOURNAL.exists():
        return {'entries': []}
    parts = JOURNAL.read_text(encoding='utf-8').split('\n### ')
    return {'entries': ['### ' + p.strip() for p in parts[1:]][-int(last):]}


# ---------------- 工具声明 ----------------

S_SAVE = {'type': 'string', 'description': '存档位：auto（默认，最近保存的）或存档位号 0/2/3…'}
TOOLS = [
    ('overview', t_overview, '局面总览：天数、现金、租金/贷款、店铺各项标量（playerStore、storeStation 的顶层数值）。',
     {'save': S_SAVE}, []),
    ('saves', t_saves, '列出各存档位（天数、现金、开局身份、版本、最后保存时间）。', {}, []),
    ('save_get', t_save_get, '按点分路径读存档里的任意节点，如 playerStore.storeClientManager；dict 列出键和标量，'
     'query 按键名过滤。', {'path': {'type': 'string'}, 'query': {'type': 'string'}, 'save': S_SAVE,
                       'limit': {'type': 'integer'}}, []),
    ('inventory', t_inventory, '库存清单：按位置（main 主库存、showcase 展柜、hidden 暗格、back、doc…）列出物品，'
     '带存档里的实际 unitValue（已含品相、真伪）、代码基础价 baseValue、买入价和假货/损坏/违禁等状态标签。'
     '报售价、决定卖什么之前先用它。where 按库存名过滤，query 按 id 或名字过滤。',
     {'where': {'type': 'string'}, 'query': {'type': 'string'}, 'save': S_SAVE}, []),
    ('weekly_report', t_weekly_report, '周报（以交租日收尾的一周）：本周账面（每日现金、净资产、销售额、进货、房租、服务费差额）、'
     '下期房租和到期事项、声望人情改造体变化、库存结构、本周 journal 决策。不给 rent_day 时取最近一个交租日；'
     '交租日当天第一次调用任何工具会自动生成。regenerate=true 重算（保留已写的计划）。',
     {'rent_day': {'type': 'integer'}, 'regenerate': {'type': 'boolean'}, 'save': S_SAVE}, []),
    ('weekly_plan', t_weekly_plan, '把陪玩会话定的【短线】（下周具体做法）和【长线】（营收方向、本局目标进度）写进该周周报最后一节，覆盖旧计划。',
     {'rent_day': {'type': 'integer'}, 'text': {'type': 'string'}}, ['rent_day', 'text']),
    ('gamelog', t_gamelog, '游戏日志（每位顾客来访、对话、交易）。默认最新一份的最后 80 行；query 过滤关键词。',
     {'query': {'type': 'string'}, 'last': {'type': 'integer'}, 'file': {'type': 'string'}}, []),
    ('kb_search', t_kb_search, '知识库检索（先用它）：人工经验种子 + 游戏全部本地化文本（物品、手册、机制、天赋、人脉升级、'
     '对白，中英对照）。kinds 可选 seed/item/book/mech/perk/rep/network/dialog/ui/name；full=true 返回整篇。',
     {'query': {'type': 'string'}, 'kinds': {'type': 'array', 'items': {'type': 'string'}},
      'k': {'type': 'integer'}, 'full': {'type': 'boolean'}}, ['query']),
    ('kb_get', t_kb_get, '按 id 取知识库整篇，如 item:item_furnace、book:book_ingot、seed:经验#1。',
     {'id': {'type': 'string'}}, ['id']),
    ('kb_add_seed', t_kb_add_seed, '【仅维护会话】写一条人工经验种子（检索权重最高）。陪玩会话不要调，'
     '发现新规律请用 journal 记「【待入库】…」。', {'title': {'type': 'string'}, 'text': {'type': 'string'},
                                         'file': {'type': 'string'}}, ['title', 'text']),
    ('kb_rebuild', t_kb_rebuild, '【仅维护会话】强制重建知识库索引（平时按文件修改时间自动重建）。', {}, []),
    ('journal', t_journal, '决策日志：给 text 追加一条（自动标时间和天数）；不给则读最近 last 条。'
     '发现知识库没有或答错的规律，写「【待入库】…」交维护会话核实入库。',
     {'text': {'type': 'string'}, 'last': {'type': 'integer'}}, []),
]
TOOL_FUNCS = {name: fn for name, fn, *_ in TOOLS}
WRITES_OWN_FILES = {'kb_add_seed', 'kb_rebuild', 'journal', 'weekly_report', 'weekly_plan'}  # 只写 本地状态目录 自己的文件


def tool_list():
    return [{'name': n, 'description': desc, 'inputSchema': {'type': 'object', 'properties': props, 'required': req},
             'annotations': {'readOnlyHint': n not in WRITES_OWN_FILES}} for n, _, desc, props, req in TOOLS]


_LIB_MODULES = ('es3', 'unityfs', 'gamedata', 'loc', 'cil', 'itemdb', 'gamenums', 'kb', 'weekly')  # 按依赖顺序
_LIB_MTIMES = {}


def _hot_reload():
    """库模块改动后自动重载；新增工具或改 server.py 仍要重启会话。"""
    import importlib
    mt = {m: (ROOT / f'{m}.py').stat().st_mtime for m in _LIB_MODULES}
    if not _LIB_MTIMES:
        _LIB_MTIMES.update(mt)
        return
    if mt == _LIB_MTIMES:
        return
    for m in _LIB_MODULES:
        importlib.reload(sys.modules[m])
    _LIB_MTIMES.update(mt)
    print('hot-reloaded: ' + ', '.join(_LIB_MODULES), file=sys.stderr)


def call_tool(name, args):
    try:
        _hot_reload()
    except Exception:
        traceback.print_exc(file=sys.stderr)
    fn = TOOL_FUNCS.get(name)
    if not fn:
        return {'content': [{'type': 'text', 'text': f'未知工具 {name}'}], 'isError': True}
    if name not in ('weekly_report', 'weekly_plan') and not name.startswith('kb_'):
        _ensure_weekly()  # 交租日第一次读取当前局面时自动出周报
    try:
        result = fn(**(args or {}))
        text = json.dumps(result, ensure_ascii=False, indent=1)
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + f'\n…（输出超过 {MAX_CHARS} 字符被截断，用 path/query/limit 缩小范围）'
        return {'content': [{'type': 'text', 'text': text}], 'isError': 'error' in result}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'{type(e).__name__}: {e}'}], 'isError': True}


# ---------------- JSON-RPC over stdio ----------------

def handle(msg):
    method, mid = msg.get('method'), msg.get('id')
    if mid is None:
        return None
    if method == 'initialize':
        result = {'protocolVersion': PROTOCOL, 'capabilities': {'tools': {}},
                  'serverInfo': {'name': 'pawnshop', 'version': kb.KB_VERSION},
                  'instructions': '《深空当铺》陪玩工具（不改游戏文件）：查规则、物品、生产链先用 kb_search；'
                                  '局面用 overview / save_get / gamelog；新规律记 journal「【待入库】」。'}
    elif method == 'tools/list':
        result = {'tools': tool_list()}
    elif method == 'tools/call':
        p = msg.get('params') or {}
        result = call_tool(p.get('name'), p.get('arguments'))
    elif method == 'ping':
        result = {}
    else:
        return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32601, 'message': f'不支持 {method}'}}
    return {'jsonrpc': '2.0', 'id': mid, 'result': result}


def main():
    stdin = open(sys.stdin.fileno(), encoding='utf-8', errors='replace', closefd=False)
    stdout = open(sys.stdout.fileno(), 'w', encoding='utf-8', newline='\n', closefd=False)
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            reply = handle(msg)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            reply = {'jsonrpc': '2.0', 'id': msg.get('id'), 'error': {'code': -32603, 'message': 'internal error'}}
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False) + '\n')
            stdout.flush()


if __name__ == '__main__':
    if len(sys.argv) > 1:
        # 调试：python server.py overview '{"save":"auto"}'
        args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        sys.stdout.reconfigure(encoding='utf-8')
        print(call_tool(sys.argv[1], args)['content'][0]['text'])
    else:
        main()
