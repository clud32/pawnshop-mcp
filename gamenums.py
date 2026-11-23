"""从 Assembly-CSharp 读出的数值，转写成知识库用的中文行。
- 物品基础价值、类型、标签、厂商、用途（itemdb）
- 难度参数（Difficulty::Vanilla 里四个 DifficultyRules）
- 人脉升级费用（NetworkUpgrade 的 Create* 方法里给 cost 赋的常量）
全部是游戏代码里的常量：基础价值不等于成交价，成交价还受加价、品相、市场事件、讨价还价影响。"""
from functools import lru_cache

import cil
import itemdb

DIFF_FIELDS = {
    'propertyBasePrice': '店铺买断基价', 'propertyPriceIncreasePerDay': '买断价每天上涨',
    'propertyPriceIncreaseCap': '买断价上涨封顶', 'rentIncreaseMultiplier': '租金每期涨幅倍率',
    'landlordGraceOwnedAtStart': '开局自带房东宽限', 'mortgageInterestRate': '按揭利息%',
    'mortgageWeeks': '按揭周数', 'mortgageDownPaymentShare': '按揭首付比例', 'retailMarkup': '零售加价%',
    'vendorPermitFee': '摊贩许可证费', 'newCustomerDiscount': '新顾客折扣%', 'upgradePriceMultiplier': '升级价格倍率',
    'supplierMarkupMultiplier': '供货商加价倍率', 'inventorMarkup': '发明家加价%', 'retiredSupplierMarkup': '退休供货商加价%',
    'merchantDiscount': '商人折扣%', 'scalperMarkupBase': '黄牛基础加价%', 'scalperMarkupPerDay': '黄牛每天加价%',
    'powerCostMultiplier': '电费倍率', 'insuranceCostMultiplier': '保险费倍率', 'startPowerCostBonus': '开局电费加成',
    'startJanitorialCostBonus': '开局清洁费加成', 'startInsuranceCostBonus': '开局保险费加成',
    'appraisalJoinCostMultiplier': '鉴定协会入会费倍率', 'reputationGainMultiplier': '声望获取倍率',
    'reputationLossMultiplier': '声望损失倍率', 'appraisalProgressGainMultiplier': '鉴定进度获取倍率',
    'appraisalProgressLossMultiplier': '鉴定进度损失倍率', 'tradeFavorRate': '交易换人情比例',
    'wildServiceFavorRefund': '王尔德服务人情返还', 'networkIntroFavor': '人脉引荐人情',
    'augKillPresenceDrop': '击杀改造人存在感下降', 'augLeftAlivePresenceRise': '放走改造人存在感上升',
    'augWarning': '改造人预警', 'augGameOverAtFullPresence': '存在感满即游戏结束', 'wildBailout': '王尔德兜底救济',
    'wildReminders': '王尔德提醒', 'displayCaseTip': '展柜提示', 'eventEndCountdown': '事件结束倒计时'}


def _fmt(v):
    return round(v, 3) if isinstance(v, float) else v


@lru_cache(None)
def difficulties():
    """[(难度 id, 英文名, 档位, {字段: 值})]，顺序同游戏菜单。"""
    A = itemdb.assembly()
    mi = next(m for m in range(1, A.rows[0x06] + 1) if A.method_name(m) == 'Difficulty::Vanilla')
    il = A.il(mi)
    rules, cur, last = [], None, None
    for ins in il:
        _at, n, a = ins
        c = cil.const_int(ins)
        if n == 'newobj' and a[1] == 'DifficultyRules::.ctor':
            cur = {}; rules.append(cur)
        elif c is not None:
            last = c
        elif n == 'stfld' and cur is not None and a[1].startswith('DifficultyRules::'):
            cur[a[1].split('::')[-1]] = _fmt(last)
    names, strs = [], []
    for _at, n, a in il:
        if n == 'ldstr':
            strs.append(a[1])
    for i, s in enumerate(strs):
        if s in ('cozy', 'normal', 'hard', 'challenge'):
            names.append((s, strs[i + 2] if i + 2 < len(strs) else s))
    return [(nid, en, rules[i] if i < len(rules) else {}) for i, (nid, en) in enumerate(names)]


@lru_cache(None)
def network_upgrades():
    """{升级 ID: {cost, subtitle, prereq[], 其他常量字段}}，来自 NetworkUpgradeList 的 Create* 方法。
    本地化 key 是 network_<ID>_title / _desc。"""
    A = itemdb.assembly()
    out = {}
    for mi in range(1, A.rows[0x06] + 1):
        if not A.row(0x06, mi)[0]:
            continue
        il = A.il(mi)
        if not any(n == 'newobj' and a[1] == 'NetworkUpgrade::.ctor' for _, n, a in il):
            continue
        cur, last, in_prereq = None, None, False
        for ins in il:
            _at, n, a = ins
            c = cil.const_int(ins)
            if n == 'ldstr':
                if in_prereq and cur is not None:
                    cur['prereq'].append(a[1]); in_prereq = False
                last = a[1]
            elif n == 'newobj' and a[1] == 'NetworkUpgrade::.ctor':
                cur = out.setdefault(str(last), {'prereq': []}) if isinstance(last, str) else None
            elif c is not None:
                last = c
            elif n == 'ldfld' and a[1] == 'NetworkUpgrade::prerequisite':
                in_prereq = True
            elif n == 'stfld' and cur is not None and a[1].startswith('NetworkUpgrade::'):
                cur[a[1].split('::')[-1]] = _fmt(last)
    return out


def _named(call):
    """'Cls::M(a, b)' → 'Cls::M(参数名=a, 参数名=b)'，参数名取自程序集的 Param 表；物品本身那个参数省掉。"""
    import re
    m = re.match(r'(.+?)\((.*)\)$', call)
    if not m:
        return call
    A = itemdb.assembly()
    mi = A.method_index().get(m[1])
    if not mi:
        return call
    names = A.param_names(mi)
    args = [a.strip() for a in re.split(r", (?=(?:[^']*'[^']*')*[^']*$)", m[2])] if m[2] else []
    if A.sig(0x06000000 | mi)[0] and len(names) == len(args) - 1:
        names = ['this'] + names
    parts = [a if i >= len(names) else f'{names[i]}={a}' for i, a in enumerate(args) if a != "'<item>'"]
    return f'{m[1].split("::")[-1]}({", ".join(parts)})'


def item_lines(stem):
    it = itemdb.items().get(stem)
    if not it:
        return []
    s = itemdb.summarize(stem, it)
    out = []
    if 'value' in s:
        out.append(f'基础价值（价格）：{s["value"]}（代码常量；成交价另受加价、品相、市场和讨价还价影响）')
    if s['types']:
        out.append('类型：' + '、'.join(s['types']))
    tags = [t if isinstance(t, str) else t[0] for t in s['tags']]
    if tags:
        out.append('标签：' + '、'.join(dict.fromkeys(str(t) for t in tags)))
    if s.get('maker'):
        out.append(f'厂商：{s["maker"]}')
    tagset = {str(t) for t in tags}
    if 'TOOL' in s['types'] or tagset & {'backpack', 'equippable', 'IMPORTANT_TAG'}:
        out.append('⚠ 自用的工具/背包/重要物品，别当货卖（如儿童背包和挎包，可留给拾荒使用）')
    other = [_named(o) for o in s['other'] if not o.startswith(('GameItem::SetContentWindow', 'MachineHelper::Setup'))]
    if other:
        out.append('其他设定：' + '；'.join(other[:12]))
    out.append('定义处：' + '、'.join(s['where']))
    return out


def difficulty_doc():
    rows = difficulties()
    lines = ['难度参数对照（Difficulty::Vanilla 代码常量）。存档 playerStore.difficultyId 是当前难度。',
             '买断价公式（PlayerStore::GetStoreBuyPrice）：第 50 天及以前 = 买断基价；之后 = 基价 + min((天数−50)×每天上涨, 封顶)。'
             '例：hard 第 107 天 = 24000 + min(57×50, 10000) = 26850。走按揭时先付首付（GetMortgageDownPayment）。']
    lines.append('字段 | ' + ' | '.join(f'{nid}（{en}）' for nid, en, _ in rows))
    for f, zh in DIFF_FIELDS.items():
        lines.append(f'{zh}（{f}） | ' + ' | '.join(str(r.get(f, '')) for _, _, r in rows))
    return '\n'.join(lines)


def network_lines(stem):
    """stem 形如 network_BREWER → 该人脉升级的费用和前置。"""
    up = network_upgrades().get(stem[len('network_'):])
    if not up:
        return []
    out = [f'费用：{up["cost"]}（单位应是王尔德人情 wildFavor，未核实）'] if 'cost' in up else []
    if up.get('prereq'):
        out.append('前置升级：' + '、'.join(up['prereq']))
    flags = {'isRepeatable': '可重复购买', 'lockInDemo': 'Demo 里锁定', 'recommended': '推荐',
             'heldUntilUsed': '买了先存着、用时生效'}
    out += [v for k, v in flags.items() if up.get(k) == 1]
    if up.get('cooldownDuration'):
        out.append(f'冷却：{up["cooldownDuration"]} 天')
    if up.get('subtitle'):
        out.append(f'分类：{up["subtitle"]}')
    return out


def _camel(s):
    return ''.join(p.capitalize() for p in s.split('_'))


@lru_cache(None)
def starting_perks():
    """开局天赋：{id: {cost, type, maxSlot, incompatible[], args[]}}。
    定义在 StartingPerkList 的同名方法里；描述里 {0}{1} 的数值在 StartingPerk::.cctor 的 Args* 静态数组里。"""
    A = itemdb.assembly()
    args, cur = {}, []
    cctor = next(m for m in range(1, A.rows[0x06] + 1) if A.method_name(m) == 'StartingPerk::.cctor')
    for ins in A.il(cctor):
        _at, n, a = ins
        c = cil.const_int(ins)
        if n == 'newarr':
            cur = []
            pending = None
        elif c is not None:
            pending = c
        elif n == 'box' and pending is not None:
            cur.append(_fmt(pending)); pending = None
        elif n == 'ldstr':
            pending = a[1]
        elif n == 'stsfld' and a[1].startswith('StartingPerk::Args'):
            args[a[1].split('::Args')[-1]] = cur
    out = {}
    for mi in range(1, A.rows[0x06] + 1):
        nm = A.method_name(mi)
        if not nm.startswith('StartingPerkList::') or not A.row(0x06, mi)[0]:
            continue
        p, last, in_incompat = None, None, False
        for ins in A.il(mi):
            _at, n, a = ins
            c = cil.const_int(ins)
            if c is not None:
                last = c
            elif n == 'ldstr':
                if in_incompat and p is not None:
                    p['incompatible'].append(a[1])
                last = a[1]
            elif n == 'newobj' and a[1].startswith('TypeSpec'):
                in_incompat = True
            elif n == 'stfld' and a[1] == 'StartingPerk::id':
                p = out.setdefault(last, {'incompatible': []}); in_incompat = False
            elif n == 'stfld' and p is not None and a[1].split('::')[-1] in ('cost', 'type', 'maxSlot', 'mindEditable'):
                p[a[1].split('::')[-1]] = last
            elif n == 'stfld' and a[1] == 'StartingPerk::incompatiblePerks':
                in_incompat = False
    for pid, p in out.items():
        p['args'] = args.get(_camel(pid), [])
        p.setdefault('cost', 0)
    return out


def _fill(text, args):
    for i, v in enumerate(args):
        text = text.replace('{%d}' % i, str(v))
    return text


def perk_lines(stem):
    """stem 形如 perk_convict → 该开局天赋的点数、互斥、描述数值。"""
    import loc
    pid = stem[len('perk_'):]
    p = starting_perks().get(pid)
    if not p:
        return []
    cost = p['cost']
    out = [f'天赋点：{cost}（' + ('消耗点数' if cost > 0 else '返还点数，属于负面天赋' if cost < 0 else '不占点数') + '）']
    if p['args']:
        desc = loc.load_tables().get('PerkTable', {}).get(f'perk_{pid}_desc', {}).get('zh', '')
        out.append('数值：' + ' / '.join(map(str, p['args'])) + (f'；描述代入后：{_fill(desc, p["args"])}' if desc else ''))
    if p['incompatible']:
        out.append('互斥：' + '、'.join(p['incompatible']))
    if p.get('maxSlot'):
        out.append(f'最多可叠 {p["maxSlot"]} 次')
    return out


START_CASH, START_RENT = 600, 200  # PlayerStore::StartNewGame：开局现金、基础房租（PlayerStore::.ctor）


@lru_cache(None)
def scenarios():
    """开局身份：{id: {type, cash, rent, rep{}, items[], gear_keys[]}}。
    StartingScenario::Vanilla 给 id→startType；NewGameData::HandleInitialItem 里按 startType 分段：
    现金 600 减装备钱、基础房租 200 加价、声望改动、初始物品。"""
    A = itemdb.assembly()
    il = A.il(next(m for m in range(1, A.rows[0x06] + 1) if A.method_name(m) == 'StartingScenario::Vanilla'))
    out, by_type = {}, {}
    for i, (_at, n, a) in enumerate(il):
        if n == 'ldstr' and i + 2 < len(il) and cil.const_int(il[i + 1]) is not None and il[i + 2][1] == 'ldstr':
            sid, st = a[1], cil.const_int(il[i + 1])
            gear = []
            for _a2, n2, a2 in il[i + 3:i + 60]:
                if n2 == 'call' and a2[1] == 'StartingScenario::Create':
                    break
                if n2 == 'ldstr' and '_gear' in a2[1]:
                    gear.append(a2[1])
            out[sid] = {'type': st, 'cash': START_CASH, 'rent': START_RENT, 'rep': {}, 'items': [], 'gear_keys': gear,
                        'name_key': il[i + 2][2][1]}
            by_type[st] = sid
    il = A.il(next(m for m in range(1, A.rows[0x06] + 1) if A.method_name(m) == 'NewGameData::HandleInitialItem'))
    cur = None
    for i, ins in enumerate(il):
        _at, n, a = ins
        if n == 'ldfld' and a[1] == 'NewGameData::startType' and i + 1 < len(il):
            cur = out.get(by_type.get(cil.const_int(il[i + 1])))
            continue
        if cur is None:
            continue
        prev = [cil.const_int(x) for x in il[max(0, i - 2):i]]
        if n == 'stfld' and a[1] == 'PlayerStore::playerCash':
            op, c = il[i - 1][1], cil.const_int(il[i - 2])
            if op == 'op#59' and c is not None:
                cur['cash'] -= c
            elif op == 'op#58' and c is not None:
                cur['cash'] += c
            elif cil.const_int(il[i - 1]) is not None:
                cur['cash'] = cil.const_int(il[i - 1])
        elif n == 'stfld' and a[1] == 'PlayerStore::startingRent' and il[i - 1][1] == 'op#58':
            cur['rent'] += cil.const_int(il[i - 2]) or 0
        elif n == 'call' and a[1].startswith('StoreReputation::Mod') and prev[-1] is not None:
            k = a[1].split('::Mod')[-1].replace('Reputation', '')
            cur['rep'][k] = cur['rep'].get(k, 0) + prev[-1]
        elif n == 'call' and a[1] == 'DirectoryMaster::Item' and il[i - 2][1] == 'ldstr':
            cur['items'].append(il[i - 2][2][1])
    return out


REP_NAMES = {'Sec': '治安部', 'BM': '黑市', 'Rev': '革命军', 'Corp': '企业', 'Scav': '拾荒者'}


def scenario_doc(sid):
    import loc
    s = scenarios()[sid]
    T = loc.load_tables().get('NewGame', {})
    zh = lambda k: (T.get(k) or {}).get('zh', k)  # noqa: E731
    lines = [f'开局身份「{zh(s["name_key"])}」（start:{sid}，startType {s["type"]}）',
             f'开局现金：{s["cash"]}（通用 {START_CASH} 减去这个身份的装备钱）；基础房租：{s["rent"]}（通用 {START_RENT} 加价）',
             '（房租和声望还会叠加开局天赋和难度倍率，算法见种子「开局数值怎么算」）']
    if s['rep']:
        lines.append('初始声望改动：' + '、'.join(f'{REP_NAMES.get(k, k)} {v:+}' for k, v in s['rep'].items()))
    lines.append('背景：' + zh(f'{sid}_body' if f'{sid}_body' in T else s['name_key'] + '_body'))
    gear = [zh(k) for k in s['gear_keys']]
    if gear:
        lines.append('开局装备（菜单文字）：' + '；'.join(gear))
    if s['items']:
        lines.append('初始物品 id：' + '、'.join(dict.fromkeys(s['items'])))
    return '\n'.join(lines)


@lru_cache(None)
def object_tables():
    """扫描全部方法里的「对象字面量」：newobj C::.ctor 之后一串 dup; 常量; stfld C::字段。
    返回 {类名: [{字段: 值, '_at': 方法}]}，只收至少有 2 个常量字段的记录。"""
    A = itemdb.assembly()
    out = {}
    for mi in range(1, A.rows[0x06] + 1):
        if not A.row(0x06, mi)[0]:
            continue
        try:
            il = A.il(mi)
        except Exception:
            continue
        cur, cls, last = None, None, None
        for ins in il:
            _at, n, a = ins
            c = cil.const_int(ins)
            if n == 'newobj' and a[1].endswith('::.ctor') and not a[1].startswith(('TypeSpec', 'System.')):
                if cur and len(cur) > 1:
                    out.setdefault(cls, []).append(cur)
                cls, cur, last = a[1][:-7], {'_at': A.method_name(mi)}, None
            elif c is not None:
                last = _fmt(c)
            elif n == 'ldstr':
                last = a[1]
            elif n == 'ldnull':
                last = None
            elif n == 'stfld' and cur is not None and a[1].startswith(cls + '::') and last is not None:
                cur[a[1].split('::')[-1]] = last; last = None
        if cur and len(cur) > 1:
            out.setdefault(cls, []).append(cur)
    return out


TABLES = {  # 类名 -> (中文名, 用作名字的字段)
    'StoreEvent': ('市场/空间站事件', 'displayName'), 'StoreReputationPerk': ('声望天赋解锁门槛', 'perkId'),
    'Liquid': ('液体（水的种类与纯度）', 'displayName'), 'StoreRequest': ('委托请求', 'id'),
    'GunOrderData': ('枪械订单', 'dialogText'), 'StoreService': ('店铺服务（每日费用）', 'displayName'),
    'StationFeature': ('空间站特性', 'displayName'), 'FactionStatus': ('派系状态', 'displayName'),
    'ModuleEffect': ('模组特殊效果', 'displayName'), 'AfterhourEventDefinition': ('夜间事件（每日概率）', 'id'),
    'CommissaryItemData': ('军需处商品', 'identifier'), 'ChemFinisherRecipe': ('化学精制配方', 'displayName'),
    'ExchangeBarter': ('交易所以物易物', 'identifier'), 'ItemCondition': ('物品状态/品相', 'identifier')}


@lru_cache(None)
def _loc_index():
    import loc
    idx = {}
    for t in loc.load_tables().values():
        for k, v in t.items():
            if v.get('zh'):
                idx.setdefault(k, v['zh'])
    return idx


def _show(v):
    if isinstance(v, str):
        zh = _loc_index().get(v)
        return f'{v}（{zh[:60]}）' if zh else v
    return str(v)


def table_docs():
    """[(id, 名字, 正文)]：每个数据表的每一行一篇。"""
    out = []
    for cls, rows in object_tables().items():
        if cls not in TABLES:
            continue
        label, name_field = TABLES[cls]
        for i, r in enumerate(rows):
            if any(x in r['_at'] for x in ('ModHelper', 'Unused', 'Debug')):
                continue  # 模组接口、废弃代码、调试用的，不收
            key = r.get(name_field) or r.get('identifier') or r.get('id') or str(i)
            L = _loc_index()
            zh = next((L[k] for k in (str(key), f'rep_perk_{key}_name', f'item_{key}_name', f'{key}_name')
                       if k in L), str(key))
            lines = [f'{label}「{zh[:40]}」（table:{cls}#{key}，代码常量，定义于 {r["_at"]}）']
            lines += [f'{k}：{_show(v)}' for k, v in r.items() if k != '_at']
            out.append((f'table:{cls}#{key}', f'{zh[:30]} {label}', '\n'.join(lines)))
    return out


@lru_cache(None)
def loc_args():
    """{本地化 key: [参数值]}：代码里 LocHelper.GetLocalized*(key, new object[]{…}) 传进去的常量，
    用来把描述里的 {0}{1}… 代成实际数值。非常量参数记为 '?'。"""
    A = itemdb.assembly()
    out = {}
    for mi in range(1, A.rows[0x06] + 1):
        if not A.row(0x06, mi)[0]:
            continue
        try:
            il = A.il(mi)
        except Exception:
            continue
        last, key, arr, idx, val, after_dup = None, None, None, None, None, False
        for ins in il:
            _at, n, a = ins
            c = cil.const_int(ins)
            if n == 'newarr' and a[1] == 'System.Object':
                key, arr, idx, val = last, {}, None, None
                continue
            if arr is not None:
                if n == 'dup':
                    after_dup, idx, val = True, None, None
                    continue
                if after_dup and idx is None and c is not None:
                    idx = c
                    continue
                if idx is not None and val is None and (c is not None or n == 'ldstr'):
                    val = _fmt(c) if c is not None else a[1]
                    continue
                if n == 'op#a2' and idx is not None:  # stelem.ref
                    arr[idx] = val if val is not None else '?'
                    idx, val, after_dup = None, None, False
                    continue
                if idx is not None and n not in ('box',) and not n.startswith('op#'):
                    val = val if val is not None else '?'
            if n == 'ldstr':
                last = a[1]
            elif n in ('call', 'callvirt') and a[1].startswith('LocHelper::GetLocalized'):
                if arr is not None and key and arr:
                    out.setdefault(key, [arr.get(i, '?') for i in range(max(arr) + 1)])
                arr, key = None, None
    return out


def fill_text(key, text):
    """把描述里的 {i} 换成代码里传入的值；返回 (新文本, 是否代入过)。"""
    args = loc_args().get(key)
    if not args or '{' not in text:
        return text, False
    return _fill(text, args), True


@lru_cache(None)
def item_refs():
    """物品 id（item_xxx_name 的 xxx）→ 代码里用到这个 id 字符串的方法全名集合（反查用途）。"""
    import collections
    A = itemdb.assembly()
    ids = {k[len('item_'):] for k in itemdb.items()}
    ref = collections.defaultdict(set)
    for mi in range(1, A.rows[0x06] + 1):
        if not A.row(0x06, mi)[0]:
            continue
        try:
            il = A.il(mi)
        except Exception:
            continue
        name = None
        for _, n, a in il:
            if n == 'ldstr' and a[1] in ids:
                name = name or A.method_name(mi)
                ref[a[1]].add(name)
    return dict(ref)


_SKIP_REF = ('Debug', 'InitDirectory', 'HandleInitialItem', 'Spawn', 'TooltipUseHelper', '.cctor', 'AddProcedural')


def ref_lines(stem):
    """「用途反查」：哪些配方、机器和功能、顾客的代码用到了这件物品。只认 id 字符串，按标签匹配的用途（如反应堆收任何废金属）查不到。"""
    import re
    ident = stem[len('item_'):]
    own = set(itemdb.items().get(stem, {}).get('where', []))
    groups = {'配方原料（3D 打印芯片等）': set(), '机器与功能': set(), '相关顾客（收或卖这件货）': set()}
    for full in sorted(item_refs().get(ident, ())):
        if full in own or any(k in full for k in _SKIP_REF):
            continue
        cls, meth = full.split('::', 1)
        m = re.match(r'<(\w+)>b__', meth) or re.match(r'<(\w+)>b__', cls)
        core = m[1] if m else meth
        if cls.startswith('ModuleDirectory') and core.startswith('PrinterChip'):
            groups['配方原料（3D 打印芯片等）'].add(core[len('PrinterChip'):])
        elif core.startswith('Create') and not core.startswith(('CreateEmpty', 'CreateMachine')):
            groups['相关顾客（收或卖这件货）'].add(core[len('Create'):])
        else:
            owner = cls if not cls.startswith('<') else ''
            groups['机器与功能'].add(f'{owner}::{core}' if owner and owner not in core else core)
    return [f'{g}：' + '、'.join(sorted(v)[:20]) for g, v in groups.items() if v]


@lru_cache(None)
def class_consts():
    """程序集 Constant 表里的字面常量（C# const 字段）：{类名: {字段: 值}}。机器阈值、修理量、损耗之类都在这里。"""
    import struct
    A = itemdb.assembly()
    fmts = {0x02: '<?', 0x04: '<b', 0x05: '<B', 0x06: '<h', 0x07: '<H', 0x08: '<i', 0x09: '<I', 0x0a: '<q',
            0x0b: '<Q', 0x0c: '<f', 0x0d: '<d'}
    out = {}
    for i in range(1, A.rows.get(0x0B, 0) + 1):
        typ, parent, blob = A.row(0x0B, i)
        if parent & 3 != 0:  # HasConstant：0=Field
            continue
        b, t = A.blob(blob), typ & 0xff
        if t in fmts and len(b) == __import__('struct').calcsize(fmts[t]):
            v = _fmt(struct.unpack(fmts[t], b)[0])
        elif t == 0x0e:
            v = b.decode('utf-16-le', 'replace')
        else:
            continue
        cls, fld = A.field_name(parent >> 2).split('::', 1)
        out.setdefault(cls, {})[fld] = v
    return out


def const_lines(stem):
    """物品定义所在类（不含 *Directory 这种总目录）的数值常量，一行列出。"""
    it = itemdb.items().get(stem)
    if not it:
        return []
    out = []
    for w in it['where']:
        cls = w.split('::')[0]
        if cls.endswith('Directory') or cls.startswith('<'):
            continue
        nums = {k: v for k, v in class_consts().get(cls, {}).items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
        if nums:
            out.append(f'代码常量（{cls}）：' + '、'.join(f'{k}={v}' for k, v in nums.items()))
    return list(dict.fromkeys(out))
