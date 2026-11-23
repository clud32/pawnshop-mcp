"""周报：每周一份，以交租日收尾。

一周 = 交租日 R 之前的 7 天（R−7 … R−1）。交租日当天一早出报，那 7 天的数据都已收盘。数据来源：
- runStats.creditsByDay / netWorthByDay：每天收盘的现金、净资产曲线（下标 0 = seriesStartDay）
- runStats 的累计数（销售额、进货、房租、服务费……）：本周差额 = 现在 − 上期快照
- 声望、人情、改造体存在感、库存结构、预约顾客、下期房租和贷款
- reports/journal.md 里落在本周天数范围内的条目（决策和待入库）
「短线 / 长线」两节由陪玩会话用 weekly_plan 写入。
文件：reports/weeks/<runID 前 8 位>/week_<交租日>.md；快照：同目录 day_<交租日>.json。
"""
import json
import re
from collections import Counter
from pathlib import Path

import gamedata

from local_state import STATE as ROOT
REPORTS = ROOT / 'reports'
JOURNAL = REPORTS / 'journal.md'
CUM = {'totalSales': '销售额', 'itemsSold': '售出件数', 'stockSpent': '进货支出', 'rentPaid': '已交房租',
       'vendingIncome': '售货机收入', 'fountainIncome': '饮水机收入', 'powerSpent': '电费',
       'janitorialSpent': '清洁费', 'insuranceSpent': '保险费', 'wildNetworkSpent': '王尔德服务费',
       'customersServed': '接待顾客', 'scavengedValue': '拾荒所得价值', 'inspections': '被检查次数',
       'goodsSeized': '被没收物品'}
PLAN_MARK = '## 短线与长线（陪玩会话填写）'


def _run_dir(run):
    key = run[:8]
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,8}', key):
        raise ValueError('存档中的 runID 格式无效')
    return REPORTS / 'weeks' / key


def _paths(run, rent_day):
    snap = _run_dir(run) / f'day_{rent_day:03d}.json'
    return _run_dir(run) / f'week_{rent_day:03d}.md', snap


def _state(s):
    ps, st = s.get('playerStore') or {}, s.get('storeStation') or {}
    day = st.get('dayCounter') or 0
    rs = ps.get('runStats') or {}
    reps = {r.get('factionDisplay') or r.get('factionId'): round(r.get('amount', 0), 2)
            for r in (ps.get('storeReputations') or [])}
    return {'run': ps.get('runID') or 'run', 'day': day, 'cash': ps.get('playerCash'), 'rent': ps.get('rentValue'),
            'arrears': ps.get('temporaryRent') or 0, 'dayUntilRent': ps.get('dayUntilRent'),
            'loan': ps.get('loanValue'), 'dayUntilLoan': ps.get('dayUntilLoan'), 'favor': ps.get('wildFavor'),
            'aug': ps.get('augPresence'), 'difficulty': ps.get('difficultyId'), 'reps': reps,
            'cum': {k: rs.get(k, 0) for k in CUM}, 'series': {
                'start': rs.get('seriesStartDay', 1), 'credits': rs.get('creditsByDay') or [],
                'worth': rs.get('netWorthByDay') or []},
            'queue': list(zip(ps.get('futurStoreClientIdQueue') or [], ps.get('futurStoreClientDayQueue') or []))}


def last_rent_day(state):
    """今天（含）以前最近的一个交租日。"""
    nxt = state['day'] + (state['dayUntilRent'] or 0)
    return nxt if nxt == state['day'] else nxt - 7


def _prev_snapshot(run, rent_day):
    d = _run_dir(run)
    if not d.is_dir():
        return None
    older = sorted(p for p in d.glob('day_*.json') if int(p.stem[4:]) < rent_day)
    return json.loads(older[-1].read_text(encoding='utf-8')) if older else None


def _series(state, a, b, key):
    s = state['series']
    vals = s[key]
    return [(d, vals[d - s['start']]) for d in range(a, b + 1) if 0 <= d - s['start'] < len(vals)]


def _journal(a, b, run=None):
    """本周条目。给了 run 就只取这一局的：
    条目按天数大幅回落（新开一局）切段，段内任一条带「局xxxxxxxx」就算整段属于那局；
    这样标签上线前的旧条目、以及旧版 MCP 进程写的不带标签的条目也能归对局。"""
    if not JOURNAL.exists():
        return []
    entries, seg, last = [], 0, None
    for part in JOURNAL.read_text(encoding='utf-8').split('\n### ')[1:]:
        head = part.splitlines()[0]
        m = re.search(r'第(\d+)天', head)
        if not m:
            continue
        day = int(m[1])
        if last is not None and day < last - 3:  # 允许补记前几天，回落更多视为新局
            seg += 1
        last = day
        t = re.search(r'局(\w{8})', head)
        entries.append((seg, day, t[1] if t else None, ' '.join(part.splitlines()[1:]).strip()))
    seg_run = {s: r for s, _, r, _ in entries if r}
    out = []
    for s, day, _, body in entries:
        if a <= day <= b and (not run or seg_run.get(s) == run[:8]):
            out.append(f'- 第 {day} 天：{body[:220]}' + ('…' if len(body) > 220 else ''))
    return out


def _inventory_lines(save):
    try:
        inv = gamedata.inventory(save)
    except Exception as e:
        return [f'（库存读取失败：{e}）']
    lines = []
    main = inv.get('main', [])
    cnt, val = Counter(), Counter()
    for r in main:
        for t in r.get('types') or ['(无类型)']:
            cnt[t] += 1
            val[t] += (r.get('unitValue') or 0) * (r.get('count') or 1)
    total = sum((r.get('unitValue') or 0) * (r.get('count') or 1) for rows in inv.values() for r in rows)
    lines.append(f'- 全部库存实际价值合计约 {total}（按存档 unitValue）')
    lines.append('- 主库存按价值：' + '、'.join(f'{t} {v}' for t, v in val.most_common(6)))
    lines.append('- 主库存按件数：' + '、'.join(f'{t} {c}' for t, c in cnt.most_common(6))
                 + '（买家推荐按「主库存直接摆放的物品」件数最多的类型招人；这里含储藏区里的，仅供参考）')
    show = inv.get('showcase', [])
    if show:
        lines.append('- 展柜：' + '、'.join(f'{r["name"]}({r.get("unitValue")})' for r in show))
    flagged = [r for rows in inv.values() for r in rows
               if any(k for k in (r.get('flags') or {}) if k != 'BOUGHT_PRICE_TAG')]
    if flagged:
        lines.append('- 带状态标签的货：' + '、'.join(f'{r["name"]}{list(k for k in r["flags"] if k != "BOUGHT_PRICE_TAG")}'
                                              for r in flagged[:10]))
    return lines


def build(save='auto', rent_day=None, stale=False):
    """stale=True：补出已经过去的某周（下一个交租日都过了）。存档只剩当前值，
    那周的累计数差额、声望、库存都还原不了，只出每日序列和日志。"""
    s = gamedata.load_save(save)
    st = _state(s)
    R = rent_day or last_rent_day(st)
    a, b = R - 7, R - 1
    prev = None if stale else _prev_snapshot(st['run'], R)
    L = [f'# 第 {a}–{b} 天周报（第 {R} 天交租日出报）', '',
         f'难度 {st["difficulty"]}；生成时存档为第 {st["day"]} 天。数据来自存档 runStats 和本周日志；'
         + ('这是补出的周报：存档已过了下一个交租日，只保留每日序列和日志。' if stale else
            f'{"累计数差额对比上期快照（第 " + str(prev["day"]) + " 天）" if prev else "没有上期快照，累计数为开局至今"}。'), '']
    if prev and (prev['day'] != a or st['day'] != R):
        L[-1:-1] = [f'⚠ 累计数、声望、人情的差额覆盖第 {prev["day"]} 天快照到第 {st["day"]} 天存档，'
                    f'共 {st["day"] - prev["day"]} 天，不只是本周（中间漏了周报或出报晚了）。每日收盘现金和净资产仍只算本周。']
    # 一、账面
    cr, nw = _series(st, a, b, 'credits'), _series(st, a, b, 'worth')
    L.append('## 一、本周账面')
    if cr:
        L.append('- 每日收盘现金：' + ' → '.join(f'D{d} {v}' for d, v in cr))
    if nw:
        L.append(f'- 净资产：第 {nw[0][0]} 天 {nw[0][1]} → 第 {nw[-1][0]} 天 {nw[-1][1]}（{nw[-1][1] - nw[0][1]:+}）')
    base = (prev or {}).get('cum', {})
    for k, zh in ([] if stale else CUM.items()):
        cur = st['cum'].get(k, 0) or 0
        d = cur - (base.get(k, 0) or 0)
        if d:
            L.append(f'- {zh}：{d:+}' + (f'（累计 {cur}）' if prev else ''))
    L.append(f'- 现在现金 {st["cash"]}')
    if stale:
        J = _journal(a, b, st['run'])
        L += ['', '## 五、本周决策与上报（journal，只含本局）'] + (J or ['- 本周本局 journal 没有记录'])
        L += ['', PLAN_MARK, '（补出的周报，不用再填计划）']
        return st, R, '\n'.join(L) + '\n'
    # 二、下期压力
    L += ['', '## 二、下一周要付的钱和到期事项',
          f'- 下次交租：第 {st["day"] + (st["dayUntilRent"] or 0)} 天，应付 {st["rent"]}'
          + (f' + 欠租 {st["arrears"]}' if st['arrears'] else '')
          + f'；交完后房租按难度倍率上涨（见 seed「租金怎么涨」）',
          f'- 贷款：{st["loan"]}，还剩 {st["dayUntilLoan"]} 天' if st['loan'] else '- 贷款：无']
    gap = (st['rent'] or 0) + st['arrears'] - (st['cash'] or 0)
    L.append(f'- 按现在的现金，交下期房租还差 {gap}' if gap > 0 else f'- 现金够交下期房租，余 {-gap}')
    if st['queue']:
        L.append('- 预约来访：' + '、'.join(f'{c}（{d} 天后）' for c, d in st['queue']))
    # 三、声望
    L += ['', '## 三、声望、人情、改造体']
    pr = (prev or {}).get('reps', {})
    L.append('- 声望：' + '；'.join(f'{k} {v}' + (f'（{v - pr.get(k, 0):+.2f}）' if prev else '')
                                  for k, v in st['reps'].items()))
    L.append(f'- 王尔德人情 {st["favor"]}' + (f'（{st["favor"] - (prev.get("favor") or 0):+}）' if prev else ''))
    L.append(f'- 改造体存在感 {st["aug"]}/100' + (f'（{st["aug"] - (prev.get("aug") or 0):+}）' if prev else ''))
    # 四、库存
    L += ['', '## 四、库存结构'] + _inventory_lines(save)
    # 五、决策
    J = _journal(a, b, st['run'])
    L += ['', '## 五、本周决策与上报（journal，只含本局）'] + (J or ['- 本周本局 journal 没有记录'])
    # 六、计划
    L += ['', PLAN_MARK, '（待填：【短线】下周具体怎么做；【长线】营收方向和本局目标的进度）']
    return st, R, '\n'.join(L) + '\n'


def generate(save='auto', rent_day=None, regenerate=False, stale=False):
    st, R, text = build(save, rent_day, stale)
    md, snap = _paths(st['run'], R)
    if md.exists() and not regenerate:
        return md, False
    old_plan = ''
    if md.exists():
        t = md.read_text(encoding='utf-8')
        if PLAN_MARK in t:
            old_plan = t.split(PLAN_MARK, 1)[1]
    if old_plan and '（待填' not in old_plan:
        text = text.split(PLAN_MARK)[0] + PLAN_MARK + old_plan
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(text, encoding='utf-8')
    if st['day'] >= R and not stale:  # 只在交租日当天或之后留快照，作为下周对比的基线
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps({k: st[k] for k in ('day', 'cash', 'favor', 'aug', 'reps', 'cum')},
                                   ensure_ascii=False, indent=1), encoding='utf-8')
    return md, True


def ensure(save='auto'):
    """工具调用时顺手检查：今天是交租日，或者上一个交租日的周报还没出，就生成。"""
    s = gamedata.load_save(save)
    st = _state(s)
    R = last_rent_day(st)
    if R < 1:
        return None
    # 漏掉的周（玩得快、或者出报出错）先补出来，再出本周
    made, r = [], R - 7
    while r >= 1 and not _paths(st['run'], r)[0].exists():
        r -= 7
    for old in range(r + 7, R, 7):
        made.append(generate(save, old, stale=True)[0])
    md, _ = _paths(st['run'], R)
    if not md.exists():
        made.append(generate(save, R)[0])
    return made[-1] if made else None


def save_plan(rent_day, text):
    st = _state(gamedata.load_save('auto'))
    md, _ = _paths(st['run'], int(rent_day))
    if not md.exists():
        generate('auto', int(rent_day))
    t = md.read_text(encoding='utf-8')
    head = t.split(PLAN_MARK)[0]
    md.write_text(head + PLAN_MARK + '\n' + text.strip() + '\n', encoding='utf-8')
    return md
