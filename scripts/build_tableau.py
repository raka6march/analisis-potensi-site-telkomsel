from pathlib import Path
import xml.etree.ElementTree as E
import csv, shutil, copy, uuid, zipfile

import argparse

parser = argparse.ArgumentParser(description='Generate the initial Tableau layout (not the final edited dashboard).')
parser.add_argument('--csv', type=Path, default=Path(__file__).resolve().parents[1]/'tableau/Data/kelas_site_bulanan.csv')
parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1]/'tableau/generated')
args = parser.parse_args()
SRC = args.csv.resolve()
if not SRC.is_file():
    parser.error(f'CSV not found: {SRC}. Extract the release package or pass --csv.')
OUT = args.output.resolve()
OUT.mkdir(parents=True, exist_ok=True)
(OUT/'Data').mkdir(exist_ok=True)
DEST = OUT/'Data/kelas_site_bulanan.csv'
if SRC != DEST.resolve():
    shutil.copy2(SRC, DEST)
with DEST.open() as f: fields=next(csv.reader(f))
def sub(p,tag,**a): return E.SubElement(p,tag,{k.replace('_','-'):str(v) for k,v in a.items()})
def txt(p,tag,s,**a): e=sub(p,tag,**a);e.text=s;return e
def uid(p): sub(p,'simple-id',uuid='{'+str(uuid.uuid4()).upper()+'}')
wb=E.Element('workbook',{'original-version':'18.1','source-build':'2024.3.0 (20243.24.1010.1014)','source-platform':'mac','version':'18.1'})
manifest=sub(wb,'document-format-change-manifest')
for feature in ['SheetIdentifierTracking','WindowsPersistSimpleIdentifiers','ZoneBackgroundTransparency']:
    sub(manifest,feature)
sources=sub(wb,'datasources')
params=sub(sources,'datasource',hasconnection='false',inline='true',name='Parameters',version='18.1')
sub(params,'aliases',enabled='yes')
for name,caption,values in [('Kategori','Pilih Kategori',['Payload','Digital','Games','Video']),('Bulan','Pilih Bulan',['2023-11','2023-12']+[f'2024-{i:02d}' for i in range(1,8)])]:
    c=sub(params,'column',caption=caption,datatype='string',name=f'[{name}]',param_domain_type='list',role='measure',type='nominal',value='"'+values[0]+'"')
    sub(c,'calculation',**{'class':'tableau','formula':'"'+values[0]+'"'})
    mem=sub(c,'members')
    for value in values: sub(mem,'member',value='"'+value+'"')
DS='kp'; ds=sub(sources,'datasource',caption='Potensi Site - hasil KP',inline='true',name=DS,version='18.1')
conn=sub(ds,'connection',**{'class':'textscan','directory':str(OUT/'Data'),'filename':DEST.name,'password':'','server':''})
rel=sub(conn,'relation',name=DEST.name,table='[kelas_site_bulanan#csv]',type='table')
cs=sub(rel,'columns',character_set='UTF-8',header='yes',locale='en_US',separator=',')
sub(ds,'aliases',enabled='yes')
defs={}
for i,f in enumerate(fields):
    dt='string' if f in ['site_id','month'] or f.endswith('_kelas') else 'real'
    sub(cs,'column',datatype=dt,name=f,ordinal=i)
    c=sub(ds,'column',caption=f.replace('_',' ').title(),datatype=dt,name=f'[{f}]',role='dimension' if dt=='string' else 'measure',type='nominal' if dt=='string' else 'quantitative')
    if dt=='real': c.set('default-format','n#,##0.00')
    defs[f]=c
calculations={
 'Kelas':('string','Kelas Terpilih','CASE [Parameters].[Kategori] '+ ' '.join(f'WHEN "{c.title()}" THEN [{c}_kelas]' for c in ['payload','digital','games','video'])+' END'),
 'Nilai':('real','Rata-rata Harian','CASE [Parameters].[Kategori] '+ ' '.join(f'WHEN "{c.title()}" THEN [{c}_user_daily_avg]' for c in ['payload','digital','games','video'])+' END'),
 'BulanAktif':('boolean','Bulan Terpilih','LEFT([month],7) = [Parameters].[Bulan]'),
 'PersenTinggi':('real','Site Kelas Tinggi','COUNTD(IF [Kelas] = "Tinggi" THEN [site_id] END) / COUNTD([site_id])'),
 'Detail':('string','Rata-rata harian | Hari | Cakupan','STR(ROUND([Nilai],2)) + "   |   " + STR(INT([days_observed])) + " hari   |   " + STR(ROUND([calendar_coverage]*100,1)) + "%"')}
for f,(dt,cap,formula) in calculations.items():
    c=sub(ds,'column',caption=cap,datatype=dt,name=f'[{f}]',role='measure' if dt=='real' else 'dimension',type='quantitative' if dt=='real' else 'nominal')
    sub(c,'calculation',**{'class':'tableau','formula':formula})
    if dt=='real': c.set('default-format','p0.0%' if f=='PersenTinggi' else 'n#,##0.00')
    defs[f]=c
style=sub(ds,'style'); rule=sub(style,'style-rule',element='mark'); enc=sub(rule,'encoding',attr='color',field='[none:Kelas:nk]',type='palette')
for label,color in [('Rendah','#94a3b8'),('Sedang','#38bdf8'),('Tinggi','#0f766e')]: txt(sub(enc,'map',to=color),'bucket','"'+label+'"')
works=sub(wb,'worksheets')
instances={}
def inst(field,der='None'):
    prefix={'None':'none','CountD':'ctd','Median':'med','Avg':'avg','User':'usr'}[der]
    typ='nominal' if der=='None' else 'quantitative'
    name=f'[{prefix}:{field}:{"nk" if typ=="nominal" else "qk"}]'
    instances[name]=dict(column=f'[{field}]',derivation=der,name=name,pivot='key',type=typ)
    return f'[{DS}].{name}'
K=inst('Kelas'); V=inst('Nilai','Median'); N=inst('site_id','CountD'); P=inst('PersenTinggi','User'); B=inst('BulanAktif'); S=inst('site_id'); D=inst('Detail')
def deps(parent):
    dep=sub(parent,'datasource-dependencies',datasource=DS)
    for c in defs.values():dep.append(copy.deepcopy(c))
    for attrs in instances.values(): sub(dep,'column-instance',**attrs)
    dep=sub(parent,'datasource-dependencies',datasource='Parameters')
    for c in params.findall('column'):dep.append(copy.deepcopy(c))
def sheet(name,rows='',cols='',mark='Bar',label=None,color=False,big=False):
    w=sub(works,'worksheet',name=name); t=sub(w,'table'); v=sub(t,'view'); ss=sub(v,'datasources')
    sub(ss,'datasource',caption='Potensi Site - hasil KP',name=DS);sub(ss,'datasource',name='Parameters')
    deps(v)
    filt=sub(v,'filter',**{'class':'categorical','column':B});sub(filt,'groupfilter',function='member',level='[none:BulanAktif:nk]',member='true')
    txt(sub(v,'slices'),'column',B);sub(v,'aggregation',value='true')
    st=sub(t,'style');r=sub(st,'style-rule',element='worksheet');sub(r,'format',attr='font-family',value='Arial');sub(r,'format',attr='font-size',value='11')
    pane=sub(sub(t,'panes'),'pane',selection_relaxation_option='selection-relaxation-allow');sub(sub(pane,'view'),'breakdown',value='auto');sub(pane,'mark',**{'class':mark})
    en=sub(pane,'encodings')
    if label:sub(en,'text',column=label)
    if color:sub(en,'color',column=K)
    ps=sub(pane,'style');r=sub(ps,'style-rule',element='mark');sub(r,'format',attr='mark-labels-show',value='true');sub(r,'format',attr='mark-labels-cull',value='true')
    if big:
        sub(r,'format',attr='font-size',value='30');sub(r,'format',attr='font-weight',value='bold');sub(r,'format',attr='color',value='#0f766e');sub(r,'format',attr='text-align',value='center')
    txt(t,'rows',rows);txt(t,'cols',cols);uid(w)
sheet('Jumlah Site',mark='Text',label=N,big=True)
sheet('Median Penggunaan',mark='Text',label=V,big=True)
sheet('Site Kelas Tinggi',mark='Text',label=P,big=True)
sheet('Distribusi Kelas',N,K,label=N,color=True)
sheet('Profil Kelas',V,K,label=V,color=True)
sheet('Detail Site',f'({S} / {K})',mark='Text',label=D,color=True)
dashname='Dashboard Potensi Site'
db=sub(sub(wb,'dashboards'),'dashboard',name=dashname)
st=sub(db,'style');r=sub(st,'style-rule',element='dashboard');sub(r,'format',attr='background-color',value='#f1f5f9')
sub(db,'size',sizing_mode='fixed',maxheight='900',maxwidth='1200',minheight='900',minwidth='1200')
ss=sub(db,'datasources');sub(ss,'datasource',name=DS);sub(ss,'datasource',name='Parameters');deps(db)
zs=sub(db,'zones');base=sub(zs,'zone',h='100000',w='100000',x='0',y='0',id='1',type_v2='layout-basic')
zoneid=1
def zone(x,y,w,h,**attrs):
    global zoneid
    zoneid+=1
    z=sub(base,'zone',id=zoneid,x=round(x/1200*100000),y=round(y/900*100000),w=round(w/1200*100000),h=round(h/900*100000),**attrs)
    return z
def zsstyle(z):
    st=sub(z,'zone-style')
    for a,v in [('background-color','#ffffff'),('border-color','#e2e8f0'),('border-style','solid'),('border-width','1'),('margin','6')]:sub(st,'format',attr=a,value=v)
z=zone(20,12,740,65,type_v2='text');txt(sub(z,'formatted-text'),'run','Analisis Potensi Site',fontsize='26',bold='true',fontcolor='#0f172a')
z=zone(20,66,720,34,type_v2='text');txt(sub(z,'formatted-text'),'run','Payload, Digital, Games, Video | Data historis site-bulan',fontsize='11',fontcolor='#64748b')
for name,x in [('Kategori',800),('Bulan',995)]:zone(x,20,185,65,type_v2='paramctrl',param=f'[Parameters].[{name}]',mode='compact')
for name,x in [('Jumlah Site',20),('Median Penggunaan',415),('Site Kelas Tinggi',810)]:zsstyle(zone(x,108,370,130,name=name))
for name,x in [('Distribusi Kelas',20),('Profil Kelas',610)]:zsstyle(zone(x,254,570,285,name=name))
zsstyle(zone(20,552,1160,263,name='Detail Site'))
z=zone(20,824,1160,65,type_v2='text');txt(sub(z,'formatted-text'),'run','Klik batang kelas untuk memfilter detail site. Nilai detail: rata-rata harian | hari tercatat | cakupan kalender.\nKelas relatif historis; satuan metrik perlu konfirmasi. Games/video sejak 28 Juni 2024 perlu validasi.',fontsize='10',fontcolor='#64748b')
uid(db)
actions=sub(wb,'actions');act=sub(actions,'action',caption='Klik kelas untuk detail',name='[ActionKP]');sub(act,'activation',auto_clear='true',type='on-select');sub(act,'source',dashboard=dashname,type='sheet',worksheet='Distribusi Kelas')
cmd=sub(act,'command',command='tsc:tsl-filter');sub(cmd,'param',name='exclude',value='Distribusi Kelas,Profil Kelas,Jumlah Site,Median Penggunaan,Site Kelas Tinggi');sub(cmd,'param',name='special-fields',value='all');sub(cmd,'param',name='target',value=dashname)
windows=sub(wb,'windows',source_height='30')
for w in works:
    win=sub(windows,'window',**{'class':'worksheet','name':w.get('name')});cards=sub(win,'cards');left=sub(cards,'edge',name='left');strip=sub(left,'strip',size='160')
    for t in ['pages','filters','marks']:sub(strip,'card',type=t)
    top=sub(cards,'edge',name='top')
    for t in ['columns','rows','title']:sub(sub(top,'strip',size='31' if t=='title' else '2147483647'),'card',type=t)
    sub(win,'viewpoint',name=w.get('name'));sub(win.find('viewpoint'),'zoom',type='entire-view' if w.get('name')!='Detail Site' else 'fit-width')
    uid(win)
win=sub(windows,'window',**{'class':'dashboard','name':dashname})
vps=sub(win,'viewpoints')
for w in works:sub(sub(vps,'viewpoint',name=w.get('name')),'zoom',type='entire-view' if w.get('name')!='Detail Site' else 'fit-width')
sub(win,'active',id='-1')
uid(win)
wb.remove(actions)
wb.insert(list(wb).index(works),actions)
E.indent(wb)
path=OUT/'Dashboard_Potensi_Site.twb';E.ElementTree(wb).write(path,encoding='utf-8',xml_declaration=True)
print(path)
