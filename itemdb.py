"""从 Assembly-CSharp 的 *ItemDirectory 类里读出物品定义（物品是代码里链式调用建出来的）。

做法：对每个建物品的方法做一遍符号执行（只认常量、物品本身、未知三种值），
记下所有以物品为接收者或参数的调用及其常量参数，如 set_unitValue(50)、SetGameItemType('FOOD')。
"""
import os
from functools import lru_cache

import cil
import gamedata

DLL = os.path.join(gamedata.DATA_DIR, 'Managed', 'Assembly-CSharp.dll')
UNK = ('?',)
BIN = {0x58: lambda a, b: a + b, 0x59: lambda a, b: a - b, 0x5A: lambda a, b: a * b,
       0x5B: lambda a, b: a / b if isinstance(a, float) or isinstance(b, float) else int(a / b) if b else 0,
       0x5D: lambda a, b: a % b if b else 0}
UNARY_NOOP = set(range(0x67, 0x6F)) | {0x76} | set(range(0x82, 0x8C)) | set(range(0xB3, 0xBB)) | \
    set(range(0xD1, 0xD7)) | {0xE0}
BINARY_OTHER = {0x5C, 0x5E, 0x5F, 0x60, 0x61, 0x62, 0x63, 0x64}
# 不关心的参数噪音
SKIP_CALLS = ('LocHelper::', 'AudioHelper::', 'System.', 'GridPixelElement::', 'PixelWindow::', 'GameItemFunc::')


@lru_cache(None)
def assembly():
    return cil.Assembly(DLL)


def _opcode(name):
    if name.startswith('op#'):
        return int(name[3:], 16)
    return None


def run(A, mi):
    """符号执行一个方法，返回 {物品编号: [(调用名, [参数])]}。
    每次凭空得到一个 GameItem（Empty / CreateEmptyItem / 返回 GameItem 且参数里没有物品）就记为新物品。"""
    st, locs, calls, nxt, flds = [], {}, {}, [0], {}  # flds: 闭包/实例字段里存过的值
    this, _n, _ret, ps = A.sig(0x06000000 | mi, params=True)
    argv = ([UNK] if this else []) + [UNK] * len(ps)
    for i, t in enumerate(ps):  # GameItem 类型的参数也当物品（Machine*/Helper 里常见：InitItem(GameItem item)）
        if t == 'GameItem':
            nxt[0] += 1; argv[i + (1 if this else 0)] = ('item', nxt[0]); calls[nxt[0]] = []

    def pop(n=1):
        out = []
        for _ in range(n):
            out.append(st.pop() if st else UNK)
        return out[::-1]
    for _at, name, arg in A.il(mi):
        code = _opcode(name)
        c = cil.const_int((_at, name, arg))
        if c is not None:
            st.append(('c', c)); continue
        if name == 'ldstr':
            st.append(('c', arg[1]))
        elif name in ('ldnull',):
            st.append(('c', None))
        elif name.startswith('ldarg'):
            k = int(name.split('.')[-1]) if name[-1].isdigit() else arg
            st.append(argv[k] if isinstance(k, int) and k < len(argv) else UNK)
        elif name.startswith('ldloc'):
            k = name.split('.')[-1] if '.' in name and name[-1].isdigit() else arg
            st.append(locs.get(k, UNK))
        elif name.startswith('stloc'):
            k = name.split('.')[-1] if '.' in name and name[-1].isdigit() else arg
            locs[k] = pop()[0]
        elif name == 'dup':
            v = pop()[0]; st += [v, v]
        elif name == 'pop':
            pop()
        elif name in ('ldsfld',):
            st.append(('f', arg[1].split('::')[-1]))
        elif name in ('ldfld', 'ldflda'):
            obj = pop()[0]
            fld = arg[1].split('::')[-1]
            if obj[0] == 'tuple' and fld.startswith('Item') and fld[4:].isdigit() and int(fld[4:]) <= len(obj[1]):
                st.append(obj[1][int(fld[4:]) - 1])  # ValueTuple 的 ItemN
            else:
                st.append(flds.get(arg[1], UNK))
        elif name == 'stfld':
            v = pop()[0]; pop(); flds[arg[1]] = v
        elif name == 'stsfld':
            pop()
        elif name in ('ldftn',):
            st.append(('fn', arg[1]))
        elif name == 'ldvirtftn':
            pop(); st.append(('fn', arg[1]))
        elif name in ('newobj',):
            _this, n, _ret = A.sig(arg[2])
            args = pop(n)
            fn = next((a[1] for a in args if a[0] == 'fn'), None)
            if arg[1].startswith('GameItem::'):
                nxt[0] += 1; st.append(('item', nxt[0])); calls.setdefault(nxt[0], [])
            else:
                st.append(('fn', fn) if fn else ('obj', arg[1].split('::')[0]))
        elif name in ('call', 'callvirt'):
            this, n, ret = A.sig(arg[2])
            args = pop(n + (1 if this else 0))
            meth = arg[1]
            owners = [a[1] for a in args if a[0] == 'item']
            if owners and not meth.startswith(SKIP_CALLS):
                calls.setdefault(owners[0], []).append(
                    (meth, [a[1] if a[0] in ('c', 'f', 'fn') else ('<item>' if a[0] == 'item' else '?')
                            for a in args if not (this and a is args[0])]))
            if ret != 'void':
                short = meth.split('::')[-1]
                if ret.startswith('System.ValueTuple') and 'GameItem' in ret:
                    els = []
                    for t in ret[ret.index('<') + 1:-1].split(','):
                        if t == 'GameItem':
                            nxt[0] += 1; calls.setdefault(nxt[0], []); els.append(('item', nxt[0]))
                        else:
                            els.append(UNK)
                    st.append(('tuple', els))
                elif ret == 'GameItem' or short in ('Empty', 'CreateEmptyItem'):
                    if owners:
                        st.append(('item', owners[0]))
                    else:
                        nxt[0] += 1; st.append(('item', nxt[0])); calls.setdefault(nxt[0], [])
                else:
                    st.append(args[0] if meth.startswith('LocHelper::') and args else UNK)
        elif name in ('newarr', 'box', 'unbox.any', 'castclass', 'isinst', 'ldlen'):
            v = pop()[0]; st.append(v if name in ('box', 'castclass') else UNK)
        elif code in BIN:
            a, b = pop(2)
            st.append(('c', BIN[code](a[1], b[1])) if a[0] == b[0] == 'c' and
                      isinstance(a[1], (int, float)) and isinstance(b[1], (int, float)) else UNK)
        elif code in BINARY_OTHER or name in ('ceq', 'cgt', 'clt', 'cgt.un', 'clt.un'):
            pop(2); st.append(UNK)
        elif code in UNARY_NOOP or code in (0x65, 0x66):
            pass
        elif name in ('ret',):
            pop() if st else None
        elif name.startswith(('br', 'b#', 'leave')):
            if name.startswith(('brfalse', 'brtrue', 'br.s#2c', 'br.s#2d')):
                pop()
            elif name.startswith('b#') or name.startswith('br.s#'):
                if name not in ('br.s#2b',):
                    pop(2)
        elif name in ('stelem', 'stobj') or (code and 0x9B <= code <= 0xA2):
            pop(3 if name != 'stobj' else 2)
        elif name in ('ldelem', 'ldelema') or (code and 0x90 <= code <= 0x9A):
            pop(2); st.append(UNK)
        elif name in ('initobj',):
            pop()
        elif name in ('ldtoken',):
            st.append(UNK)
    return calls


def _directory_ids(A):
    """各 *Directory 的 InitDirectory 里 ldstr <物品 id>; ldftn <lambda> → {lambda 名: 物品 id}。"""
    out = {}
    for ti in range(1, A.rows[0x02] + 1):
        for mi in A.methods_of(ti):
            if not A.method_name(mi).endswith('::InitDirectory'):
                continue
            last = None
            for _at, name, arg in A.il(mi):
                if name == 'ldstr':
                    last = arg[1]
                elif name == 'ldftn' and last:
                    out[arg[1]] = last; last = None
    return out


@lru_cache(None)
def items():
    """扫描全部方法，按名字 key（item_xxx_name）归并物品定义。
    返回 {名字 key 去掉 _name: {'where': [类::方法], 'calls': [(调用, 参数)]}}。"""
    A = assembly()
    out = {}
    for ti in range(1, A.rows[0x02] + 1):
        for mi in A.methods_of(ti):
            try:
                il = A.il(mi)
            except Exception:
                continue
            if not any(n == 'ldstr' and a[1].startswith('item_') for _, n, a in il):
                continue
            try:
                per = run(A, mi)
            except Exception:
                continue
            for calls in per.values():
                key = next((args[0] for meth, args in calls if meth.split('::')[-1] in ('set_name', 'SetName')
                            and args and isinstance(args[0], str) and args[0].startswith('item_')), None)
                if not key:
                    continue
                stem = key[:-5] if key.endswith('_name') else key
                rec = out.setdefault(stem, {'where': [], 'calls': []})
                rec['where'].append(A.method_name(mi))
                if len(calls) > len(rec['calls']):  # 同一物品多处出现时留调用最多的那份（通常是定义处）
                    rec['calls'] = calls
    return out


def summarize(stem, it):
    """一个物品的常用字段：名字 key、类型、价格、标签、厂商……其余调用原样保留。"""
    s = {'stem': stem, 'where': it['where'][:3], 'types': [], 'tags': [], 'other': []}
    for meth, args in it['calls']:
        short = meth.split('::')[-1]
        if short in ('set_name', 'SetName'):
            s.setdefault('name_key', args[0] if args else None)
        elif short == 'set_shortDescription':
            s.setdefault('desc_key', args[0] if args else None)
        elif short == 'set_flavorText':
            s.setdefault('flavor_key', args[0] if args else None)
        elif short in ('set_unitValue', 'SetValue'):
            s['value'] = args[0] if args else None
        elif short == 'SetGameItemType':
            s['types'] += [a for a in args if isinstance(a, str)]
        elif short in ('EnableTag', 'ModifyTag'):
            s['tags'].append(args[0] if len(args) == 1 else args)
        elif short == 'EnableManufacturer':
            s['maker'] = args[0] if args else None
        elif short == 'SetSpriteAndShape':
            s['sprite'] = args[-1] if args else None
        else:
            s['other'].append(f'{meth}({", ".join(map(repr, args))})')
    return s
