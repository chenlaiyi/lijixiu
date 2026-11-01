"""Read address exports without executing workbooks or collection scripts."""
import csv
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

HEADERS = ['城市','区县','立即修小区编号','小区名称','贝壳小区ID','小区别名','商圈','楼栋名称','贝壳楼栋ID',
    '原始单元名称','入口类型','单元名称','道路门牌原文','道路门牌标准写法','贝壳单元ID','房号','贝壳房屋ID',
    '房屋类型','标准完整地址','同址别名','内部备注','来源名称','来源链接','采集时间','核验状态']
MAX_ROWS = 5000


def read_file(filename,content):
    try:return _read_file(filename,content)
    except (zipfile.BadZipFile,ET.ParseError,StopIteration,IndexError) as exc:
        raise ValueError('文件损坏或不是支持的标准Excel文件，请重新导出后重试') from exc


def _read_file(filename, content):
    if not content or len(content)>15*1024*1024:
        raise ValueError('请选择不超过15MB的地址文件')
    suffix=Path(filename).suffix.lower()
    if suffix=='.csv':
        reader=csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
        if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames):
            raise ValueError('CSV缺少表头或存在重复列名')
        rows=list(reader)
    elif suffix=='.json':
        data=json.loads(content.decode('utf-8-sig'))
        rows=data.get('import_address') if isinstance(data,dict) else data
    elif suffix=='.xlsx':
        rows=read_xlsx(content)
    else:
        raise ValueError('支持 UTF-8 CSV、Excel .xlsx（导入地址工作表）、标准JSON；不支持.xls')
    if not isinstance(rows,list) or not rows or len(rows)>MAX_ROWS or not all(isinstance(r,dict) for r in rows):
        raise ValueError(f'导入地址必须为1至{MAX_ROWS}行记录')
    return rows,hashlib.sha256(content).hexdigest()


def read_xlsx(content):
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if sum(f.file_size for f in archive.infolist())>60*1024*1024:
            raise ValueError('Excel解压后过大，请拆分文件')
        shared=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared=[''.join(e.itertext()) for e in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si',ns)]
        sheets=ET.fromstring(archive.read('xl/workbook.xml')).findall('s:sheets/s:sheet',ns)
        sheet=next((s for s in sheets if s.get('name')=='导入地址'),None)
        if sheet is None:raise ValueError('Excel必须包含名为“导入地址”的工作表')
        rid=sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        rels=ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target=next(r.get('Target') for r in rels if r.get('Id')==rid)
        name=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        records=[]
        for row in ET.fromstring(archive.read(name)).findall('s:sheetData/s:row',ns):
            values={}
            for cell in row:
                ref=cell.get('r','');letters=re.match('[A-Z]+',ref)
                if not letters:continue
                col=0
                for c in letters[0]:col=col*26+ord(c)-64
                if col>100:raise ValueError('Excel列数过多')
                if cell.find('s:f',ns) is not None:raise ValueError(f'{ref}含公式，请粘贴为文本值后导入')
                kind=cell.get('t');value=cell.findtext('s:v',default='',namespaces=ns)
                if kind=='inlineStr':value=''.join(cell.find('s:is',ns).itertext()) if cell.find('s:is',ns) is not None else ''
                elif kind=='s':value=shared[int(value)]
                values[col-1]=value
            if values:records.append(values)
            if len(records)>MAX_ROWS+1:raise ValueError('Excel记录超过5000行')
        if not records:raise ValueError('Excel为空')
        header=records[0];names=[header.get(i,'') for i in range(max(header)+1)]
        if len(set(names))!=len(names) or not all(names):raise ValueError('Excel表头含空列或重复名称')
        return [{key:r.get(i,'') for i,key in enumerate(names)} for r in records[1:] if any(r.values())]


def template_csv():
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=HEADERS)
    writer.writeheader()
    writer.writerow({'城市':'厦门市','区县':'海沧区','立即修小区编号':'示例小区编号（请替换）','小区名称':'示例小区（请替换）',
        '楼栋名称':'S6号楼','原始单元名称':'示例路28','入口类型':'道路门牌','道路门牌标准写法':'示例路28号',
        '房号':'101','房屋类型':'住宅','核验状态':'来源采集，未实地核验'})
    return stream.getvalue().encode('utf-8-sig')

