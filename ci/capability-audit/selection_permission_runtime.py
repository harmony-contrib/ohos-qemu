"""Consent through the actual permission-manager window of the owned guest."""
import time
from guest_ui import LayoutNotReady, NodeNotReady, select_node
from run_root_probe import digest

PERMISSION_BUNDLE = 'com.ohos.permissionmanager'
ALLOW_ONCE = ('仅本次允许', 'Allow this time', 'Allow only this time')


def consent_node(layout, app_label='QEMU selection regression'):
    roots = layout if isinstance(layout,list) else [layout]
    pending = [(root,'') for root in roots]; prompts = []; count = 0
    while pending:
        item,inherited = pending.pop(); count += 1
        if count > 100000 or not isinstance(item,dict): raise ValueError('invalid clipboard permission hierarchy')
        attributes = item.get('attributes'); children = item.get('children',[])
        if not isinstance(attributes,dict) or not isinstance(children,list): raise ValueError('invalid clipboard permission node')
        owner = attributes.get('bundleName') or inherited; text = attributes.get('text','')
        if owner == PERMISSION_BUNDLE and app_label in text and ('剪贴板' in text or 'clipboard' in text.lower()):
            if attributes.get('visible') != 'true' or attributes.get('type') != 'Text':
                raise ValueError('clipboard consent prompt not actually visible')
            prompts.append(text)
        pending.extend((child,owner) for child in children)
    if len(prompts) != 1:
        raise NodeNotReady('exact caller clipboard consent prompt not attached')
    candidates = []
    for text in ALLOW_ONCE:
        try:
            node = select_node(layout, PERMISSION_BUNDLE, text=text, clickable=True)
        except NodeNotReady:
            continue
        if node['attributes'].get('type') != 'Button':
            raise ValueError('clipboard consent must use a real permission-manager button')
        candidates.append(node)
    if not candidates:
        raise NodeNotReady('clipboard permission-manager consent button not attached')
    if len(candidates) != 1:
        raise ValueError('clipboard consent button is ambiguous')
    return candidates[0]


def grant_once(ui, label, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            layout, path = ui.layout(bundle=PERMISSION_BUNDLE, label=label)
            node = consent_node(layout)
        except (LayoutNotReady, NodeNotReady):
            time.sleep(.25)
            continue
        screenshot = ui.screenshot(label=label)
        x, y, w, h = node['rect']
        ui.shell('uitest uiInput click ' + str(x + w // 2) + ' ' + str(y + h // 2),
                 label + '-actual-consent-button-center')
        return dict(layout=str(path), layout_sha256=digest(path), selected_node=node,
                    screenshot=str(screenshot), screenshot_sha256=digest(screenshot))
    raise ValueError('actual clipboard permission-manager window never appeared')
