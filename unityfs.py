"""纯标准库的 Unity 资源读取：UnityFS 包（LZ4/LZ4HC）→ SerializedFile → 按类型树读对象。
只支持带类型树的文件（Addressables 包默认带；游戏主体 .assets 不带，要另行处理）。"""
import struct

COMMON = ("AABB\0AnimationClip\0AnimationCurve\0AnimationState\0Array\0Base\0BitField\0bitset\0bool\0char\0"
          "ColorRGBA\0Component\0data\0deque\0double\0dynamic_array\0FastPropertyName\0first\0float\0Font\0"
          "GameObject\0Generic Mono\0GradientNEW\0GUID\0GUIStyle\0int\0list\0long long\0map\0Matrix4x4f\0"
          "MdFour\0MonoBehaviour\0MonoScript\0m_ByteSize\0m_Curve\0m_EditorClassIdentifier\0m_EditorHideFlags\0"
          "m_Enabled\0m_ExtensionPtr\0m_GameObject\0m_Index\0m_IsArray\0m_IsStatic\0m_MetaFlag\0m_Name\0"
          "m_ObjectHideFlags\0m_PrefabInternal\0m_PrefabParentObject\0m_Script\0m_StaticEditorFlags\0m_Type\0"
          "m_Version\0Object\0pair\0PPtr<Component>\0PPtr<GameObject>\0PPtr<Material>\0PPtr<MonoBehaviour>\0"
          "PPtr<MonoScript>\0PPtr<Object>\0PPtr<Prefab>\0PPtr<Sprite>\0PPtr<TextAsset>\0PPtr<Texture>\0"
          "PPtr<Texture2D>\0PPtr<Transform>\0Prefab\0Quaternionf\0Rectf\0RectInt\0RectOffset\0second\0set\0"
          "short\0size\0SInt16\0SInt32\0SInt64\0SInt8\0staticvector\0string\0TextAsset\0TextMesh\0Texture\0"
          "Texture2D\0Transform\0TypelessData\0UInt16\0UInt32\0UInt64\0UInt8\0unsigned int\0unsigned long long\0"
          "unsigned short\0vector\0Vector2f\0Vector3f\0Vector4f\0m_ScriptingClassIdentifier\0Gradient\0Type*\0"
          "int2_storage\0int3_storage\0BoundsInt\0m_CorrespondingSourceObject\0m_PrefabInstance\0m_PrefabAsset\0"
          "FileSize\0Hash128\0RenderingLayerMask\0").encode()

PRIM = {'bool': '?', 'char': 'c', 'SInt8': 'b', 'UInt8': 'B', 'short': 'h', 'SInt16': 'h', 'unsigned short': 'H',
        'UInt16': 'H', 'int': 'i', 'SInt32': 'i', 'unsigned int': 'I', 'UInt32': 'I', 'Type*': 'I',
        'long long': 'q', 'SInt64': 'q', 'unsigned long long': 'Q', 'UInt64': 'Q', 'FileSize': 'Q',
        'float': 'f', 'double': 'd'}


def lz4_block(src, size):
    dst = bytearray(); i = 0; n = len(src)
    while i < n:
        tok = src[i]; i += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                b = src[i]; i += 1; lit += b
                if b != 255: break
        dst += src[i:i + lit]; i += lit
        if i >= n: break
        off = src[i] | (src[i + 1] << 8); i += 2
        ml = tok & 15
        if ml == 15:
            while True:
                b = src[i]; i += 1; ml += b
                if b != 255: break
        ml += 4
        st = len(dst) - off
        if off >= ml:
            dst += dst[st:st + ml]
        else:
            for k in range(ml): dst.append(dst[st + k])
    return bytes(dst[:size])


def _decomp(data, usize, flags):
    c = flags & 0x3f
    if c == 0: return data
    if c in (2, 3): return lz4_block(data, usize)
    if c == 1:
        import lzma
        props = data[:5]
        return lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[{'id': lzma.FILTER_LZMA1,
                'dict_size': struct.unpack('<I', props[1:5])[0], 'lc': props[0] % 9,
                'lp': (props[0] // 9) % 5, 'pb': props[0] // 45}]).decompress(data[5:])[:usize]
    raise ValueError(f'未支持的压缩 {c}')


def read_bundle(path):
    """返回 {节点路径: bytes}。"""
    b = open(path, 'rb').read(); p = 0

    def cstr():
        nonlocal p
        e = b.index(b'\0', p); s = b[p:e].decode(); p = e + 1; return s
    if cstr() != 'UnityFS': raise ValueError('不是 UnityFS 包')
    ver = struct.unpack('>I', b[p:p + 4])[0]; p += 4; cstr(); cstr()
    _size, csz, usz, flags = struct.unpack('>QIII', b[p:p + 20]); p += 20
    if ver >= 7: p = (p + 15) // 16 * 16
    if flags & 0x80:
        info = b[len(b) - csz:]
    else:
        info = b[p:p + csz]; p += csz
    info = _decomp(info, usz, flags)
    q = 16; nb = struct.unpack('>i', info[q:q + 4])[0]; q += 4
    blocks = []
    for _ in range(nb):
        u, c, f = struct.unpack('>IIH', info[q:q + 10]); q += 10; blocks.append((u, c, f))
    nn = struct.unpack('>i', info[q:q + 4])[0]; q += 4
    nodes = []
    for _ in range(nn):
        off, sz, f = struct.unpack('>qqI', info[q:q + 20]); q += 20
        e = info.index(b'\0', q); name = info[q:e].decode(); q = e + 1
        nodes.append((off, sz, name))
    if flags & 0x200: p = (p + 15) // 16 * 16
    data = bytearray()
    for u, c, f in blocks:
        data += _decomp(b[p:p + c], u, f); p += c
    return {name: bytes(data[off:off + sz]) for off, sz, name in nodes}


class SerializedFile:
    def __init__(self, b):
        self.b = b
        ver = struct.unpack('>I', b[8:12])[0]
        if ver < 22: raise ValueError(f'SerializedFile 版本 {ver} 未支持')
        self.big = b[16] != 0
        _meta, _fs, self.data_off = struct.unpack('>IQQ', b[20:40])
        self.p = 48; E = '>' if self.big else '<'; self.E = E
        self.unity = self._cstr(); self._r('i')
        self.typetree = self._r('?')
        self.types = []
        for _ in range(self._r('i')):
            cid = self._r('i'); self._r('?'); self._r('h')
            if cid == 114: self.p += 16
            self.p += 16
            nodes = self._tree() if self.typetree else None
            self.types.append((cid, nodes))
        self.objects = []
        for _ in range(self._r('i')):
            self.p = (self.p + 3) // 4 * 4
            pid = self._r('q'); start = self._r('q'); size = self._r('I'); ti = self._r('i')
            self.objects.append((pid, self.data_off + start, size, ti))
        for _ in range(self._r('i')):  # script types（预加载表，用不到）
            self._r('i'); self.p = (self.p + 3) // 4 * 4; self._r('q')
        self.externals = []  # PPtr 的 m_FileID=k 指 externals[k-1]
        for _ in range(self._r('i')):
            self._cstr(); self.p += 20; self.externals.append(self._cstr().replace('\\', '/').rsplit('/', 1)[-1])

    def _r(self, f):
        v = struct.unpack_from(self.E + f, self.b, self.p)[0]; self.p += struct.calcsize(f); return v

    def _cstr(self):
        e = self.b.find(b'\0', self.p); s = self.b[self.p:e].decode('utf-8', 'replace'); self.p = e + 1; return s

    def _tree(self):
        n = self._r('i'); sbs = self._r('i'); raw = []
        for _ in range(n):
            _v, lvl, _tf, to, no, bs, _ix, mf, _h = struct.unpack_from(self.E + 'HBBIIiiiQ', self.b, self.p)
            self.p += 32; raw.append((lvl, to, no, mf))
        sb = self.b[self.p:self.p + sbs]; self.p += sbs
        deps = self._r('i')  # type dependencies（别写成 self.p += 4*self._r()，会丢掉 _r 自己的 +4）
        self.p += 4 * deps

        def s(o):
            buf, o = (COMMON, o & 0x7fffffff) if o & 0x80000000 else (sb, o)
            return buf[o:buf.index(b'\0', o)].decode()
        return [(lvl, s(to), s(no), mf) for lvl, to, no, mf in raw]

    def read(self, obj):
        pid, start, size, ti = obj
        nodes = self.types[ti][1]
        if nodes is None: raise ValueError('无类型树')
        r = _Reader(self.b, start, self.E)
        # 顶层逐字段读，某个字段（常见是 ManagedReference 的 references）读坏了就保留前面已读的部分
        lvl0 = nodes[0][0]
        out, j = {}, 1
        while j < len(nodes):
            if nodes[j][0] == lvl0 + 1:
                try:
                    out[nodes[j][2]], _ = r.node(nodes, j)
                except Exception:
                    out['_partial'] = True
                    break
            j += 1
        return out

    def class_id(self, obj):
        return self.types[obj[3]][0]

    def raw(self, obj):
        return self.b[obj[1]:obj[1] + obj[2]]


def open_assets(path):
    """游戏主体 .assets 可能几百 MB，用 mmap 读。"""
    import mmap
    f = open(path, 'rb')
    return SerializedFile(mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ))


class _Reader:
    def __init__(self, b, p, E):
        self.b, self.p, self.E = b, p, E

    def align(self):
        self.p = (self.p + 3) // 4 * 4

    def node(self, nodes, i):
        lvl, typ, name, mf = nodes[i]
        kids = []; j = i + 1
        while j < len(nodes) and nodes[j][0] > lvl:
            if nodes[j][0] == lvl + 1: kids.append(j)
            j += 1
        if typ in PRIM and not kids:
            f = PRIM[typ]
            v = struct.unpack_from(self.E + f, self.b, self.p)[0]; self.p += struct.calcsize(f)
        elif typ == 'string':
            n = struct.unpack_from(self.E + 'i', self.b, self.p)[0]; self.p += 4
            v = self.b[self.p:self.p + n].decode('utf-8', 'replace'); self.p += n
            self.align()
        elif kids and nodes[kids[0]][1] == 'Array':
            v, _ = self.node(nodes, kids[0])
        elif typ == 'Array':
            n = struct.unpack_from(self.E + 'i', self.b, self.p)[0]; self.p += 4
            el = kids[1]
            if nodes[el][1] in ('UInt8', 'char') and not any(x[0] > nodes[el][0] for x in nodes[el + 1:el + 2]):
                v = self.b[self.p:self.p + n]; self.p += n
            else:
                v = [self.node(nodes, el)[0] for _ in range(n)]
        elif typ == 'TypelessData':
            n = struct.unpack_from(self.E + 'i', self.b, self.p)[0]; self.p += 4
            v = self.b[self.p:self.p + n]; self.p += n
        else:
            v = {}
            for k in kids:
                v[nodes[k][2]] = self.node(nodes, k)[0]
        if mf & 0x4000: self.align()
        return v, j
