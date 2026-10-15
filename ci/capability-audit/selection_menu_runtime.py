"""Select a real enabled menu button through its observed label child."""
import time
from guest_ui import bounds, LayoutNotReady, NodeNotReady


def menu_button(layout, bundle, labels):
    roots=layout if isinstance(layout,list) else [layout]
    pending=[(root,'',[]) for root in roots];found=[];count=0
    while pending:
        node,inherited,parents=pending.pop();count+=1
        if count>100000 or len(parents)>256 or not isinstance(node,dict):raise ValueError('invalid menu hierarchy')
        attributes=node.get('attributes');children=node.get('children',[])
        if not isinstance(attributes,dict) or not isinstance(children,list):raise ValueError('invalid menu node')
        actual=attributes.get('bundleName') or inherited
        if actual==bundle and attributes.get('text') in labels:
            if attributes.get('type')!='SelectMenuButtonText' or attributes.get('visible')!='true':
                raise ValueError('menu label is not an actual visible selection-menu label')
            candidates=[parent for parent in reversed(parents) if parent.get('type')=='SelectMenuButton']
            if not candidates:raise ValueError('selection menu label has no real button parent')
            parent=candidates[0]
            if any(parent.get(key)!='true' for key in ('visible','enabled','clickable')):
                raise ValueError('selection menu button is not enabled and clickable')
            rect=list(bounds(parent.get('bounds')));text_rect=list(bounds(attributes.get('bounds')))
            x,y,w,h=rect;tx,ty,tw,th=text_rect
            if not(x<=tx and y<=ty and tx+tw<=x+w and ty+th<=y+h):raise ValueError('menu label escaped its button bounds')
            found.append(dict(attributes=parent,bundle=actual,rect=rect,label=attributes['text'],label_attributes=attributes))
        pending.extend((child,actual,parents+[attributes]) for child in children)
    if not found:raise NodeNotReady('actual selection menu button is not attached')
    if len(found)!=1:raise ValueError('actual selection menu button label is ambiguous')
    return found[0]


def click_menu(ui,bundle,labels,label,timeout=60):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            layout,path=ui.layout(bundle=bundle,label=label)
            node=menu_button(layout,bundle,labels)
        except (LayoutNotReady,NodeNotReady):time.sleep(.25);continue
        x,y,w,h=node['rect'];ui.shell('uitest uiInput click '+str(x+w//2)+' '+str(y+h//2),label+'-actual-menu-button-center')
        return dict(layout=str(path),selected_node=node)
    raise ValueError('actual selection menu never attached its requested enabled button')
