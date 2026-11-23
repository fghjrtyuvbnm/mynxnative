"""Reorder authenticated original records by shader key, never by old indices."""
import hashlib,struct
from pathlib import Path

def rows(text):
 return [line.split('\t',4) for line in text.splitlines() if line and not line.startswith(('#','package\t'))]

def remap(shader,previous,current):
 old,new=rows(previous),rows(current)
 assert {(r[2],r[3]) for r in old}=={(r[2],r[3]) for r in new}
 packages={name:(shader/'pkg'/name).read_bytes().split(b'BTCDBTCD')[1:] for name in {r[0] for r in old}}
 records={}
 for name,index,stage,key,_ in old:
  raw=packages[name][int(index)]
  ctl_size,code_size=struct.unpack_from('<2I',raw,0x20)
  code,ctl=raw[0x30:0x30+code_size],raw[0x30+code_size:]
  assert len(ctl)==ctl_size
  # The split table is authenticated; validate its executable record with the scanner too.
  import shader_split
  assert shader_split.skey(ctl,code)==key
  record=b'BTCDBTCD'+bytes.fromhex(key)+raw[8:]
  if key in records:assert records[key]==record
  records[key]=record
 groups={}
 for name,index,stage,key,_ in new:groups.setdefault(name,{})[int(index)]=records[key]
 for name,entries in groups.items():
  assert sorted(entries)==list(range(len(entries)))
  (shader/'pkg'/name).write_bytes(b''.join(entries[i] for i in range(len(entries))))
 print('Validated and reordered',len(records),'original shader records',flush=True)

