"""Select the actual titled Photos dialog; generated button indices are unstable."""
from guest_ui import NodeNotReady, bounds


# Fixed production zh_CN resources, checked against System round18 ui-contract
# e65ed60b7d4f022b19c2ebe5ca836992bce595d1d72ba0dc6b81b36a2e4b54df.
# An unsupported locale must fail instead of guessing a translation.
ZH = {'save': {'title': '允许“%s”保存 %d 张图片？', 'allow': '允许', 'deny': '禁止'},
      'delete': {'title': '是否删除此图片？', 'allow': '删除', 'deny': '取消'}}


def select_dialog(layout, owner, kind, *, label=None, count=None):
    if owner not in ('com.ohos.photos', 'org.harmonycontrib.wallpaperchallenge',
                     'org.harmonycontrib.knowledgeimporter') or kind not in ZH:
        raise ValueError('fixed actual Photos dialog owner and action required')
    spec = ZH[kind]
    if kind == 'delete' and owner != 'com.ohos.photos': raise ValueError('actual Photos browser deletion required')
    if kind == 'save':
        if not isinstance(label, str) or not 1 <= len(label) <= 128 or type(count) is not int or not 1 <= count <= 100:
            raise ValueError('actual caller label and exact image count required')
        title = spec['title'] % (label, count)
    else:
        if label is not None or count is not None: raise ValueError('single active-photo deletion has no caller/count template')
        title = spec['title']
    roots = layout if isinstance(layout, list) else [layout]
    entries = []; titles = []
    def walk(node, inherited, parents, depth):
        if len(entries) >= 100000 or depth > 256 or not isinstance(node, dict):
            raise ValueError('invalid actual dialog hierarchy')
        attrs, children = node.get('attributes'), node.get('children', [])
        if not isinstance(attrs, dict) or not isinstance(children, list): raise ValueError('invalid actual dialog node')
        bundle = attrs.get('bundleName') or inherited
        entry = (node, bundle, parents); entries.append(entry)
        if bundle == owner and attrs.get('visible') == 'true' and attrs.get('text') == title: titles.append(entry)
        for child in children: walk(child, bundle, parents + [(node, bundle)], depth + 1)
    for root in roots: walk(root, '', [], 0)
    if not titles: raise NodeNotReady('actual caller/count-specific Photos dialog title unavailable')
    if len(titles) != 1: raise ValueError('ambiguous actual Photos dialog title')
    node, _, ancestors = titles[0]
    def buttons(subtree, text):
        candidates = {}
        for current, bundle, parents in entries:
            if bundle != owner or current['attributes'].get('text') != text or current['attributes'].get('visible') != 'true': continue
            chain = parents + [(current, bundle)]
            indices = [i for i, (parent, _) in enumerate(chain) if parent is subtree]
            if not indices: continue
            for parent, actual_owner in reversed(chain[indices[0]:]):
                attrs = parent['attributes']
                if actual_owner == owner and attrs.get('type') == 'Button':
                    if attrs.get('visible') == 'true':
                        candidates[id(parent)] = {'attributes': attrs, 'bundle': owner, 'rect': list(bounds(attrs.get('bounds')))}
                    break
        return list(candidates.values())
    for ancestor, _ in reversed(ancestors + [(node, owner)]):
        allow, deny = buttons(ancestor, spec['allow']), buttons(ancestor, spec['deny'])
        if len(allow) > 1 or len(deny) > 1: raise ValueError('ambiguous actual Photos dialog buttons')
        if len(allow) == len(deny) == 1:
            if allow[0] == deny[0]: raise ValueError('same button cannot confirm and deny the dialog')
            if any(button['attributes'].get('enabled') != 'true' or button['attributes'].get('clickable') != 'true'
                   for button in (allow[0], deny[0])):
                raise NodeNotReady('the actual titled Photos dialog buttons are not enabled clickable controls')
            return allow[0], {'kind': kind, 'locale': 'zh_CN', 'title': title, 'allow': spec['allow'], 'deny': spec['deny']}
    raise NodeNotReady('complete enabled confirm/deny buttons in the actual titled Photos dialog unavailable')
