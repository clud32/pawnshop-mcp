"""Easy Save 3 存档读取：明文 JSON，但字典的整数键不带引号（{8376:{...}}），先补引号再解析。"""
import json


def _quote_bare_keys(s):
    out, i, n, in_str = [], 0, len(s), False
    while i < n:
        c = s[i]
        if in_str:
            if c == '\\':
                nxt = s[i + 1]
                # ES3 会写出 \' 这类 JSON 不认的转义，补成字面反斜杠
                out.append(c + nxt if nxt in '"\\/bfnrtu' else '\\\\' + nxt)
                i += 2; continue
            out.append(c)
            if c == '"':
                in_str = False
            i += 1; continue
        if c == '"':
            in_str = True; out.append(c); i += 1; continue
        if c in '{,':
            out.append(c); i += 1
            j = i
            while j < n and s[j] in ' \t\r\n':
                j += 1
            k = j
            while k < n and (s[k].isdigit() or s[k] == '-'):
                k += 1
            if k > j and k < n and s[k] == ':':
                out.append(s[i:j] + '"' + s[j:k] + '"'); i = k
            continue
        out.append(c); i += 1
    return ''.join(out)


def load(path):
    with open(path, encoding='utf-8') as f:
        s = f.read()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return json.loads(_quote_bare_keys(s))
