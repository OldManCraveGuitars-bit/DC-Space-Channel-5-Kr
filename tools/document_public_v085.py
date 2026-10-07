"""Document the v0.85 save-message and boss graphics repairs with captured evidence."""
import json,re
from prepare_public_v085 import ROOT,PUBLIC,RELEASE,PATCH,sha

BASE='https://github.com/OldManCraveGuitars-bit/DC-Space-Channel-5-Kr'
UPDATE='''## v0.85 업데이트 — 저장 안내문·보스 그래픽 수정

### 저장 안내문과 SAVE 표시

- 저장 화면의 **“파일을 덮어쓰려면 A 버튼, 게임을 계속하려면 B 버튼을 눌러 모로.”** 문구에서 흰 획 주변이 번지고 가장자리가 흐트러지던 문제를 수정했습니다.
- **영덕 블루로드체**를 유지했습니다. 덮어쓰기 안내는 실제 표시 크기인 **16px / 줄 간격 20px**로 만들고, 큰 글자를 게임에서 0.6배 축소하던 단계를 없앴습니다. 다른 저장·불러오기 경고는 각 표시 크기에 맞췄습니다.
- 글자 가장자리의 알파 값을 정리하고, 새 문구의 배치에 맞춰 텍스처 참조 범위를 조정했습니다. 저장 안내 아틀라스는 압축 후 픽셀 대조를 통과했습니다.
- **SAVE의 마지막 E 오른쪽 잘림**은 원래 영문 그림을 유지하고 화면에서 참조하는 오른쪽 범위를 6px 늘려 수정했습니다.

![v0.85 저장 화면과 SAVE 끝부분](docs/screenshots/16-save-screen-v085.png)

아래는 같은 실제 게임 화면의 안내문을 잘라 **2배 최근접 확대**한 것입니다. 글자를 다시 그리거나 보정한 이미지가 아닙니다.

![v0.85 저장 안내문 확대](docs/screenshots/17-save-warning-v085.png)

### 1스테이지 보스 전투 중 텍스처 깨짐

- 코코★타피오카가 **등장한 뒤 전투할 때** 몸 표면에 잡색과 줄무늬가 생기던 문제를 수정했습니다.
- 이전 한글 HUD의 큰 비압축 텍스처가 그래픽 메모리 배치를 밀어내면서 보스 텍스처와 영상 출력 영역이 겹치는 것을 확인했습니다.
- 원래 공용 아틀라스의 작은 VQ 저장 구조를 복원하고, 사용자가 수정한 한글 글씨를 별도의 **512×128 팔레트 텍스처**로 표시합니다. 기존 16비트 전체 아틀라스보다 **391,168바이트(382KiB)** 적게 사용합니다.
- 사용자 PNG를 다시 그리거나 축소하지 않았습니다. 게임의 **ARGB4444 정밀도로 양자화한 표시 픽셀을 모두 보존**하므로, 이전 VQ 재압축 때처럼 글자 모양을 뭉개지 않습니다.
- 보스 원본 텍스처 7개와 모델·재배치 데이터를 보존했습니다. 실제 전투 중 그래픽 메모리에서도 7개 텍스처가 일본판 원본 바이트와 일치하고 영상 영역과 겹치지 않는 것을 확인했습니다.
- 모든 수정은 디스크 내부에 들어갑니다. 일반 에뮬레이터로 패치한 디스크를 실행할 수 있습니다.

![v0.85 보스 등장 후 실제 전투 — 몸 표면과 한글 HUD](docs/screenshots/18-boss-gameplay-v085.png)

![v0.85 한글 시청률 HUD와 내장 음성 자막](docs/screenshots/19-gameplay-hud-v085.png)

### 이번 검증과 배포

위 새 게임 화면은 **개조하지 않은 Flycast libretro 코어로 새로 부팅한 수정 후보 디스크**에서 캡처했습니다. 게임의 CPU 비기를 사용했고 상태 불러오기나 코어 메모리 쓰기를 사용하지 않았습니다. 보스 등장 장면뿐 아니라 이후 전투와 저장 화면까지 확인했습니다.

배포 빌드와 캡처 후보의 자막 코드·HUD 코드·저장 안내문·새 한글 텍스처는 동일합니다. 배포 과정에서 바뀐 실행 파일 부분은 파일 재배치에 맞춘 음성 아카이브 위치이며, 기존 승인된 모로성인 아틀라스의 압축 상태도 유지했습니다. [화면별 기록](docs/verification/screenshots.json), [보스 그래픽 메모리 대조](docs/verification/boss-vram.json), [후보/배포 코드 대조](docs/verification/candidate-final-code.json)를 제공합니다.

최종 GDI 파일·섹터 EDC/ECC와 CHD 무결성을 검사했으며, **배포 Windows 적용기로 원본 일본판을 다시 패치한 결과도 5개 트랙과 CHD 해시가 기준 빌드와 일치**했습니다. [배포 패치 검증](docs/verification/patch-roundtrip.json)을 참고하세요.

Workbench **v12**에 새 저장 안내문 렌더링과 HUD 저장 방식을 반영했습니다. 기존 SET JUDGMENT 1~6, VMU 설정 저장, 일본판 진행 세이브 호환과 내장 자막을 이어갑니다. v0.85에서 VMU·판정 검증 전체를 다시 실행한 것은 아니며, 기존 검증 기록은 v0.8/v0.81 자료로 표시합니다. **물리 Dreamcast/ODE와 다른 리포트·Normal/Extra 전체 분기는 아직 추가 검증이 필요합니다.**

'''

CHANGE='''## v0.85 — 2026-10-08

### 저장 화면

- 영덕 블루로드체를 유지하며 저장 안내문 흰 획 번짐과 가장자리 정리.
- 덮어쓰기 안내를 실제 표시 크기 16px, 줄 간격 20px로 제작하고 기존 0.6배 축소 제거.
- 다른 저장/불러오기 경고의 글자 크기·행 위치·UV 범위 조정. 압축 후 픽셀 대조 통과.
- SAVE 영문 원본 이미지의 E가 잘리지 않도록 오른쪽 UV를 390px에서 396px로 확장.

### 보스와 HUD

- 1스테이지 보스 등장 후 전투 중 텍스처가 영상 출력 영역과 겹치던 문제 수정.
- 공용 HUD의 원래 VQ 아틀라스와 별도 512×128 PAL8 한글 텍스처 사용.
- 해당 HUD의 VRAM 사용량을 524,288바이트에서 133,120바이트로 축소(382KiB 절약).
- 사용자 수정 PNG 크기·위치·ARGB4444 표시 픽셀 보존. 그림 재작업·리샘플링 없음.
- 새 PVM 멤버를 추가하면서 텍스처 데이터의 32바이트 정렬 유지.
- 보스 텍스처 7개·모델 데이터 보존; 전투 중 VRAM의 원본 바이트 일치 확인.

### 배포와 검증

- Patch 적용기/차이 패치, Workbench v12, 최신 CSV와 체크섬 갱신.
- 저장 화면, 안내문 확대, 보스 전투, 한글 HUD 캡처 4장 추가. 메인 화면은 문서 최상단 유지.
- 공식 Flycast 코어의 새 부팅/CPU 진행으로 보스 등장 이후 전투와 저장 화면 확인.
- 후보와 배포 코드 차이 대조, GDI 읽기/EDC/ECC, CHD Raw/Overall SHA1 확인.
- 배포 실행 파일로 원본 일본판을 실제 패치해 5개 트랙과 CHD 해시 일치 확인.
- 물리 Dreamcast/ODE와 다른 리포트 전체 회귀 검증은 미완료. VMU/판정 검증은 v0.8/v0.81 기록 유지.

'''

STORAGE='''### 4. 사용자 제공 이미지 화질과 v0.85 저장 방식

v0.7~v0.81에서는 작은 한글 획의 VQ 압축 손실을 피하기 위해 `COMMON_DATA.PVM:114` 전체를 비압축 ARGB4444로 저장했습니다. v0.85는 이 방식에서 발생한 보스 그래픽 메모리 충돌을 수정했습니다.

- 원래 아틀라스의 VQ 데이터에서 한글 글씨 영역을 비우고, 사용자 이미지의 한글 픽셀을 별도 512×128 PAL8 텍스처로 표시합니다. 3개 팔레트는 각각 197/139/111색이며 ARGB4444 양자화 결과를 정확히 재현합니다.
- 원래 영어·아이콘 영역을 보존하고, 사용자 한글 글씨를 다시 그리거나 리샘플링하지 않습니다.
- 아틀라스와 한글 텍스처의 VRAM 합계는 133,120바이트이며 이전보다 391,168바이트 작습니다. COMMON PVM 파일은 원본 784,544바이트에서 850,160바이트로 늘어납니다.
- 디스크에서는 내용이 동일한 `R21.MPB`/`R22.MPB` 데이터 영역을 공유해 공간을 확보합니다. 파일을 32섹터 이동한 뒤 내용·주소·EDC/ECC와 음성 아카이브 연결을 확인했습니다.
- 트랙 길이와 구조, 트랙 5 INDEX 00의 실제 사운드 데이터는 보존했습니다.

PNG의 색상은 게임의 채널당 4비트 정밀도로 양자화됩니다. 그 양자화 이후의 글자 픽셀에는 추가 손실이 없습니다.

'''


def main():
    manifest=json.loads((PATCH/'manifest.json').read_text('utf-8'))
    p=PUBLIC/'README.md';text=p.read_text('utf-8')
    assert text.startswith('![스페이스 채널 5 한글 메인 화면]')
    text=text.replace('# DC Space Channel 5 한국어 패치 v0.81','# DC Space Channel 5 한국어 패치 v0.85',1)
    text=text.replace('[v0.81 다운로드]','[v0.85 다운로드]').replace('/releases/tag/v0.81)','/releases/tag/v0.85)')
    text=text.replace('v0.81은 현재까지','v0.85은 현재까지').replace('v0.85은 현재까지','v0.85는 현재까지')
    text=text.replace('## v0.81 업데이트 — VMU 판정 설정 저장',UPDATE+'## v0.81에서 추가한 VMU 판정 설정 저장',1)
    text=text.replace('Workbench v9','Workbench v12').replace('편집기 v9','편집기 v12').replace('SC5KoreanWorkbench_v9.exe','SC5KoreanWorkbench_v12.exe').replace('v9의 전체 ROM','v12의 전체 ROM')
    text=text.replace('Workbench v12과','Workbench v12와')
    text=text.replace('v0.81 Patch ZIP을 새 폴더','v0.85 Patch ZIP을 새 폴더').replace('v0.7/v0.8로 패치한 CHD/BIN','v0.7/v0.8/v0.81로 패치한 CHD/BIN')
    text=text.replace('DC-Space-Channel-5-Kr-v0.81-','DC-Space-Channel-5-Kr-v0.85-').replace('SC5KoreanPatcher_v0.81.exe','SC5KoreanPatcher_v0.85.exe')
    text=text.replace('이번 업데이트에는 새 스크린샷을 추가하지 않았습니다. 아래 옵션 이미지는 v0.8 당시의 화면입니다.',
                      'v0.81 당시에는 새 스크린샷을 추가하지 않았습니다. 아래 옵션 이미지는 v0.8 당시의 화면이며, v0.85 저장·보스 화면은 위에 추가했습니다.')
    start=text.index('### 4. 사용자 제공 이미지의 VQ 압축 뭉개짐 개선');end=text.index('## 작업 화면',start)
    text=text[:start]+STORAGE+text[end:]
    text=text.replace('왼쪽: 제공 PNG / 가운데: 이전 VQ 압축 / 오른쪽: 최종 ARGB4444 비압축 저장.',
                      'v0.7 당시 비교입니다. 왼쪽: 제공 PNG / 가운데: 이전 VQ 압축 / 오른쪽: 당시 ARGB4444 비압축 저장. v0.85 저장 방식은 위에 설명했습니다.')
    start=text.index('### 확인한 것\n',text.index('## 검증한 범위와 남은 작업'));end=text.index('검증 자료는 ',start)
    text=text[:start]+'''### 확인한 것

- v0.85 수정 후보의 새 부팅, 한글 HUD와 저장 안내문, 보스 등장 후 전투 화면 확인.
- 전투 중 보스 텍스처 7개의 VRAM 데이터가 일본판 원본과 일치하고 영상 영역과 겹치지 않음을 확인.
- 최종 배포 파일의 실행 코드·COMMON·사운드 드라이버 읽기 결과와 섹터 EDC/ECC 확인.
- 사용자 PNG의 ARGB4444 표시 픽셀 보존, 그래픽 메모리 382KiB 절약 확인.
- 배포 Windows 적용기로 원본 일본판에서 다시 만든 트랙 5개와 CHD의 기준 해시 일치, CHD 무결성 확인.
- 기존 음성 안내/뉴스 자막·판정 옵션·VMU 저장 확인은 위에 표시한 v0.7~v0.81 검증 기록을 유지.

'''+text[end:]
    old=json.loads((ROOT/'work/github-v0.81/DC-Space-Channel-5-Kr-v0.81-Patch/manifest.json').read_text('utf-8'))
    text=text.replace(old['chd_sha256'],manifest['chd_sha256']).replace(old['tracks'][4]['output_sha256'],manifest['tracks'][4]['output_sha256'])
    text=text.replace('3992da5013e74e024d66f63fd7baea09d37e4d67fbb2b2a823e86ed03594a89d',sha(ROOT/'SC5KoreanWorkbench_v12.exe'))
    p.write_text(text,'utf-8')
    p=PUBLIC/'CHANGELOG.md';p.write_text(p.read_text('utf-8').replace('# 변경 기록\n\n','# 변경 기록\n\n'+CHANGE,1),'utf-8')
    p=PUBLIC/'docs/DEVELOPMENT.md';text=p.read_text('utf-8').replace('SC5KoreanWorkbench_v9.exe','SC5KoreanWorkbench_v12.exe').replace('공개한 v9 실행 파일과 현재 소스는 COMMON 비압축 저장 모듈 및 섹터 재배치 도우미를 포함합니다.',
        '공개한 v12 실행 파일과 현재 소스는 COMMON VQ + PAL8 한글 표시, 저장 안내문 크기/UV 조정 모듈 및 섹터 재배치 도우미를 포함합니다.')
    text+='''
## v0.85 그래픽 수정

`sc5/compact_hud.py`가 사용자 이미지의 ARGB4444 픽셀을 3개 팔레트와 512×128 PAL8 텍스처로 저장합니다. `native/hud.c`는 원래 스프라이트 함수의 global GBIX 경로로 한글 영역을 표시합니다. `sc5/warning_layout.py`와 `sc5/texture_text.py`는 저장 안내문을 실제 표시 크기로 만들고 원래 UV/배율을 조정합니다. 빌드 방식은 `data/edits.json`의 `common_compact`로 기록됩니다.

`tools/prepare_public_v085.py`, `document_public_v085.py`, `finalize_public_v085.py`는 로컬 배포 준비 기록입니다. `docs/verification`의 보스 VRAM·저장 화면·후보/최종 코드 대조·패치 재적용 결과가 검증 범위를 설명합니다.
'''
    p.write_text(text,'utf-8')
    notes='![스페이스 채널 5 한글 메인 화면](docs/screenshots/01-title.png)\n\n# v0.85 — 저장 안내문·보스 그래픽 수정\n\n'+UPDATE
    notes+='''## 다운로드와 업데이트

- **DC-Space-Channel-5-Kr-v0.85-Patch.zip**: 차이 패치, Windows 적용기 `SC5KoreanPatcher_v0.85.exe`, GDI/CHD 생성 도구.
- **DC-Space-Channel-5-Kr-v0.85-Workbench.zip**: 편집기 v12, 현재 번역·이미지·자막 데이터와 소스.
- **DC-Space-Channel-5-Kr-v0.85-Text.csv**: 861행 원문/번역/시간 대조 목록.
- **SHA256SUMS.txt**: 배포 파일 체크섬.

Patch ZIP을 새 폴더에 풀고 **원본 일본판 5개 BIN에서 다시 적용**하세요. 기존 한글패치 CHD/BIN 위에 덧씌우는 업데이트가 아닙니다. 기존 일본판/한글판 진행 세이브는 같은 VMU를 사용하면 유지됩니다. 판정 설정은 기존처럼 별도 `SC5KR_JUDGE` 파일 2블록에 저장합니다.

원본 게임과 BIOS는 포함하지 않습니다. 패치 결과는 `Space Channel 5 Korean Native.chd`와 GDI/BIN이며 게임 기능은 단일 디스크 내부에 구현되어 있습니다.

[사용법과 전체 작업 내역](README.md) · [상세 변경 기록](CHANGELOG.md)

KOREAN LOCALIZATION BY **GIKAKNO**
'''
    notes=notes.replace('](docs/screenshots/','](https://raw.githubusercontent.com/OldManCraveGuitars-bit/DC-Space-Channel-5-Kr/v0.85/docs/screenshots/')
    notes=re.sub(r'\]\((docs/[^)]+|README\.md|CHANGELOG\.md)\)',lambda m:']('+BASE+'/blob/v0.85/'+m[1]+')',notes)
    (RELEASE/'release-notes.md').write_text(notes,'utf-8')


if __name__=='__main__':main()
