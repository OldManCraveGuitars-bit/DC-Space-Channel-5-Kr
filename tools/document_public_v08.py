"""Write v0.8 user documentation while retaining the v0.7 history."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PUBLIC=Path(r'C:\CODEX\DC-Space-Channel-5-Kr')

NEW=r'''## v0.8 업데이트 — SET JUDGMENT

입력 타이밍에 여유를 주는 **판정 완화 옵션**을 게임 내부에 추가했습니다. OPTIONS의 기존 네 항목 아래에서 `SET JUDGMENT 1 2 3 4 5 6`을 선택할 수 있습니다. 패치한 디스크 하나에 메뉴·그림·판정 코드가 들어 있습니다.

### 판정 단계

| 선택 | 원래 성공 판정의 앞쪽에 추가 | 원래 성공 판정의 뒤쪽에 추가 |
| --- | --- | --- |
| **1** | 0초 — 원래 판정 | 0초 — 원래 판정 |
| **2** | 0.02초 / 20ms | 0.02초 / 20ms |
| **3** | 0.04초 / 40ms | 0.04초 / 40ms |
| **4** | 0.06초 / 60ms | 0.06초 / 60ms |
| **5** | 0.08초 / 80ms | 0.08초 / 80ms |
| **6** | **0.10초 / 100ms** | **0.10초 / 100ms** |

표의 값은 원래 판정에 더하는 시간입니다. 원래 판정 폭 자체는 곡의 템포와 노트 배치에 따라 달라집니다. 현재 템포를 읽어 초 단위의 추가 시간을 게임의 박자 단위로 환산합니다. 방향·A/B의 일치 여부는 게임의 원래 판정 루틴을 사용합니다.

### 조작과 저장

1. 메인 메뉴에서 **OPTIONS**로 들어갑니다.
2. 위/아래로 맨 아래 **SET JUDGMENT** 줄을 선택합니다. 맨 위에서 위를 눌러도 이 줄로 이동합니다.
3. **A / START / 오른쪽**: 다음 단계. **6 → 1**로 순환합니다.
4. **왼쪽**: 이전 단계. **1 → 6**으로 순환합니다.
5. 선택한 숫자는 선명하게, 나머지는 **50% 반투명**으로 표시됩니다. 선택 중인 줄은 기존 OPTIONS처럼 노란색으로 강조됩니다.

기본값은 **1**입니다. 같은 게임 실행 중에는 옵션을 나갔다 들어오거나 새 게임을 시작해도 선택값을 유지합니다. **게임을 완전히 종료하고 새로 부팅하면 1로 돌아갑니다.** 이 설정을 VMU에 저장하는 기능은 없습니다.

### 실제 게임 화면

아래 옵션 화면은 **최종 v0.8 디스크를 개조하지 않은 Flycast libretro 코어로 실행한 캡처**입니다. 외부 자막이나 코어 메모리 쓰기를 사용하지 않았습니다.

**기본 1단계 — 기존 항목 아래에 새 옵션 추가**

![v0.8 SET JUDGMENT 기본값 1](docs/screenshots/11-judgment-default.png)

**2단계 선택 — 선택 숫자와 반투명 숫자 구분**

![v0.8 SET JUDGMENT 2단계 선택](docs/screenshots/12-judgment-level2.png)

**6단계 선택 — 앞뒤 최대 0.10초 추가**

![v0.8 SET JUDGMENT 6단계 선택](docs/screenshots/13-judgment-level6.png)

### 글씨·숫자 디자인 수정

- 기존 옵션의 기울기·테두리·분홍/흰색 계열에 맞춰 새 줄을 제작했습니다.
- 숫자 모양, 문구의 위아래 가장자리, JUDGMENT 글자 겹침과 마지막 T 끝부분을 정리한 뒤 사용자가 직접 수정한 최종 PNG를 적용했습니다.
- **SET_JUDGMENT_2.png, 429×24**의 크기·위치·투명 영역을 보존합니다. 다시 그리거나 크기를 바꾸지 않습니다.
- 새 줄은 VQ 압축 없이 ARGB4444 색상 도형으로 표시합니다. 게임의 채널당 4비트 색상·알파 정밀도에 맞춘 양자화만 적용합니다.
- 레이블과 여섯 숫자를 별도로 표시해 선택 숫자의 반투명 효과를 유지합니다.
- Workbench v8과 소스 빌더도 `data/judgment_artwork.json`에 지정한 PNG를 사용합니다. 다음 ROM 생성 때 자동 생성 글씨로 되돌아가지 않습니다.

사용자가 제공한 제작 PNG입니다. 위 세 장은 실제 게임 화면이며, 아래는 편집 자료입니다.

![사용자 수정 SET JUDGMENT PNG](docs/screenshots/15-judgment-user-png.png)

### v0.8 검증 범위

- 두 플레이어 판정 루틴, 두 템포, 1~6단계의 앞/뒤 경계와 잘못된 버튼 입력을 포함한 **100개 검사**를 원래 SH-4 판정 루틴으로 확인했습니다.
- 판정 범위가 겹칠 때 이미 처리한 노트에서 다음 노트로 넘어가는 **6개 연속 노트 검사**를 확인했습니다. 이 106개 검사는 최종 PNG 수정 전 빌드에서 수행했고, 이후 변경은 그림 표시와 PNG 가져오기입니다.
- 최종 v0.8 디스크의 기본값 1, 선택 2/6, 반투명 표시와 메뉴 진입을 공식 코어에서 확인했습니다.
- 사용자 PNG의 모든 표시 픽셀이 ARGB4444 양자화 결과와 일치하는지 검사했습니다.
- 최종 GDI의 실행 파일·COMMON 이미지·사운드 드라이버·음원 파일 읽기 결과와 섹터 EDC/ECC, CHD 무결성을 확인했습니다.
- 배포 `.exe`로 원본 일본판을 실제 패치해 결과 트랙 5개와 CHD가 기준 빌드와 일치하는지 확인합니다. 근거는 [배포 패치 검증](docs/verification/patch-roundtrip.json)에 보존합니다.

물리 Dreamcast/ODE, 모든 빠른 연타·홀드 조합 및 Normal/Extra 전체 플레이 분기는 추가 검증 대상입니다. 기존 음성 청취·번역 검수의 남은 항목도 아래에 유지합니다.

### v0.7 사용자가 업데이트할 때

v0.8 Patch ZIP을 새 폴더에 풀고 **원본 일본판 5개 BIN에서 다시 적용**합니다. v0.7으로 패치한 CHD/BIN은 원본 선택 대상으로 사용할 수 없습니다. 새 결과 폴더에 생성한 CHD 또는 GDI/BIN으로 게임을 실행합니다.

'''

CHANGE=r'''## v0.8 — 2026-10-06

### 게임 내부 판정 완화

- OPTIONS 아래에 SET JUDGMENT 1 2 3 4 5 6 메뉴 추가.
- 1은 기본 판정, 2~6은 앞뒤 성공 판정에 각각 0.02/0.04/0.06/0.08/0.10초 추가.
- 실제 곡 템포의 분자/분모로 시간 환산; 방향·A/B 판단은 원래 게임 루틴 사용.
- A/START/오른쪽으로 다음 값, 왼쪽으로 이전 값; 6↔1 순환.
- 선택 숫자는 원래 알파, 나머지는 50% 알파; 선택 줄은 기존 메뉴의 노란색 강조 적용.
- 현재 실행 중 선택값 유지, 새 부팅 기본값 1. VMU 설정 저장 없음.
- 이미 처리한 노트가 다음 노트의 빠른 입력을 삼키는 겹침 상황 처리.

### 옵션 이미지 수정

- 숫자 모양과 문구의 위아래 가장자리 수정.
- JUDGMENT의 글자 겹침과 마지막 T 잘림 보완 작업 후 사용자 재수정 PNG 적용.
- 최종 SET_JUDGMENT_2.png(429×24, SHA-256 d3c7443b9f5609991a39c4d15257d2271a1e21295df11e8f5d30d3887887e8a5) 사용.
- 원본 크기·좌표·투명 영역 보존, VQ 압축 없이 ARGB4444 픽셀 도형으로 표시.
- 여섯 숫자의 독립 선택 효과 유지; 기존 TITLE/COMMON/ROLL 한글화 이미지 유지.

### 편집기와 배포

- Workbench v8: 사용자 판정 옵션 PNG 가져오기와 SH-4 메뉴 코드 포함.
- data/judgment_artwork.json을 기준으로 ROM 재생성 시 같은 PNG 적용.
- Windows 패치 적용기 v0.8: 배포 manifest의 버전을 프로그램 제목과 기본 출력 폴더에 사용.
- 원본 일본판에 적용하는 새 트랙 5 차이 패치, Workbench v8 묶음, 대조 CSV, SHA-256 제공.
- 메인 화면을 README/릴리스 설명 최상단에 유지. 기본 1·선택 2·선택 6 실제 옵션 화면 및 제작 PNG 추가.

### 검증과 범위

- 원래 SH-4 판정 루틴으로 경계/버튼 100개 및 연속 노트 6개 검사 통과. 최종 PNG 수정 전 판정 코드 검사이며 이후 판정 규칙 변경 없음.
- 최종 디스크에서 공식 코어의 옵션 표시·기본값·선택 숫자/반투명 확인.
- PNG→ARGB4444 전체 픽셀 일치, 패키지 디스크 파일 읽기·섹터 EDC/ECC·CHD 무결성 확인.
- 배포 실행 파일로 일본판 원본 → 5개 트랙/GDI/CHD 전체 결과 대조.
- 물리 Dreamcast/ODE, 모든 연타·홀드 및 전체 Normal/Extra 분기는 미확인.
- 한글 자막은 기존 244개 미디어/546구간을 이어받음. 이번 버전은 새 판정 기능과 옵션 디자인 업데이트이며 번역 전체 검수 완료를 뜻하지 않음.

'''

def main():
    readme=PUBLIC/'README.md';text=readme.read_text('utf-8')
    changes={'# DC Space Channel 5 한국어 패치 v0.7':'# DC Space Channel 5 한국어 패치 v0.8',
             '[v0.7 다운로드]':'[v0.8 다운로드]',
             '/releases/tag/v0.7':'/releases/tag/v0.8',
             'v0.7은 현재까지':'v0.8은 현재까지',
             'DC-Space-Channel-5-Kr-v0.7-':'DC-Space-Channel-5-Kr-v0.8-',
             'SC5KoreanPatcher_v0.7.exe':'SC5KoreanPatcher_v0.8.exe',
             'SC5KoreanWorkbench_v6.exe':'SC5KoreanWorkbench_v8.exe',
             '편집기 v6':'편집기 v8',
             'v6의 전체 ROM':'v8의 전체 ROM',
             '## v0.7에 들어간 작업':'## v0.7에서 이어받은 한글화 작업',
             '아래 1~5번은 **최종 v0.7 CHD':'아래 기존 게임 플레이 화면은 **최종 v0.7 CHD'}
    for old,new in changes.items():text=text.replace(old,new)
    text=text.replace('## 다운로드와 패치 적용',NEW+'## 다운로드와 패치 적용',1)
    text=text.replace('확인합니다. 근거는','확인합니다. 근거는')
    readme.write_text(text,'utf-8')
    changelog=PUBLIC/'CHANGELOG.md';text=changelog.read_text('utf-8')
    marker=text.index('## v0.7')
    changelog.write_text(text[:marker]+CHANGE+text[marker:],'utf-8')
    development=PUBLIC/'docs/DEVELOPMENT.md';text=development.read_text('utf-8').replace('공개한 v6 실행 파일','공개한 v8 실행 파일')
    text+='''\n## v0.8 판정 옵션과 사용자 PNG\n\n`native/judgment.c`가 OPTIONS 행과 플레이어 입력 판정을 연결합니다. `sc5/judgment_assets.py`는 `data/judgment_artwork.json`의 `source` PNG를 읽고 7개 표시 범위(문구 + 여섯 숫자)를 만듭니다. 기본 PNG 캔버스는 429×24, 숫자 시작 x=285, 숫자 간격 24px입니다. 크기와 좌표를 유지해 편집하면 ROM 빌드가 같은 파일을 반영합니다. PNG에 없는 픽셀을 새로 만들거나 VQ 압축을 수행하지 않습니다. 게임의 ARGB4444 정밀도로 양자화하고 전체 표시 픽셀을 다시 대조합니다.\n\n판정 단계는 실행 파일의 세션 변수입니다. 별도 설정 파일이나 VMU 변경이 필요하지 않습니다. 106개 판정 검사는 PNG 최종 업데이트 전의 동일 판정 코드 검사입니다. 자료는 `docs/verification/judgment-boundaries.json`, `judgment-adjacent-notes.json`, `judgment-user-png.json`에 있습니다. 실제 화면은 `docs/screenshots/11-judgment-default.png`~`13-judgment-level6.png`입니다.\n\n`tools/prepare_public_v08.py`와 `tools/finalize_public_v08.py`는 이 로컬 공개 배포 준비 기록입니다. 기존 경로와 검증된 디스크를 요구하므로 범용 재빌드 명령으로 사용하지 않습니다.\n'''
    development.write_text(text,'utf-8')

if __name__=='__main__':main()
