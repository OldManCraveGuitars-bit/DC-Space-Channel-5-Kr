"""Verify the actual packaged patcher roundtrip and assemble v0.81 archives."""
import json
from pathlib import Path
import shutil
import sys
from prepare_public_v081 import ROOT,PUBLIC,RELEASE,PATCH,ORIGINAL,sha,write_json
from finalize_public_v08 import archive

NOTES='''# v0.81 — 판정 설정 VMU 저장 / 최신 옵션 PNG

## 이번 변경

- SET JUDGMENT의 선택값을 VMU에 자동 저장하고 게임 완전 종료 후 새 부팅에도 자동 복원합니다. LOAD 메뉴에서 진행 세이브를 불러오지 않아도 설정을 읽습니다.
- 설정 파일이 없으면 기본값 **1**입니다. 2~6은 원래 성공 판정의 앞뒤에 각각 **0.02 / 0.04 / 0.06 / 0.08 / 0.10초**를 추가합니다. 판정 단계와 버튼 조작은 v0.8과 같습니다.
- 사용자 최신 **SET_JUDGMENT_2.png(429×24)**를 재적용했습니다. 크기·간격·투명 영역을 보존하며 ARGB4444 정밀도로만 변환합니다. 선택하지 않은 숫자는 기존처럼 반투명입니다.
- Workbench **v9**에 새 VMU 코드와 최신 PNG를 포함했습니다. ROM 내부 기능이므로 개조 에뮬레이터나 코어가 필요하지 않습니다.

## 저장 방법과 일본판 세이브 호환

옵션에서 숫자를 바꾸면 마지막 변경 후 **90프레임(60fps 기준 약 1.5초)**을 기다려 저장을 시작합니다. **변경 후 약 3초 기다린 뒤 게임을 종료**해 주세요. 실행 속도가 낮으면 더 오래 걸릴 수 있습니다.

게임이 사용하는 VMU에 **SC5KR_JUDGE**라는 별도 설정 파일을 만들며 **2블록**을 사용합니다. **일본판 진행 세이브와 호환**됩니다. 기존 SPACECH5_001 등의 파일과 저장 형식은 그대로이며, 일본판에서는 원래 판정을 사용합니다. 에뮬레이터에서 세이브를 공유하려면 같은 가상 VMU를 지정하세요.

VMU가 없거나 여유 공간이 부족하면 실행 중 선택값은 유지되지만 다음 부팅에 저장되지 않습니다. VMU에 여유 공간을 확보한 뒤 다시 설정해 주세요.

## 업데이트와 배포 파일

v0.81 Patch ZIP을 새 폴더에 풀고 **원본 일본판 5개 BIN**을 선택해 **SC5KoreanPatcher_v0.81.exe**로 다시 패치합니다. v0.7/v0.8로 패치한 BIN/CHD는 원본 대신 사용할 수 없습니다. 기존 진행 세이브는 그대로 사용합니다.

- **DC-Space-Channel-5-Kr-v0.81-Patch.zip**: 차이 패치·Windows 적용기·GDI/CHD 생성 도구.
- **DC-Space-Channel-5-Kr-v0.81-Workbench.zip**: 독립 실행형 편집기 v9·최신 편집 데이터·소스.
- **DC-Space-Channel-5-Kr-v0.81-Text.csv**: 기존 861행 원문/번역/시간 대조 목록.
- **SHA256SUMS.txt**: 배포 파일 체크섬.

원본 게임과 BIOS는 포함하지 않습니다. 이번 릴리스에는 새 스크린샷을 추가하지 않았습니다.

## 확인한 범위

- 개조하지 않은 공식 Flycast libretro 코어에서 기본 1 → 6 저장 → 프로세스 완전 종료 → 새 부팅 시 6 자동 복원 → 2로 변경/재저장 확인.
- 기존 일본판 진행 파일 6개의 내용과 할당 블록 보존, 새 설정 파일 2블록·정상 VMS CRC 확인.
- VMU 미연결·공간 부족에서 저장 실패가 진행 파일을 바꾸지 않고 실행 중 설정을 유지하는지 확인.
- 최신 PNG 전체 표시 픽셀 대조, 최종 GDI 파일 읽기/섹터 EDC/ECC와 CHD 무결성 확인.
- 배포 Windows 실행 파일로 원본 일본판을 실제 패치한 뒤 5개 트랙과 CHD 해시 일치 확인.

v0.8의 판정 경계 100개·연속 노트 6개 검증 기록은 그대로 유지합니다. 이번 버전은 저장 기능과 최신 이미지 적용을 검증했으며 모든 판정 패턴을 새로 검사한 것은 아닙니다. **물리 Dreamcast/ODE, 전체 Normal/Extra 분기, 남은 음성 청취·번역 검수는 미완료**입니다. 기존 내장 자막 244개 미디어/546구간을 이어받았습니다.

[사용법과 전체 작업 내역](https://github.com/OldManCraveGuitars-bit/DC-Space-Channel-5-Kr/blob/v0.81/README.md) · [변경 기록](https://github.com/OldManCraveGuitars-bit/DC-Space-Channel-5-Kr/blob/v0.81/CHANGELOG.md) · [VMU 검증 기록](https://github.com/OldManCraveGuitars-bit/DC-Space-Channel-5-Kr/blob/v0.81/docs/verification/judgment-vmu.json)

KOREAN LOCALIZATION BY **GIKAKNO**
'''

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    proof=json.loads((RELEASE/'patch-roundtrip/patch-result.json').read_text('utf-8'))
    manifest=json.loads((PATCH/'manifest.json').read_text('utf-8'))
    assert proof['success'] and proof['chd_sha256']==manifest['chd_sha256']
    assert len(proof['tracks'])==5
    for item,track in zip(proof['tracks'],manifest['tracks']):
        assert item['sha256']==track['output_sha256']
        assert sha(ORIGINAL/track['source_name'])==track['source_sha256']
    proof.update(patcher_exe_sha256=sha(PATCH/'SC5KoreanPatcher_v0.81.exe'),
                 test_method='Packaged v0.81 Windows executable CLI, original five BIN tracks, complete GDI/CHD generation',
                 original_hashes_rechecked_after_apply=True)
    write_json(PUBLIC/'docs/verification/patch-roundtrip.json',proof)
    from finalize_public_v07 import licenses_and_project
    licenses_and_project()
    for name in ('prepare_public_v081.py','document_public_v081.py','finalize_public_v081.py'):
        shutil.copy2(ROOT/'tools'/name,PUBLIC/'tools'/name)
    for name in ('README.md','CHANGELOG.md','THIRD_PARTY_NOTICES.md'):shutil.copy2(PUBLIC/name,PATCH/name)
    shutil.copytree(PUBLIC/'docs',PATCH/'docs')
    shutil.copy2(PUBLIC/'data/localization_export.csv',PATCH/'DC-Space-Channel-5-Kr-v0.81-Text.csv')
    bundle=RELEASE/'DC-Space-Channel-5-Kr-v0.81-Workbench';bundle.mkdir(exist_ok=False)
    for folder in ('assets','data','native','sc5','tools','docs'):shutil.copytree(PUBLIC/folder,bundle/folder)
    for name in ('README.md','CHANGELOG.md','THIRD_PARTY_NOTICES.md','requirements.txt','run_workbench.cmd'):
        shutil.copy2(PUBLIC/name,bundle/name)
    editor=ROOT/'SC5KoreanWorkbench_v9.exe';shutil.copy2(editor,bundle/editor.name)
    files=[]
    for folder in (PATCH,bundle):
        target=RELEASE/(folder.name+'.zip');archive(folder,target);files.append(target)
    csv=RELEASE/'DC-Space-Channel-5-Kr-v0.81-Text.csv';shutil.copy2(PUBLIC/'data/localization_export.csv',csv);files.append(csv)
    sums=RELEASE/'SHA256SUMS.txt';sums.write_text(''.join(f'{sha(p)}  {p.name}\n' for p in files),'ascii')
    (RELEASE/'release-notes.md').write_text(NOTES,'utf-8')
    report={'success':True,'repo':'https://github.com/OldManCraveGuitars-bit/DC-Space-Channel-5-Kr',
            'tag':'v0.81','chd_sha256':manifest['chd_sha256'],'packaged_patcher_roundtrip':True,
            'original_files_preserved':True,'VMU_setting_persistence':True,'new_release_screenshots':0,
            'files':[{'name':p.name,'size':p.stat().st_size,'sha256':sha(p)} for p in files+[sums]]}
    write_json(RELEASE/'publication.json',report)
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
