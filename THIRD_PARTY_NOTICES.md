# 사용 자료와 외부 구성요소

## 게임 자료

Space Channel 5는 SEGA의 게임입니다. 게임 화면, 캐릭터 및 원작 자산의 권리는 해당 권리자에게 있습니다. 이 저장소에는 번역 자료·수정 이미지·검증 화면·작업 코드가 있으며, 릴리스는 사용자 원본을 필요로 하는 차이 패치로 제공합니다.

## 영덕 블루로드체

글꼴 제공: 영덕군. [공식 전용서체 안내 및 사용 조건](https://www.yd.go.kr/?page_id=120264)을 따릅니다. 글꼴 파일은 사용자 제공 원본 그대로이며 SHA-256은 `0cb7ee0dca070a387888bb03224bb3fed3ba73ae94078ac5cacf55c3bf477944`입니다. 글꼴 자체를 판매하거나 변형하지 않았습니다.

## xdelta3 3.2.1

Copyright Joshua MacDonald 및 기여자. Apache License 2.0.

- [정확한 버전 소스와 원본 배포](https://github.com/jmacd/xdelta/releases/tag/v3.2.1)
- [포함 라이선스](docs/licenses/xdelta3-Apache-2.0.txt)

Windows x86-64 원본 실행 파일을 변경하지 않고 패치 ZIP에 넣었습니다.

## MAME chdman 0.289

MAME 개발자와 기여자의 CHD 도구입니다. MAME 프로젝트의 혼합 라이선스 조건을 따르며 프로젝트 전체의 배포 조건은 GPL 2.0입니다.

- [해당 버전 전체 소스](https://github.com/mamedev/mame/tree/mame0289)
- [해당 버전 소스 압축 다운로드](https://github.com/mamedev/mame/archive/refs/tags/mame0289.tar.gz)
- [MAME COPYING 및 외부 구성요소 안내](docs/licenses/MAME-COPYING.txt)
- [GPL 2.0 전문](docs/licenses/GPL-2.0.txt)

원본 Windows `chdman.exe`를 변경하지 않고 패치 ZIP에 넣었습니다. ROM/BIOS는 포함하지 않았습니다.

## 편집기 및 패치 적용기 실행 환경

독립 실행형 Windows 프로그램은 Python과 Tcl/Tk를 PyInstaller로 묶었습니다. 편집기에는 Pillow, NumPy, fontTools, PyAV와 FFmpeg 관련 구성요소가 포함됩니다. 각 구성요소의 원래 라이선스는 `docs/licenses/runtime/`에 함께 제공합니다.

PyAV는 FFmpeg 라이브러리를 사용합니다. FFmpeg의 소스와 라이선스 조건은 [FFmpeg 공식 사이트](https://ffmpeg.org/legal.html)를 참고하세요. 번들에 사용된 정확한 패키지 버전 및 원래 배포처는 `docs/licenses/runtime-packages.json`에 기록했습니다.

이 안내가 게임 자료나 글꼴에 새로운 라이선스를 부여하지는 않습니다. 각 구성요소에는 각각의 원래 조건이 적용됩니다.

## 후반 영상 제작 도구

R4_MAKUMA.SFD 수정 영상 제작에 FFmpeg와 [SFD_Muxer](https://github.com/nebulas-star/SFD_Muxer/tree/40a4fcbff24a30201464523816bb4470e03f3976)를 사용했습니다. SFD_Muxer는 MIT 라이선스이며 [라이선스 전문](docs/licenses/SFD_Muxer-MIT.txt)을 보존합니다. 해당 도구 실행 파일이나 완성된 게임 영상은 공개 ZIP에 포함하지 않습니다. 영상 수정분은 사용자 원본이 필요한 xdelta로 제공합니다.
