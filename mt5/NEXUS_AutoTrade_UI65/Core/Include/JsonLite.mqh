#ifndef NEXUS_JSON_LITE_MQH
#define NEXUS_JSON_LITE_MQH

string NexusTrim(string value)
  {
   StringTrimLeft(value);
   StringTrimRight(value);
   return value;
  }

int NexusSkipWs(const string s,int p)
  {
   const int n=StringLen(s);
   while(p<n)
     {
      ushort c=StringGetCharacter(s,p);
      if(c!=' ' && c!='\t' && c!='\r' && c!='\n') break;
      p++;
     }
   return p;
  }

int NexusFindKeyValueStart(const string json,const string key)
  {
   // Resolve only keys belonging to the current/root object. A plain
   // StringFind can accidentally return a nested key with the same name.
   string needle="\""+key+"\"";
   int n=StringLen(json),depth=0; bool in_string=false,esc=false;
   for(int i=0;i<n;i++)
     {
      ushort c=StringGetCharacter(json,i);
      if(in_string)
        {
         if(esc){esc=false;continue;}
         if(c=='\\'){esc=true;continue;}
         if(c=='\"')in_string=false;
         continue;
        }
      if(c=='\"')
        {
         if(depth==1 && StringSubstr(json,i,StringLen(needle))==needle)
           {
            int p=StringFind(json,":",i+StringLen(needle));
            if(p>=0)return NexusSkipWs(json,p+1);
           }
         in_string=true;
         continue;
        }
      if(c=='{')depth++;
      else if(c=='}' && depth>0)depth--;
     }
   return -1;
  }

string NexusJsonString(const string json,const string key,const string def="")
  {
   int p=NexusFindKeyValueStart(json,key);
   if(p<0 || p>=StringLen(json)) return def;
   if(StringSubstr(json,p,4)=="null") return def;
   if(StringGetCharacter(json,p)!='\"')
     {
      int e=p;
      while(e<StringLen(json) && StringGetCharacter(json,e)!=',' && StringGetCharacter(json,e)!='}') e++;
      return NexusTrim(StringSubstr(json,p,e-p));
     }
   p++;
   string out="";
   bool esc=false;
   for(int i=p;i<StringLen(json);i++)
     {
      ushort c=StringGetCharacter(json,i);
      if(esc)
        {
         if(c=='n') out+="\n";
         else if(c=='r') out+="\r";
         else if(c=='t') out+="\t";
         else out+=ShortToString(c);
         esc=false;
         continue;
        }
      if(c=='\\') { esc=true; continue; }
      if(c=='\"') break;
      out+=ShortToString(c);
     }
   return out;
  }

bool NexusJsonIsNull(const string json,const string key)
  {
   int p=NexusFindKeyValueStart(json,key);
   if(p<0) return true;
   return StringSubstr(json,p,4)=="null";
  }

double NexusJsonDouble(const string json,const string key,const double def=0.0)
  {
   int p=NexusFindKeyValueStart(json,key);
   if(p<0 || StringSubstr(json,p,4)=="null") return def;
   int e=p;
   if(StringGetCharacter(json,p)=='\"')
     {
      string v=NexusJsonString(json,key,"");
      if(v=="") return def;
      return StringToDouble(v);
     }
   while(e<StringLen(json) && StringGetCharacter(json,e)!=',' && StringGetCharacter(json,e)!='}' && StringGetCharacter(json,e)!=']') e++;
   string v=NexusTrim(StringSubstr(json,p,e-p));
   if(v=="") return def;
   return StringToDouble(v);
  }

long NexusJsonLong(const string json,const string key,const long def=0)
  {
   return (long)NexusJsonDouble(json,key,(double)def);
  }

bool NexusJsonBool(const string json,const string key,const bool def=false)
  {
   int p=NexusFindKeyValueStart(json,key);
   if(p<0) return def;
   string v=StringSubstr(json,p,5); StringToLower(v);
   if(StringFind(v,"true")==0) return true;
   if(StringFind(v,"false")==0) return false;
   return def;
  }

string NexusJsonObject(const string json,const string key)
  {
   int p=NexusFindKeyValueStart(json,key);
   if(p<0 || p>=StringLen(json) || StringGetCharacter(json,p)!='{') return "";
   int depth=0;
   bool in_string=false,esc=false;
   for(int i=p;i<StringLen(json);i++)
     {
      ushort c=StringGetCharacter(json,i);
      if(in_string)
        {
         if(esc) { esc=false; continue; }
         if(c=='\\') { esc=true; continue; }
         if(c=='\"') in_string=false;
         continue;
        }
      if(c=='\"') { in_string=true; continue; }
      if(c=='{') depth++;
      else if(c=='}')
        {
         depth--;
         if(depth==0) return StringSubstr(json,p,i-p+1);
        }
     }
   return "";
  }

string NexusJsonArray(const string json,const string key)
  {
   int p=NexusFindKeyValueStart(json,key);
   if(p<0 || p>=StringLen(json) || StringGetCharacter(json,p)!='[') return "";
   int depth=0;
   bool in_string=false,esc=false;
   for(int i=p;i<StringLen(json);i++)
     {
      ushort c=StringGetCharacter(json,i);
      if(in_string)
        {
         if(esc) { esc=false; continue; }
         if(c=='\\') { esc=true; continue; }
         if(c=='\"') in_string=false;
         continue;
        }
      if(c=='\"') { in_string=true; continue; }
      if(c=='[') depth++;
      else if(c==']')
        {
         depth--;
         if(depth==0) return StringSubstr(json,p,i-p+1);
        }
     }
   return "";
  }

int NexusSplitObjectArray(const string array_json,string &objects[])
  {
   ArrayResize(objects,0);
   if(StringLen(array_json)<2) return 0;
   int depth=0,start=-1;
   bool in_string=false,esc=false;
   for(int i=0;i<StringLen(array_json);i++)
     {
      ushort c=StringGetCharacter(array_json,i);
      if(in_string)
        {
         if(esc) { esc=false; continue; }
         if(c=='\\') { esc=true; continue; }
         if(c=='\"') in_string=false;
         continue;
        }
      if(c=='\"') { in_string=true; continue; }
      if(c=='{')
        {
         if(depth==0) start=i;
         depth++;
        }
      else if(c=='}')
        {
         depth--;
         if(depth==0 && start>=0)
           {
            int n=ArraySize(objects);
            ArrayResize(objects,n+1);
            objects[n]=StringSubstr(array_json,start,i-start+1);
            start=-1;
           }
        }
     }
   return ArraySize(objects);
  }

string NexusJsonEscape(string value)
  {
   StringReplace(value,"\\","\\\\");
   StringReplace(value,"\"","\\\"");
   StringReplace(value,"\r","\\r");
   StringReplace(value,"\n","\\n");
   return value;
  }

#endif
