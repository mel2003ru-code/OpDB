"""Actual model-generated oracle with independently implemented SQLite aggregates."""
import os
import random
import sqlite3
import tempfile
from opdb import NumericTruthStore


def model_generated_oracle(vals):
    return (0, 0, None, None) if not vals else (len(vals), sum(vals), min(vals), max(vals))


def check(store,path,model):
    con=sqlite3.connect(path)
    try:
        con.create_function('decode8',1,lambda value:int.from_bytes(value,'big',signed=True))
        source={k:int.from_bytes(v,'big',signed=True) for k,v in con.execute('SELECT k,v FROM opdb_source_kv')}
        assert source==model
        for group in ['a','b','missing']:
            vals=[v for k,v in model.items() if k.split('/',1)[0]==group]
            expected=model_generated_oracle(vals)
            sql=con.execute("SELECT count(*),coalesce(sum(decode8(v)),0),min(decode8(v)),max(decode8(v)) FROM opdb_source_kv WHERE substr(k,1,instr(k||'/','/')-1)=?",(group,)).fetchone()
            got=store.numeric_stats(group)
            assert expected==sql,(group,expected,sql)
            assert (got.count,got.total,got.minimum,got.maximum)==expected
    finally:
        con.close()


with tempfile.TemporaryDirectory() as tmp:
    path=os.path.join(tmp,'oracle.sqlite3')
    model={};rng=random.Random(2706353024)
    store=NumericTruthStore(path)
    try:
        # Explicit initial write, overwrite and delete; subsequent bounded random batches.
        batches=[[('put','a/0',3),('put','a/1',-2),('put','b/0',7)],
                 [('put','a/0',-5),('delete','a/1'),('delete','b/0')]]
        batches += [[('put' if rng.random()>.3 else 'delete',rng.choice(['a','b'])+'/'+str(rng.randrange(6)),rng.randint(-10,10)) for _ in range(10)] for _ in range(3)]
        for index,batch in enumerate(batches):
            ops=[]
            for item in batch:
                kind,key=item[:2]
                if kind=='put':
                    value=item[2];model[key]=value;ops.append(('put',key,value.to_bytes(8,'big',signed=True)))
                else:
                    model.pop(key,None);ops.append(('delete',key))
            store.apply(ops)
            check(store,path,model)
            if index==1:
                store.close();store=NumericTruthStore(path)
                check(store,path,model)
    finally:
        store.close()
print('Independent generated-oracle / SQLite / Numeric Lens check passed')
