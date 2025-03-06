import sys
import os
import certifi
from cx_Freeze import setup, Executable

# 애플리케이션 이름 및 버전 정보
APP_NAME = "룰렛 자동 집계"
VERSION = "1.0.1"

# 의존성 패키지 목록
build_exe_options = {
    "packages": [
        "sys", "os", "json", "ssl", "certifi", "requests", "threading", 
        "asyncio", "websockets", "PyQt6", "datetime"
    ],
    "excludes": [],
    "include_files": [
        # 리소스 파일 추가
        ("resources/damew_roulette.png", "resources/damew_roulette.png"),
        ("resources/Damew.ico", "resources/Damew.ico"),
        (os.path.join(os.path.dirname(certifi.__file__), "cacert.pem"), "cacert.pem")
    ],
    "include_msvcr": True,  # MSVC 런타임 포함
    # DLL 파일들을 lib 폴더에 넣도록 설정
    "bin_path_includes": ["lib"],
    "bin_includes": ["lib"],
    "bin_excludes": [
        # 불필요한 DLL 제외
        "VCRUNTIME140_1.dll", 
        "VCRUNTIME140.dll", 
        "MSVCP140.dll",
        "api-ms-win-*.dll"  # Windows API DLL 제외
    ],
    # ZIP 파일로 라이브러리 압축
    "zip_include_packages": ["*"],  # 모든 패키지를 압축
    "zip_exclude_packages": [],     # 압축에서 제외할 패키지
    "build_exe": "build/Roulette Results Aggregator"  # 출력 디렉토리 지정
}

# 실행 파일 설정
base = None
if sys.platform == "win32":
    base = "Win32GUI"  # GUI 애플리케이션 (콘솔 없음)

executables = [
    Executable(
        "main.py",  # 실행할 메인 스크립트
        base=base,
        target_name="다뮤 룰렛 집계기.exe",  # 생성될 실행 파일 이름
        icon="resources/Damew.ico",  # 아이콘 경로
        shortcut_name=APP_NAME,
        shortcut_dir="DesktopFolder",
    )
]

setup(
    name=APP_NAME,
    version=VERSION,
    description="자동으로 룰렛 집계",
    options={"build_exe": build_exe_options},
    executables=executables
)