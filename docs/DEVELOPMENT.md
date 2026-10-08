# 개발 및 편집 환경

일반 실행용 ROM은 릴리스의 Patch ZIP으로 만듭니다. 아래 안내는 번역·이미지를 바꿔 다시 빌드하는 개발자를 위한 내용입니다.

## 편집기 사용

Workbench ZIP을 압축 해제하고 `SC5KoreanWorkbench_v16.exe`를 실행합니다. `data/edits.json`이 있는 폴더를 프로젝트로 선택하고, 원본 디스크 선택 버튼으로 일본판 5트랙 폴더를 지정합니다. 번역 저장·원본 비교·음성/영상 재생·CSV 내보내기는 독립 실행형 편집기에서 사용합니다.

ROM 생성과 게임 실행에는 다음의 별도 도구 준비가 필요합니다.

## 소스 환경

Windows와 Python 3.13에서 작업했습니다. Tk는 Python 설치 구성에 포함합니다.

```powershell
python -m pip install -r requirements.txt
python -m sc5.native_editor --project . --disc 'D:\Games\Space Channel 5 (Japan)'
```

선택한 원본 경로는 편집기의 `원본 디스크 선택`에서 저장할 수 있습니다. `data/disc.json`의 원본 경로는 배포 환경에서 지정하도록 비워 두었습니다. 해당 파일의 LBA와 이미지 카탈로그는 원본 디스크 기준입니다. 생성한 ROM의 재배치 위치는 빌드 과정에서 다시 읽습니다.

## ROM 생성용 외부 도구

- SH-4용 little endian `sh-elf-gcc`, `objcopy`, `nm`, `objdump`: 프로젝트의 `work/native-rom/toolchain/sh-elf/sh-elf/bin/` 아래에 준비합니다. 사용한 GCC 옵션은 `sc5/native_subtitles.py`에 있습니다.
- MAME 0.289의 `chdman.exe`: `work/native-rom/toolchain/mame/chdman.exe`에 준비합니다. Patch ZIP의 `bin/chdman.exe`를 같은 위치에 복사할 수도 있습니다.
- `native/sector_retime.dll`은 원시 Mode 1 섹터 주소와 EDC/ECC 갱신에 사용하는 Windows 호스트 빌드 도우미입니다. 게임과 에뮬레이터에는 설치하지 않습니다. 소스는 `native/sector_retime.c`입니다.
- 편집기에서 바로 게임을 실행하려면 `sc5/runtime_launcher.py`에 정의된 일반 Flycast 플레이어 위치도 준비해야 합니다. 플레이어는 릴리스 ZIP에 포함하지 않았습니다.

현재 내장 코드 빌더는 대상 원본 실행 파일과의 일치를 확인하는 로컬 사본을 사용하므로, 최초 한 번 다음과 같이 사용자 원본에서 추출합니다. 원본 실행 파일은 GitHub에 배포하지 않습니다.

```powershell
New-Item -ItemType Directory -Force work/runtime
python -m sc5.cli --disc 'D:\Games\Space Channel 5 (Japan)' extract 1ST_READ.BIN work/runtime/original-1ST_READ.BIN
```

원본 디스크를 선택한 뒤 편집기의 **자막 내장 ROM 생성**을 누릅니다. 또는 소스에서 다음을 실행합니다.

```powershell
python -m sc5.native_editor --build-disc --project . --disc 'D:\Games\Space Channel 5 (Japan)'
```

CPRO → PVR/PVM 및 SAN 수정 → ISO 파일 재배치 → 자막 데이터 생성 → SH-4 컴파일/실행 파일 삽입 → GDI/CHD 생성 순서입니다. 결과는 `output/`에 생성합니다. 원본 CUE/BIN은 수정하지 않습니다.

## 편집기 실행 파일 재생성

```powershell
python -m pip install pyinstaller
python tools/build_native_editor.py --out SC5KoreanWorkbench.exe
```

공개한 v12 실행 파일과 현재 소스는 COMMON VQ + PAL8 한글 표시, 저장 안내문 크기/UV 조정 모듈 및 섹터 재배치 도우미를 포함합니다. 최종 ROM 전체 빌드는 로컬 소스 환경에서 검증했으며, 모든 사용자 환경과 별도 도구 배치까지 검증한 배포는 아닙니다.

## 패치 적용기 소스

`tools/release_patcher.py`는 릴리스 폴더의 `manifest.json`, `patches`, `bin`을 읽습니다. 패치 파일 생성에는 일본판 원본과 검증된 최종 GDI/BIN이 필요합니다. `tools/prepare_public_v07.py`는 이번 로컬 릴리스 준비 기록이며 경로와 증거 파일 이름이 작업 환경에 고정되어 있습니다. 범용 재빌드 명령으로 사용하지 않습니다.

## 자료 구분

- `data/edits.json`: 현재 편집 상태.
- `data/translations/`: CPRO 일본어·한국어 문장.
- `data/asr*`: 인식 초안. 자동 인식 결과를 청취 검수 완료로 해석하지 않습니다.
- `data/localization_export.csv`: 861행 대조용 내보내기. CSV 자동 가져오기는 지원하지 않습니다.
- `assets/image-edits`, `assets/san-edits`: 수정 이미지.
- `assets/packing-bases`: 기존 승인 이미지의 VQ 상태를 유지하기 위한 기준.
- `docs/verification`: 최종 ROM 및 스크린샷 검증 기록.

현재 저장소는 ROM·BIOS·개조 에뮬레이터·원본 음성/영상 파일을 포함하지 않습니다. 원본 미리보기는 사용자가 선택한 디스크에서 추출합니다.

## v0.8 판정 옵션과 사용자 PNG

`native/judgment.c`가 OPTIONS 행과 플레이어 입력 판정을 연결합니다. `sc5/judgment_assets.py`는 `data/judgment_artwork.json`의 `source` PNG를 읽고 7개 표시 범위(문구 + 여섯 숫자)를 만듭니다. 기본 PNG 캔버스는 429×24, 숫자 시작 x=285, 숫자 간격 24px입니다. 크기와 좌표를 유지해 편집하면 ROM 빌드가 같은 파일을 반영합니다. PNG에 없는 픽셀을 새로 만들거나 VQ 압축을 수행하지 않습니다. 게임의 ARGB4444 정밀도로 양자화하고 전체 표시 픽셀을 다시 대조합니다.

v0.81은 `native/judgment_vmu.c`에서 원래 게임의 비동기 VMU 드라이버로 `SC5KR_JUDGE` 설정 파일 2블록을 기록하고 부팅 시 읽습니다. 기존 `SPACECH5_001` 등의 진행 파일 형식은 바꾸지 않습니다. 숫자 변경 후 90프레임 동안 추가 변경이 없으면 저장을 시작합니다. 106개 판정 검사는 PNG 최종 업데이트 전의 동일 판정 코드 검사입니다. 자료는 `docs/verification/judgment-boundaries.json`, `judgment-adjacent-notes.json`, `judgment-user-png.json`에 있습니다. 실제 화면은 `docs/screenshots/11-judgment-default.png`~`13-judgment-level6.png`입니다.

`tools/prepare_public_v08.py`와 `tools/finalize_public_v08.py`는 이 로컬 공개 배포 준비 기록입니다. 기존 경로와 검증된 디스크를 요구하므로 범용 재빌드 명령으로 사용하지 않습니다.

## v0.81 공개 준비

`tools/prepare_public_v081.py`, `document_public_v081.py`, `finalize_public_v081.py`는 검증된 로컬 디스크를 사용하는 배포 준비 기록입니다. `docs/verification/judgment-vmu.json`에는 공식 코어의 완전 종료/새 부팅, 일본판 진행 파일 보존, VMU 미연결/공간 부족 검증을 기록합니다. 새 스크린샷은 추가하지 않았습니다.

## v0.85 그래픽 수정

`sc5/compact_hud.py`가 사용자 이미지의 ARGB4444 픽셀을 3개 팔레트와 512×128 PAL8 텍스처로 저장합니다. `native/hud.c`는 원래 스프라이트 함수의 global GBIX 경로로 한글 영역을 표시합니다. `sc5/warning_layout.py`와 `sc5/texture_text.py`는 저장 안내문을 실제 표시 크기로 만들고 원래 UV/배율을 조정합니다. 빌드 방식은 `data/edits.json`의 `common_compact`로 기록됩니다.

`tools/prepare_public_v085.py`, `document_public_v085.py`, `finalize_public_v085.py`는 로컬 배포 준비 기록입니다. `docs/verification`의 보스 VRAM·저장 화면·후보/최종 코드 대조·패치 재적용 결과가 검증 범위를 설명합니다.

## v1.1 영상 차이 패치와 글자 표시

- `sc5/movie_assets.py`는 `data/movie_replacements.json`의 수정 영상을 미리보기·디스크 빌드에 연결합니다. 공개본에는 `assets/movie-edits/R4_MAKUMA.SFD.xdelta`만 포함합니다.
- Workbench ZIP의 `bin/xdelta3.exe`를 함께 유지하세요. 소스 체크아웃은 Patch ZIP의 같은 파일을 `bin/xdelta3.exe`로 복사합니다. 원본 영상, 차이 패치, 도구, 복원 결과의 SHA-256을 모두 검사합니다.
- 원본 영상은 지정한 일본판 디스크에서 읽으며 복원 결과는 `work/movie-replacements/`에 캐시합니다. 영상 원본이나 음성을 저장소에 추가하지 않습니다.
- `sc5/render_cpro.py`는 79장 프로필을 최종 픽셀 크기로 만들고 `sc5/profile_layout.py`가 본문 세로 축소와 분류 제목 잘림·중앙 정렬을 처리합니다.
- `native/hud.c`는 한글 팔레트 텍스처 표시 후 원래 활성 머티리얼까지 복원합니다.
- `tools/prepare_public_v11.py`, `finalize_public_v11.py`는 특정 로컬 경로와 검증 자료를 사용하는 배포 기록입니다. 범용 게임 재빌드 명령은 위의 소스 환경을 따릅니다.

V1.1 배포 패치의 원본→최종 디스크 재생성은 검증했습니다. Workbench ZIP을 완전히 새 개발 환경에 설치해 SH-4 전체 재빌드까지 실행하는 검증과 실기 검증은 별도입니다.
