"""Small typed relationships shared by quest, item and map cards."""
import math


def relationship(store,kind,identity,subtitle='',*,key=None):
    record=store.entry(kind,identity)
    if not record:return None
    entry,row=record
    return dict(key=key or entry.key,target=entry.key if store.available(kind,identity) else None,
                name=entry.name,subtitle=subtitle,icon=entry.icon)


def quest_rewards(row):
    """Keep choice/class pools separate; never count their flat copies twice."""
    result=[]
    for index,reward in enumerate(row.get('rewards',[])):
        if reward.get('type')=='item' and reward.get('guaranteed') is False:continue
        result.append({**reward,'key':('reward',index),'caption':'Reward'})
    for field,label in (('reward_choices','Choose one'),('reward_random','Random reward')):
        for pool_index,pool in enumerate(row.get(field,[])):
            for group_index,group in enumerate(pool.get('groups',[])):
                items=group.get('items',[]);weights=[r.get('weight') for r in items]
                valid=bool(items and all(type(n) in (int,float) and math.isfinite(n) and n>0 for n in weights))
                total=sum(weights) if valid else 0
                for index,item in enumerate(items):
                    caption=label
                    if field=='reward_random' and total:caption+=' · '+f"{100*item['weight']/total:.1f}".rstrip('0').rstrip('.')+'%'
                    classes=group.get('classes') or []
                    if classes:caption+=' · '+', '.join(classes)
                    result.append(dict(type='item',**item,key=(field,pool_index,group_index,index),caption=caption))
    return result


def item_quest_sources(store,item_id):
    records=[]
    for entry,row in store.quests_for(item_id):
        variants=[reward['caption'] for reward in quest_rewards(row) if reward.get('type')=='item' and reward.get('id')==item_id]
        caption='Quest'+(f' · Lv. {entry.level}' if entry.level else '')
        if len(set(variants))==1 and variants[0]!='Reward':caption+=' · '+variants[0].replace('Random reward · ','').replace('Choose one','Choice reward')
        records.append(dict(key=('quest',entry.id),target=entry.key,name=entry.name,subtitle=caption,icon=entry.icon,tip=entry.name+'\n'+caption))
    return records
