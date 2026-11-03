"""Build one Jellyfin catalog per major from reviewed plugin definitions and receipts.
python scripts/build-manifests.py          # generate
python scripts/build-manifests.py --check  # validate without modifying files
"""
import argparse
import datetime
import json
from pathlib import Path
import re
import uuid
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def require(value,message):
    if not value:raise ValueError(message)

def https(value):
    parsed=urlparse(value)
    return parsed.scheme=='https' and bool(parsed.hostname) and not parsed.username and not parsed.password

def build():
    catalogs={};guids=set()
    for path in sorted((ROOT/'plugins').glob('*.json')):
        plugin=read(path);slug=path.stem
        require(bool(re.fullmatch('[a-z0-9-]+',slug)),'Invalid plugin slug')
        uuid.UUID(plugin['guid']);require(plugin['guid'] not in guids,'Duplicate plugin GUID');guids.add(plugin['guid'])
        for key in ['name','owner','overview','description','category']:
            require(isinstance(plugin[key],str) and plugin[key].strip(),'Empty '+key)
        require(https(plugin['imageUrl']),'Image must have a public HTTPS URL')
        image=ROOT/'assets'/slug/'thumbnail.png';require(image.is_file(),'Missing thumbnail')
        require(image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'),'Invalid PNG thumbnail')
        groups={};seen=set()
        for receipt_path in (ROOT/'releases'/slug).glob('*.json'):
            receipt=read(receipt_path);version=receipt['version'];target=receipt['targetAbi']
            require(bool(re.fullmatch(r'\d+\.\d+\.\d+\.\d+',version)),'Jellyfin version must be numeric')
            require(version not in seen,'Duplicate release version');seen.add(version)
            require(bool(re.fullmatch(r'\d+\.\d+\.\d+\.\d+',target)) and int(target.split('.')[0])>0,'Invalid ABI')
            require(bool(re.fullmatch('[a-f0-9]{32}',receipt['checksum'])),'Invalid MD5')
            require(bool(re.fullmatch('[a-f0-9]{64}',receipt['sha256'])),'Invalid SHA256')
            require(https(receipt['sourceUrl']) and urlparse(receipt['sourceUrl']).path.endswith('/'+receipt['filename']),'Invalid release URL')
            require(bool(re.fullmatch('[a-f0-9]{40}',receipt['sourceCommit'])),'Release must identify its source commit')
            require('beta' in receipt['releaseVersion'] or receipt.get('stage')=='stable','Release stage missing')
            datetime.datetime.fromisoformat(receipt['timestamp'].replace('Z','+00:00'))
            groups.setdefault(target.split('.')[0],[]).append({key:receipt[key] for key in ['version','changelog','targetAbi','sourceUrl','checksum','timestamp']})
        require(groups,'No release receipts for '+slug)
        for major,versions in groups.items():
            catalogs.setdefault(major,[]).append({**plugin,'versions':sorted(versions,key=lambda v:tuple(map(int,v['version'].split('.'))),reverse=True)})
    require(catalogs,'No plugin definitions found')
    return {ROOT/major/'manifest.json':json.dumps(plugins,ensure_ascii=False,indent=2)+'\n' for major,plugins in catalogs.items()}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    manifests=build()
    for path,content in manifests.items():
        if args.check:require(path.exists() and path.read_text(encoding='utf-8')==content,'Manifest is stale: '+str(path.relative_to(ROOT)))
        else:path.parent.mkdir(exist_ok=True);path.write_text(content,encoding='utf-8')
    require(set(ROOT.glob('[0-9]*/manifest.json'))==set(manifests),'Unexpected version catalog')
    print('Validated '+str(len(manifests))+' version catalog(s).')

if __name__=='__main__':main()
