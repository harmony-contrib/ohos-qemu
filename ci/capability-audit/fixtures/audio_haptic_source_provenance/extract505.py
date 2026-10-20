"""Lexical extraction of actual C++ definitions for isolated dependency checks."""
import re
def method(text,owner,name):
 match=re.search(r'^(?:void|int32_t|size_t|Status) '+re.escape(owner)+'::'+re.escape(name)+r'\([^\n]*\)\n\{',text,re.M)
 if not match:raise ValueError('actual method missing: '+owner+'::'+name)
 begin=match.start();position=match.end()-1;depth=0;mode='code'
 while position<len(text):
  c=text[position];pair=text[position:position+2]
  if mode=='line':
   if c=='\n':mode='code'
  elif mode=='block':
   if pair=='*/':mode='code';position+=1
  elif mode in ('"',"'"):
   if c=='\\':position+=1
   elif c==mode:mode='code'
  elif pair=='//':mode='line';position+=1
  elif pair=='/*':mode='block';position+=1
  elif c in ('"',"'"):mode=c
  elif c=='{':depth+=1
  elif c=='}':
   depth-=1
   if depth==0:return text[begin:position+1]
  position+=1
 raise ValueError('unclosed actual method')
