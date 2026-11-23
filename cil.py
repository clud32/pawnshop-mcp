"""纯标准库的 .NET 程序集读取：ECMA-335 元数据表 + IL 方法体反汇编。
用来从 Assembly-CSharp.dll 里读出写在代码里的物品、配方、价格常量（这个游戏不放在数据文件里）。"""
import struct

# 表号 -> 列定义。列类型：数字=定长字节；'s' #Strings 索引；'g' #GUID；'b' #Blob；
# ('t', 表号) 单表索引；('c', 编码索引名)
CODED = {
    'TypeDefOrRef': (2, [0x02, 0x01, 0x1B]),
    'HasConstant': (2, [0x04, 0x08, 0x17]),
    'HasCustomAttribute': (5, [0x06, 0x04, 0x01, 0x02, 0x08, 0x09, 0x0A, 0x00, 0x0E, 0x17, 0x14, 0x11, 0x1A,
                               0x1B, 0x20, 0x23, 0x26, 0x27, 0x28, 0x2A, 0x2C, 0x2B]),
    'HasFieldMarshal': (1, [0x04, 0x08]),
    'HasDeclSecurity': (2, [0x02, 0x06, 0x20]),
    'MemberRefParent': (3, [0x02, 0x01, 0x1A, 0x06, 0x1B]),
    'HasSemantics': (1, [0x14, 0x17]),
    'MethodDefOrRef': (1, [0x06, 0x0A]),
    'MemberForwarded': (1, [0x04, 0x06]),
    'Implementation': (2, [0x26, 0x23, 0x27]),
    'CustomAttributeType': (3, [None, None, 0x06, 0x0A, None]),
    'ResolutionScope': (2, [0x00, 0x1A, 0x23, 0x01]),
    'TypeOrMethodDef': (1, [0x02, 0x06]),
}
T = lambda n: ('t', n)  # noqa: E731
C = lambda n: ('c', n)  # noqa: E731
SCHEMA = {
    0x00: [2, 's', 'g', 'g', 'g'],
    0x01: [C('ResolutionScope'), 's', 's'],
    0x02: [4, 's', 's', C('TypeDefOrRef'), T(0x04), T(0x06)],
    0x03: [T(0x04)],
    0x04: [2, 's', 'b'],
    0x05: [T(0x06)],
    0x06: [4, 2, 2, 's', 'b', T(0x08)],
    0x07: [T(0x08)],
    0x08: [2, 2, 's'],
    0x09: [T(0x02), C('TypeDefOrRef')],
    0x0A: [C('MemberRefParent'), 's', 'b'],
    0x0B: [2, C('HasConstant'), 'b'],
    0x0C: [C('HasCustomAttribute'), C('CustomAttributeType'), 'b'],
    0x0D: [C('HasFieldMarshal'), 'b'],
    0x0E: [2, C('HasDeclSecurity'), 'b'],
    0x0F: [2, 4, T(0x02)],
    0x10: [4, T(0x04)],
    0x11: ['b'],
    0x12: [T(0x02), T(0x14)],
    0x13: [T(0x14)],
    0x14: [2, 's', C('TypeDefOrRef')],
    0x15: [T(0x02), T(0x17)],
    0x16: [T(0x17)],
    0x17: [2, 's', 'b'],
    0x18: [2, T(0x06), C('HasSemantics')],
    0x19: [T(0x02), C('MethodDefOrRef'), C('MethodDefOrRef')],
    0x1A: ['s'],
    0x1B: ['b'],
    0x1C: [2, C('MemberForwarded'), 's', T(0x1A)],
    0x1D: [4, T(0x04)],
    0x1E: [4, 4],
    0x1F: [4],
    0x20: [4, 2, 2, 2, 2, 4, 'b', 's', 's'],
    0x21: [4, T(0x20)],
    0x22: [4, 4, 4, T(0x20)],
    0x23: [2, 2, 2, 2, 4, 'b', 's', 's', 'b'],
    0x24: [4, T(0x23)],
    0x25: [4, 4, 4, T(0x23)],
    0x26: [4, 's', 'b'],
    0x27: [4, 4, 's', 's', C('Implementation')],
    0x28: [4, 4, 's', C('Implementation')],
    0x29: [T(0x02), T(0x02)],
    0x2A: [2, 2, C('TypeOrMethodDef'), 's'],
    0x2B: [C('MethodDefOrRef'), 'b'],
    0x2C: [T(0x2A), C('TypeDefOrRef')],
}

# IL 操作码：名字 -> 操作数类型。i1/i4/i8/r4/r8/tok/br1/br4/sw/u1/u2/none
_OPS1 = {
    0x00: ('nop', ''), 0x01: ('break', ''), 0x02: ('ldarg.0', ''), 0x03: ('ldarg.1', ''), 0x04: ('ldarg.2', ''),
    0x05: ('ldarg.3', ''), 0x06: ('ldloc.0', ''), 0x07: ('ldloc.1', ''), 0x08: ('ldloc.2', ''), 0x09: ('ldloc.3', ''),
    0x0A: ('stloc.0', ''), 0x0B: ('stloc.1', ''), 0x0C: ('stloc.2', ''), 0x0D: ('stloc.3', ''),
    0x0E: ('ldarg.s', 'u1'), 0x0F: ('ldarga.s', 'u1'), 0x10: ('starg.s', 'u1'), 0x11: ('ldloc.s', 'u1'),
    0x12: ('ldloca.s', 'u1'), 0x13: ('stloc.s', 'u1'), 0x14: ('ldnull', ''), 0x15: ('ldc.i4.m1', ''),
    0x16: ('ldc.i4.0', ''), 0x17: ('ldc.i4.1', ''), 0x18: ('ldc.i4.2', ''), 0x19: ('ldc.i4.3', ''),
    0x1A: ('ldc.i4.4', ''), 0x1B: ('ldc.i4.5', ''), 0x1C: ('ldc.i4.6', ''), 0x1D: ('ldc.i4.7', ''),
    0x1E: ('ldc.i4.8', ''), 0x1F: ('ldc.i4.s', 'i1'), 0x20: ('ldc.i4', 'i4'), 0x21: ('ldc.i8', 'i8'),
    0x22: ('ldc.r4', 'r4'), 0x23: ('ldc.r8', 'r8'), 0x25: ('dup', ''), 0x26: ('pop', ''), 0x27: ('jmp', 'tok'),
    0x28: ('call', 'tok'), 0x29: ('calli', 'tok'), 0x2A: ('ret', ''),
    0x38: ('br', 'br4'), 0x39: ('brfalse', 'br4'), 0x3A: ('brtrue', 'br4'), 0x45: ('switch', 'sw'),
    0x6F: ('callvirt', 'tok'), 0x70: ('cpobj', 'tok'), 0x71: ('ldobj', 'tok'), 0x72: ('ldstr', 'tok'),
    0x73: ('newobj', 'tok'), 0x74: ('castclass', 'tok'), 0x75: ('isinst', 'tok'), 0x79: ('unbox', 'tok'),
    0x7A: ('throw', ''), 0x7B: ('ldfld', 'tok'), 0x7C: ('ldflda', 'tok'), 0x7D: ('stfld', 'tok'),
    0x7E: ('ldsfld', 'tok'), 0x7F: ('ldsflda', 'tok'), 0x80: ('stsfld', 'tok'), 0x81: ('stobj', 'tok'),
    0x8C: ('box', 'tok'), 0x8D: ('newarr', 'tok'), 0x8E: ('ldlen', ''), 0x8F: ('ldelema', 'tok'),
    0xA3: ('ldelem', 'tok'), 0xA4: ('stelem', 'tok'), 0xA5: ('unbox.any', 'tok'), 0xC2: ('refanyval', 'tok'),
    0xC6: ('mkrefany', 'tok'), 0xD0: ('ldtoken', 'tok'), 0xDD: ('leave', 'br4'), 0xDE: ('leave.s', 'br1'),
}
for _i in range(0x2B, 0x38):
    _OPS1[_i] = (f'br.s#{_i:x}', 'br1')
for _i in range(0x3B, 0x45):
    _OPS1[_i] = (f'b#{_i:x}', 'br4')
for _i in list(range(0x46, 0x6F)) + list(range(0x76, 0x79)) + list(range(0x82, 0x8C)) + \
        list(range(0x90, 0xA3)) + list(range(0xB3, 0xBB)) + [0xC3, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7,
                                                              0xD8, 0xD9, 0xDA, 0xDB, 0xDC, 0xDF, 0xE0]:
    _OPS1.setdefault(_i, (f'op#{_i:x}', ''))
_OPS2 = {0x00: ('arglist', ''), 0x01: ('ceq', ''), 0x02: ('cgt', ''), 0x03: ('cgt.un', ''), 0x04: ('clt', ''),
         0x05: ('clt.un', ''), 0x06: ('ldftn', 'tok'), 0x07: ('ldvirtftn', 'tok'), 0x09: ('ldarg', 'u2'),
         0x0A: ('ldarga', 'u2'), 0x0B: ('starg', 'u2'), 0x0C: ('ldloc', 'u2'), 0x0D: ('ldloca', 'u2'),
         0x0E: ('stloc', 'u2'), 0x0F: ('localloc', ''), 0x11: ('endfilter', ''), 0x12: ('unaligned.', 'u1'),
         0x13: ('volatile.', ''), 0x14: ('tail.', ''), 0x15: ('initobj', 'tok'), 0x16: ('constrained.', 'tok'),
         0x17: ('cpblk', ''), 0x18: ('initblk', ''), 0x19: ('no.', 'u1'), 0x1A: ('rethrow', ''),
         0x1C: ('sizeof', 'tok'), 0x1D: ('refanytype', ''), 0x1E: ('readonly.', '')}
_SIZE = {'': 0, 'u1': 1, 'i1': 1, 'br1': 1, 'u2': 2, 'i4': 4, 'tok': 4, 'br4': 4, 'r4': 4, 'i8': 8, 'r8': 8}


class Assembly:
    def __init__(self, path):
        self.b = b = open(path, 'rb').read()
        pe = struct.unpack_from('<I', b, 0x3C)[0]
        nsec = struct.unpack_from('<H', b, pe + 6)[0]
        opt = pe + 24
        magic = struct.unpack_from('<H', b, opt)[0]
        dd = opt + (96 if magic == 0x10B else 112)
        cli_rva = struct.unpack_from('<I', b, dd + 14 * 8)[0]
        sec = opt + struct.unpack_from('<H', b, pe + 20)[0]
        self.secs = []
        for i in range(nsec):
            o = sec + i * 40
            vsize, va, rsize, raw = struct.unpack_from('<IIII', b, o + 8)
            self.secs.append((va, max(vsize, rsize), raw))
        cli = self.off(cli_rva)
        md_rva, _ = struct.unpack_from('<II', b, cli + 8)
        md = self.off(md_rva)
        vlen = struct.unpack_from('<I', b, md + 12)[0]
        p = md + 16 + vlen + 2
        nstreams = struct.unpack_from('<H', b, p)[0]; p += 2
        self.streams = {}
        for _ in range(nstreams):
            so, ss = struct.unpack_from('<II', b, p); p += 8
            e = b.index(b'\0', p); name = b[p:e].decode(); p = (e + 4) // 4 * 4
            self.streams[name] = (md + so, ss)
        self._tables()

    def off(self, rva):
        for va, size, raw in self.secs:
            if va <= rva < va + size:
                return rva - va + raw
        raise ValueError(f'RVA {rva:#x} 不在任何节里')

    def _tables(self):
        b = self.b
        p, _ = self.streams.get('#~') or self.streams['#-']
        heap = b[p + 6]
        self.wstr, self.wguid, self.wblob = (4 if heap & 1 else 2), (4 if heap & 2 else 2), (4 if heap & 4 else 2)
        valid = struct.unpack_from('<Q', b, p + 8)[0]
        q = p + 24
        self.rows = {}
        for t in range(64):
            if valid >> t & 1:
                self.rows[t] = struct.unpack_from('<I', b, q)[0]; q += 4

        def width(col):
            if isinstance(col, int): return col
            if col == 's': return self.wstr
            if col == 'g': return self.wguid
            if col == 'b': return self.wblob
            if col[0] == 't': return 2 if self.rows.get(col[1], 0) < 1 << 16 else 4
            bits, tabs = CODED[col[1]]
            mx = max(self.rows.get(t, 0) for t in tabs if t is not None)
            return 2 if mx < 1 << (16 - bits) else 4
        self.tab = {}
        for t in sorted(self.rows):
            cols = SCHEMA[t]
            ws = [width(c) for c in cols]
            self.tab[t] = (q, sum(ws), ws, cols)
            q += self.rows[t] * sum(ws)

    def row(self, t, i):
        """第 i 行（从 1 开始）→ 原始列值列表。"""
        q, rs, ws, _cols = self.tab[t]
        p = q + (i - 1) * rs
        out = []
        for w in ws:
            out.append(struct.unpack_from('<H' if w == 2 else '<I', self.b, p)[0] if w in (2, 4) else
                       int.from_bytes(self.b[p:p + w], 'little')); p += w
        return out

    def string(self, i):
        p, _ = self.streams['#Strings']
        e = self.b.index(b'\0', p + i)
        return self.b[p + i:e].decode('utf-8', 'replace')

    def blob(self, i):
        p, _ = self.streams['#Blob']
        p += i
        n, k = _cuint(self.b, p)
        return self.b[p + k:p + k + n]

    def us(self, i):
        p, _ = self.streams['#US']
        p += i
        n, k = _cuint(self.b, p)
        return self.b[p + k:p + k + n - 1].decode('utf-16-le', 'replace')

    # ---------- 名字解析 ----------
    def typedef_name(self, i):
        r = self.row(0x02, i)
        ns, n = self.string(r[2]), self.string(r[1])
        return f'{ns}.{n}' if ns else n

    def typeref_name(self, i):
        r = self.row(0x01, i)
        ns, n = self.string(r[2]), self.string(r[1])
        return f'{ns}.{n}' if ns else n

    def type_of_coded(self, v, kind='TypeDefOrRef'):
        bits, tabs = CODED[kind]
        t, i = tabs[v & ((1 << bits) - 1)], v >> bits
        if t == 0x02: return self.typedef_name(i)
        if t == 0x01: return self.typeref_name(i)
        if t == 0x1B: return f'TypeSpec#{i}'
        if t == 0x06: return self.method_name(i)
        return f'{t:#x}#{i}'

    def method_name(self, i):
        return f'{self.typedef_name(self.method_owner(i))}::{self.string(self.row(0x06, i)[3])}'

    def field_name(self, i):
        return f'{self.typedef_name(self.field_owner(i))}::{self.string(self.row(0x04, i)[1])}'

    def _owner(self, i, col, table):
        if not hasattr(self, '_own'):
            self._own = {}
        key = (col, table)
        if key not in self._own:
            starts = [self.row(0x02, t)[col] for t in range(1, self.rows[0x02] + 1)]
            self._own[key] = starts
        starts = self._own[key]
        lo = 0
        for t, s in enumerate(starts):
            if s <= i: lo = t
            else: break
        return lo + 1

    def method_owner(self, i):
        return self._owner(i, 5, 0x06)

    def field_owner(self, i):
        return self._owner(i, 4, 0x04)

    def token(self, tok):
        t, i = tok >> 24, tok & 0xFFFFFF
        if t == 0x70: return ('str', self.us(i))
        if t == 0x06: return ('method', self.method_name(i))
        if t == 0x04: return ('field', self.field_name(i))
        if t == 0x02: return ('type', self.typedef_name(i))
        if t == 0x01: return ('type', self.typeref_name(i))
        if t == 0x0A:
            r = self.row(0x0A, i)
            return ('method' if self.blob(r[2])[:1] != b'\x06' else 'field',
                    f'{self.type_of_coded(r[0], "MemberRefParent")}::{self.string(r[1])}')
        if t == 0x2B:
            r = self.row(0x2B, i)
            return ('method', self.type_of_coded(r[0], 'MethodDefOrRef') + '<>')
        if t == 0x1B: return ('type', f'TypeSpec#{i}')
        return ('tok', f'{tok:#x}')

    # ---------- 签名 ----------
    def sig(self, tok, params=False):
        """方法 token → (hasthis, 参数个数, 返回类型名)；params=True 时再附参数类型列表。"""
        t, i = tok >> 24, tok & 0xFFFFFF
        if t == 0x2B:
            v = self.row(0x2B, i)[0]
            bits, tabs = CODED['MethodDefOrRef']
            t, i = tabs[v & 1], v >> bits
        if t == 0x06:
            blob = self.blob(self.row(0x06, i)[4])
        elif t == 0x0A:
            blob = self.blob(self.row(0x0A, i)[2])
        else:
            return False, 0, '?'
        cc = blob[0]; p = 1
        if cc & 0x10:
            _, k = _cuint(blob, p); p += k
        n, k = _cuint(blob, p); p += k
        ret, p = self._type(blob, p)
        if not params:
            return bool(cc & 0x20), n, ret
        ps = []
        for _ in range(n):
            t, p = self._type(blob, p); ps.append(t)
        return bool(cc & 0x20), n, ret, ps

    _ET = {0x01: 'void', 0x02: 'bool', 0x03: 'char', 0x04: 'sbyte', 0x05: 'byte', 0x06: 'short', 0x07: 'ushort',
           0x08: 'int', 0x09: 'uint', 0x0A: 'long', 0x0B: 'ulong', 0x0C: 'float', 0x0D: 'double', 0x0E: 'string',
           0x16: 'typedref', 0x18: 'nint', 0x19: 'nuint', 0x1C: 'object'}

    def _type(self, s, p):
        e = s[p]; p += 1
        if e in self._ET: return self._ET[e], p
        if e in (0x11, 0x12):
            v, k = _cuint(s, p); return self.type_of_coded(v), p + k
        if e in (0x0F, 0x10, 0x1D, 0x45):
            t, p = self._type(s, p); return t + ('[]' if e == 0x1D else '&'), p
        if e in (0x13, 0x1E):
            v, k = _cuint(s, p); return f'T{v}', p + k
        if e in (0x1F, 0x20):
            _, k = _cuint(s, p); return self._type(s, p + k)
        if e == 0x15:
            t, p = self._type(s, p); n, k = _cuint(s, p); p += k
            args = []
            for _ in range(n):
                a, p = self._type(s, p); args.append(a)
            return f'{t}<{",".join(args)}>', p
        return f'et{e:#x}', p

    def param_names(self, mi):
        """MethodDef 的参数名（不含 this）。"""
        r = self.row(0x06, mi)
        start = r[5]
        end = self.row(0x06, mi + 1)[5] if mi < self.rows[0x06] else self.rows.get(0x08, 0) + 1
        out = {}
        for i in range(start, end):
            pr = self.row(0x08, i)
            if pr[1]:
                out[pr[1]] = self.string(pr[2])
        return [out[k] for k in sorted(out)]

    def method_index(self):
        """方法全名 → MethodDef 行号（重载取第一个）。"""
        if not hasattr(self, '_midx'):
            self._midx = {}
            for i in range(1, self.rows[0x06] + 1):
                self._midx.setdefault(self.method_name(i), i)
        return self._midx

    # ---------- 类型与方法 ----------
    def types(self):
        return {self.typedef_name(i): i for i in range(1, self.rows[0x02] + 1)}

    def methods_of(self, ti):
        start = self.row(0x02, ti)[5]
        end = self.row(0x02, ti + 1)[5] if ti < self.rows[0x02] else self.rows[0x06] + 1
        return list(range(start, end))

    def fields_of(self, ti):
        start = self.row(0x02, ti)[4]
        end = self.row(0x02, ti + 1)[4] if ti < self.rows[0x02] else self.rows[0x04] + 1
        return [(i, self.string(self.row(0x04, i)[1]), self.row(0x04, i)[0]) for i in range(start, end)]

    def il(self, mi):
        """方法体 → [(偏移, 操作码名, 操作数)]，tok 操作数已解析成 (类别, 名字)。"""
        rva = self.row(0x06, mi)[0]
        if not rva:
            return []
        b, p = self.b, self.off(rva)
        h = b[p]
        if h & 3 == 2:
            size, p = h >> 2, p + 1
        else:
            size = struct.unpack_from('<I', b, p + 4)[0]; p += (struct.unpack_from('<H', b, p)[0] >> 12) * 4
        code, out, i = b[p:p + size], [], 0
        while i < len(code):
            at = i
            op = code[i]; i += 1
            if op == 0xFE:
                name, kind = _OPS2.get(code[i], (f'fe#{code[i]:x}', '')); i += 1
            else:
                name, kind = _OPS1.get(op, (f'op#{op:x}', ''))
            arg = None
            if kind == 'sw':
                n = struct.unpack_from('<I', code, i)[0]; i += 4 + 4 * n
            elif kind:
                raw = code[i:i + _SIZE[kind]]; i += _SIZE[kind]
                fmt = {'u1': '<B', 'i1': '<b', 'br1': '<b', 'u2': '<H', 'i4': '<i', 'br4': '<i', 'tok': '<I',
                       'r4': '<f', 'i8': '<q', 'r8': '<d'}[kind]
                arg = struct.unpack(fmt, raw)[0]
                if kind == 'tok':
                    arg = self.token(arg) + (arg,)  # (类别, 名字, 原始 token)
            out.append((at, name, arg))
        return out


def _cuint(b, p):
    x = b[p]
    if x & 0x80 == 0: return x, 1
    if x & 0xC0 == 0x80: return ((x & 0x3F) << 8) | b[p + 1], 2
    return ((x & 0x1F) << 24) | (b[p + 1] << 16) | (b[p + 2] << 8) | b[p + 3], 4


def const_int(ins):
    """ldc.i4 系列 → int；不是常量返回 None。"""
    name, arg = ins[1], ins[2]
    if name.startswith('ldc.i4.') and name[7:] not in ('s',):
        return -1 if name == 'ldc.i4.m1' else int(name[7:])
    if name in ('ldc.i4', 'ldc.i4.s', 'ldc.i8', 'ldc.r4', 'ldc.r8'):
        return arg
    return None
