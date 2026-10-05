"""Add v0.81 text only, retaining all previous release screenshots."""
import json
from prepare_public_v081 import ROOT,PUBLIC,OLD,PATCH,sha

UPDATE='''## v0.81 업데이트 — VMU 판정 설정 저장

- **SET JUDGMENT 선택값을 VMU에 자동 저장**하고, 게임을 완전히 종료한 뒤 다시 부팅해도 자동으로 읽습니다. LOAD 메뉴를 사용할 필요는 없습니다.
- 저장된 설정이 없으면 기본값은 **1**입니다. 같은 게임 실행 중에는 옵션을 나가거나 새 게임을 시작해도 선택값을 유지합니다.
- 숫자 변경을 멈춘 뒤 약 1.5초(90프레임) 후 저장을 시작합니다. **마지막 변경 후 3초 정도 기다린 뒤 게임을 종료**해 주세요. 프레임 속도가 낮으면 저장까지 더 오래 걸릴 수 있습니다.
- 설정은 게임이 사용하는 VMU의 별도 파일 **`SC5KR_JUDGE`**, **2블록**에 저장합니다. VMU가 없거나 공간이 부족하면 실행 중의 선택값은 유지되지만 다음 부팅에는 저장되지 않습니다.
- **일본판 진행 세이브와 호환됩니다.** 기존 `SPACECH5_001` 등의 파일과 진행 저장 형식을 바꾸지 않습니다. 일본판에서도 기존 진행 세이브를 사용할 수 있으며, 일본판 자체에는 판정 완화가 적용되지 않습니다. 에뮬레이터에서는 같은 가상 VMU를 지정해야 기존 세이브를 공유할 수 있습니다.
- 사용자가 다시 수정한 **SET_JUDGMENT_2.png(429×24)**를 적용했습니다. 크기·간격·투명 영역을 보존하며 ARGB4444 색상 정밀도로만 변환합니다.
- 게임의 원래 VMU 드라이버로 구현했습니다. 설정 저장에도 에뮬레이터나 코어 개조가 필요하지 않습니다. Workbench **v9**에 해당 코드와 최신 PNG를 포함했습니다.

### v0.81 검증

개조하지 않은 공식 Flycast libretro 코어에서 기본 1 → 6 저장 → 프로세스 완전 종료 → 새 부팅 시 6 자동 복원 → 2로 변경·재저장을 확인했습니다. 기존 일본판 진행 파일 6개의 내용과 할당 블록이 그대로이며, 새 설정 파일은 2블록과 정상 VMS CRC를 사용하는 것을 확인했습니다. VMU 미연결·공간 부족 상황도 별도 복사본에서 확인했습니다. 기록은 [VMU 검증 자료](docs/verification/judgment-vmu.json)에 있습니다.

새 PNG의 모든 표시 픽셀, 최종 GDI 파일·섹터 EDC/ECC와 CHD 무결성을 검사했으며, v0.81 배포 적용기로 원본 일본판에서 만든 결과도 5개 트랙과 CHD 해시가 일치합니다. v0.8의 106개 판정 규칙 검사는 이전 검증 기록이며, 이번 버전의 추가 검증은 저장 기능과 최신 이미지 적용입니다. 물리 Dreamcast/ODE 시험과 기존 번역 검수의 남은 범위는 계속 확인이 필요합니다.

이번 업데이트에는 새 스크린샷을 추가하지 않았습니다. 아래 옵션 이미지는 v0.8 당시의 화면입니다.

'''

CHANGE='''## v0.81 — 2026-10-06

### VMU 판정 설정 저장

- SET JUDGMENT 선택값 자동 저장·새 부팅 시 자동 읽기. 저장값이 없으면 기본 1.
- 기존 일본판 VMU 진행 파일과 저장 형식 유지; 별도 SC5KR_JUDGE 파일 2블록 사용.
- 마지막 변경 이후 90프레임 대기 후 원래 게임의 비동기 VMU 드라이버로 기록. 저장 중 진행 파일 콜백은 원래 동작을 유지.
- 표준 VMS 헤더·아이콘·CRC와 값 범위 확인. VMU 미연결/공간 부족 시 실행 중 선택값은 유지.
- 옵션 변경 후 약 3초 기다린 뒤 종료하도록 사용 안내 추가.

### 최신 PNG와 배포

- 사용자 수정 SET_JUDGMENT_2.png(429×24, SHA-256 721a3276eb747ea74510b5c2b41114a258d556cc36814dace2280f673744d196) 재적용.
- 크기·간격·투명 영역 보존, 비압축 ARGB4444 표시와 숫자별 선택 효과 유지.
- Workbench v9에 VMU 코드와 최신 이미지 적용 기능 포함.
- 패치 적용기 v0.81·차이 패치·편집기·861행 CSV·체크섬 갱신.
- 이전 스크린샷 유지, 새 스크린샷 추가 없음. 릴리스 설명은 이번 변경 내용으로 구성.

### 검증

- 공식 Flycast 코어에서 설정 6 저장·완전 종료·새 부팅 자동 복원·2로 변경/재저장 확인.
- 기존 일본판 진행 파일 6개의 내용과 할당 블록 보존; 설정 파일 2블록·정상 VMS CRC 확인.
- VMU 미연결과 여유 공간 부족 처리 확인.
- PNG 전체 픽셀 양자화 대조·GDI 파일 읽기/섹터 EDC/ECC·CHD 무결성 통과.
- 배포 실행 파일의 원본 일본판 → 트랙 5개/GDI/CHD 결과 일치 확인.
- v0.8 판정 규칙 106개 검증 기록 유지. 물리 Dreamcast/ODE와 전체 Normal/Extra 분기 검수는 미완료.

'''

def main():
    p=PUBLIC/'README.md';text=p.read_text('utf-8')
    assert text.startswith('![스페이스 채널 5 한글 메인 화면]')
    text=text.replace('# DC Space Channel 5 한국어 패치 v0.8','# DC Space Channel 5 한국어 패치 v0.81')
    text=text.replace('[v0.8 다운로드]','[v0.81 다운로드]').replace('/releases/tag/v0.8)','/releases/tag/v0.81)')
    text=text.replace('v0.8은 현재까지','v0.81은 현재까지')
    text=text.replace('## v0.8 업데이트 — SET JUDGMENT',UPDATE+'## v0.8에서 추가한 SET JUDGMENT')
    text=text.replace('기본값은 **1**입니다. 같은 게임 실행 중에는 옵션을 나갔다 들어오거나 새 게임을 시작해도 선택값을 유지합니다. **게임을 완전히 종료하고 새로 부팅하면 1로 돌아갑니다.** 이 설정을 VMU에 저장하는 기능은 없습니다.',
                      '저장된 설정이 없을 때 기본값은 **1**입니다. v0.81에서는 선택값을 VMU에 자동 저장하고 새 부팅 시 복원합니다. 자세한 저장 조건과 일본판 세이브 호환 안내는 위 v0.81 항목을 참고하세요.')
    text=text.replace('Workbench v8','Workbench v9').replace('SC5KoreanWorkbench_v8.exe','SC5KoreanWorkbench_v9.exe')
    text=text.replace('편집기 v8','편집기 v9').replace('v8의 전체 ROM','v9의 전체 ROM')
    text=text.replace('편집기 v8와','편집기 v9와')
    text=text.replace('사용자가 제공한 제작 PNG입니다. 위 세 장은 실제 게임 화면이며, 아래는 편집 자료입니다.',
                      '아래 제작 PNG와 위 세 장의 옵션 화면은 v0.8 당시 자료입니다. v0.81의 최신 수정 파일은 `assets/image-edits/SET_JUDGMENT_2.png`에 있습니다.')
    old='### v0.7 사용자가 업데이트할 때\n\nv0.8 Patch ZIP을 새 폴더에 풀고 **원본 일본판 5개 BIN에서 다시 적용**합니다. v0.7으로 패치한 CHD/BIN은 원본 선택 대상으로 사용할 수 없습니다.'
    new='### 기존 버전에서 업데이트할 때\n\nv0.81 Patch ZIP을 새 폴더에 풀고 **원본 일본판 5개 BIN에서 다시 적용**합니다. v0.7/v0.8로 패치한 CHD/BIN은 원본 선택 대상으로 사용할 수 없습니다.'
    assert old in text;text=text.replace(old,new)
    text=text.replace('DC-Space-Channel-5-Kr-v0.8-','DC-Space-Channel-5-Kr-v0.81-')
    text=text.replace('SC5KoreanPatcher_v0.8.exe','SC5KoreanPatcher_v0.81.exe')
    text=text.replace('v0.8 배포 실행 파일을 사용한 실제 적용 결과','v0.81 배포 실행 파일을 사용한 실제 적용 결과')
    manifest=json.loads((PATCH/'manifest.json').read_text('utf-8'))
    old_manifest=json.loads((OLD/'manifest.json').read_text('utf-8'))
    text=text.replace(old_manifest['chd_sha256'],manifest['chd_sha256'])
    text=text.replace(old_manifest['tracks'][4]['output_sha256'],manifest['tracks'][4]['output_sha256'])
    text=text.replace('bfac6a635230ed2ee6619bc13bca21b5a7561e3b95ae7e41ab398f099d4eefa3',sha(ROOT/'SC5KoreanWorkbench_v9.exe'))
    p.write_text(text,'utf-8')
    p=PUBLIC/'CHANGELOG.md';text=p.read_text('utf-8');p.write_text(text.replace('# 변경 기록\n\n','# 변경 기록\n\n'+CHANGE,1),'utf-8')
    p=PUBLIC/'docs/DEVELOPMENT.md';text=p.read_text('utf-8').replace('SC5KoreanWorkbench_v8.exe','SC5KoreanWorkbench_v9.exe').replace('공개한 v8 실행 파일','공개한 v9 실행 파일')
    text=text.replace('판정 단계는 실행 파일의 세션 변수입니다. 별도 설정 파일이나 VMU 변경이 필요하지 않습니다.',
                      'v0.81은 `native/judgment_vmu.c`에서 원래 게임의 비동기 VMU 드라이버로 `SC5KR_JUDGE` 설정 파일 2블록을 기록하고 부팅 시 읽습니다. 기존 `SPACECH5_001` 등의 진행 파일 형식은 바꾸지 않습니다. 숫자 변경 후 90프레임 동안 추가 변경이 없으면 저장을 시작합니다.')
    text+='\n## v0.81 공개 준비\n\n`tools/prepare_public_v081.py`, `document_public_v081.py`, `finalize_public_v081.py`는 검증된 로컬 디스크를 사용하는 배포 준비 기록입니다. `docs/verification/judgment-vmu.json`에는 공식 코어의 완전 종료/새 부팅, 일본판 진행 파일 보존, VMU 미연결/공간 부족 검증을 기록합니다. 새 스크린샷은 추가하지 않았습니다.\n'
    p.write_text(text,'utf-8')

if __name__=='__main__':main()
