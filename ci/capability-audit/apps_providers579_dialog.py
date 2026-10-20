"""Fixed production Photos consent, scoped to the real owned ordinary caller.

Same production zh_CN title/ancestor/button contract as photos_dialog_contract;
no shared helper modification and no arbitrary JSON selectors or text.
"""
from guest_ui import NodeNotReady, bounds
from apps_providers579_project import bundle, require


def select(layout, run, kind, case='photos'):
    require(kind in ('save', 'delete') and case in ('photos', 'camera') and (kind == 'delete' or case == 'photos'), 'two actual consent actions')
    owner = bundle(case, 'normal')
    title = ('允许“Apps579 photos normal ' + run[:8] + '”保存 1 张图片？' if kind == 'save' else '是否删除此图片？')
    allow, deny = ('允许', '禁止') if kind == 'save' else ('删除', '取消')
    entries, titles = [], []
    def walk(node, inherited, parents, depth):
        require(depth <= 256 and len(entries) < 100000 and type(node) is dict, 'bounded actual hierarchy')
        attrs, children = node['attributes'], node.get('children', [])
        actual_owner = attrs.get('bundleName') or inherited
        entry = node, actual_owner, parents
        entries.append(entry)
        if actual_owner in (owner, 'com.ohos.photos') and attrs.get('visible') == 'true' and attrs.get('text') == title:
            titles.append(entry)
        for child in children:
            walk(child, actual_owner, parents + [(node, actual_owner)], depth + 1)
    for root in layout if type(layout) is list else [layout]:
        walk(root, '', [], 0)
    if not titles:
        raise NodeNotReady('actual source-bound caller/count-specific Photos title absent')
    require(len(titles) == 1, 'ambiguous actual Photos title')
    node, actual_owner, ancestors = titles[0]
    def buttons(subtree, text):
        found = {}
        for current, current_owner, parents in entries:
            if current_owner != actual_owner or current['attributes'].get('text') != text:
                continue
            chain = parents + [(current, current_owner)]
            if not any(p is subtree for p, _ in chain):
                continue
            for parent, parent_owner in reversed(chain):
                attrs = parent['attributes']
                if parent_owner == actual_owner and attrs.get('type') == 'Button':
                    if attrs.get('visible') == attrs.get('enabled') == attrs.get('clickable') == 'true':
                        found[id(parent)] = {'attributes': attrs, 'bundle': actual_owner, 'rect': list(bounds(attrs.get('bounds')))}
                    break
        return list(found.values())
    for ancestor, _ in reversed(ancestors + [(node, actual_owner)]):
        yes, no = buttons(ancestor, allow), buttons(ancestor, deny)
        require(len(yes) <= 1 and len(no) <= 1, 'ambiguous actual Photos buttons')
        if len(yes) == len(no) == 1:
            require(yes[0] != no[0], 'same actual button cannot allow and deny')
            return yes[0], {'kind': kind, 'locale': 'zh_CN', 'title': title, 'deny': no[0]}
    raise NodeNotReady('complete actual Photos dialog not ready')
