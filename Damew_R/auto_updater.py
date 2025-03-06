import os
import sys
import json
import shutil
import zipfile
import requests
import subprocess
from PyQt6.QtWidgets import (QApplication, QDialog, QProgressBar, QLabel, 
                            QVBoxLayout, QPushButton, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

def get_executable_dir():
    """실행 파일 또는 스크립트가 있는 디렉토리 경로를 반환합니다."""
    if getattr(sys, 'frozen', False):
        # exe로 실행될 때
        return os.path.dirname(sys.executable)
    else:
        # 스크립트로 실행될 때
        return os.path.dirname(os.path.abspath(__file__))

class UpdateWorker(QThread):
    progress_signal = pyqtSignal(int, str)
    complete_signal = pyqtSignal(bool, str)
    
    def __init__(self, github_repo, github_token=None, is_private=False):
        super().__init__()
        self.github_repo = github_repo
        self.github_token = github_token
        self.is_private = is_private
        self.api_url = f"https://api.github.com/repos/{github_repo}"
        
    def run(self):
        try:
            self.progress_signal.emit(10, "최신 버전 확인 중...")
            
            # 현재 버전 확인
            version_file = os.path.join(get_executable_dir(), "version.txt")
            if os.path.exists(version_file):
                with open(version_file, "r") as f:
                    current_version = f.read().strip()
            else:
                # 버전 파일이 없으면 초기 버전 생성
                current_version = "v0.0.0"
                with open(version_file, "w") as f:
                    f.write(current_version)
            
            self.progress_signal.emit(20, f"현재 버전: {current_version}")
            
            # GitHub API로 최신 릴리스 정보 가져오기
            if self.is_private and self.github_token:
                headers = {'Authorization': f'token {self.github_token}'}
                response = requests.get(f"{self.api_url}/releases/latest", headers=headers)
            else:
                response = requests.get(f"{self.api_url}/releases/latest")
            
            if response.status_code != 200:
                self.complete_signal.emit(False, f"GitHub API 요청 실패: {response.status_code}")
                return
            
            release_info = response.json()
            latest_version = release_info.get('tag_name')
            
            if not latest_version:
                self.complete_signal.emit(False, "최신 버전 정보를 찾을 수 없습니다.")
                return
            
            self.progress_signal.emit(30, f"최신 버전: {latest_version}")
            
            # 버전 비교
            if latest_version == current_version:
                self.complete_signal.emit(True, "이미 최신 버전입니다.")
                return
            
            # 업데이트 필요
            self.progress_signal.emit(40, "업데이트 파일 다운로드 중...")
            
            # assets 확인
            if not release_info.get('assets'):
                self.complete_signal.emit(False, "업데이트 파일을 찾을 수 없습니다.")
                return
            
            # 첫 번째 asset 다운로드 (ZIP 파일 가정)
            download_url = release_info['assets'][0]['url']
            
            # 다운로드 요청 헤더 설정
            headers = {'Accept': 'application/octet-stream'}
            if self.is_private and self.github_token:
                headers['Authorization'] = f'token {self.github_token}'
            
            # 파일 다운로드
            response = requests.get(download_url, headers=headers, stream=True)
            
            if response.status_code != 200:
                self.complete_signal.emit(False, f"파일 다운로드 실패: {response.status_code}")
                return
            
            # 임시 디렉토리 및 파일 경로
            temp_dir = os.path.join(get_executable_dir(), "update_temp")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.makedirs(temp_dir)
            
            zip_path = os.path.join(temp_dir, "update.zip")
            
            # 파일 저장
            self.progress_signal.emit(50, "파일 저장 중...")
            with open(zip_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192*1024):  # 8MB 단위로 저장
                    f.write(chunk)
            
            # 압축 해제
            self.progress_signal.emit(60, "압축 해제 중...")
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # 원본 파일 백업 (선택 사항)
            self.progress_signal.emit(70, "백업 생성 중...")
            backup_dir = os.path.join(get_executable_dir(), "backup")
            if os.path.exists(backup_dir):
                shutil.rmtree(backup_dir)
            os.makedirs(backup_dir)
            
            # 중요 파일/디렉토리 백업 (설정, 데이터 등)
            for item in ["version.txt", "settings.json", "kills_data.json"]:
                src_path = os.path.join(get_executable_dir(), item)
                if os.path.exists(src_path):
                    dst_path = os.path.join(backup_dir, item)
                    if os.path.isdir(src_path):
                        shutil.copytree(src_path, dst_path)
                    else:
                        shutil.copy2(src_path, dst_path)
            
            # 파일 업데이트
            self.progress_signal.emit(80, "파일 업데이트 중...")
            
            # 제외할 파일/디렉토리 목록 (백업된 파일 및 업데이트 파일 제외)
            exclude_items = ["backup", "update_temp", "version.txt", "settings.json", "kills_data.json"]
            
            def copy_tree_with_exclude(src, dst, exclude=[]):
                if not os.path.exists(dst):
                    os.makedirs(dst)
                
                for item in os.listdir(src):
                    if item in exclude:
                        continue
                    
                    s = os.path.join(src, item)
                    d = os.path.join(dst, item)
                    
                    if os.path.isdir(s):
                        copy_tree_with_exclude(s, d, exclude)
                    else:
                        if os.path.exists(d):
                            os.remove(d)
                        shutil.copy2(s, d)
            
            copy_tree_with_exclude(extract_dir, get_executable_dir(), exclude_items)
            
            # 버전 파일 업데이트
            self.progress_signal.emit(90, "버전 정보 업데이트 중...")
            with open(version_file, "w") as f:
                f.write(latest_version)
            
            # 임시 파일 정리
            self.progress_signal.emit(95, "임시 파일 정리 중...")
            shutil.rmtree(temp_dir)
            
            self.progress_signal.emit(100, "업데이트 완료!")
            self.complete_signal.emit(True, f"성공적으로 버전 {latest_version}(으)로 업데이트되었습니다.")
            
        except Exception as e:
            self.complete_signal.emit(False, f"업데이트 중 오류 발생: {str(e)}")

class UpdateDialog(QDialog):
    def __init__(self, github_repo, github_token=None, is_private=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("아프리카 도우미 업데이트")
        self.setFixedSize(400, 200)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        
        self.layout = QVBoxLayout(self)
        
        self.status_label = QLabel("업데이트 확인 중...")
        self.layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.layout.addWidget(self.progress_bar)
        
        self.restart_button = QPushButton("재시작")
        self.restart_button.clicked.connect(self.restart_app)
        self.restart_button.setEnabled(False)
        self.layout.addWidget(self.restart_button)
        
        self.close_button = QPushButton("닫기")
        self.close_button.clicked.connect(self.reject)
        self.layout.addWidget(self.close_button)
        
        # 업데이트 작업 시작
        self.worker = UpdateWorker(github_repo, github_token, is_private)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.complete_signal.connect(self.update_complete)
        self.worker.start()
        
        self.update_needed = False
        
    def update_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.status_label.setText(message)
        
    def update_complete(self, success, message):
        if success:
            if "이미 최신 버전" in message:
                self.status_label.setText(message)
                self.progress_bar.setValue(100)
            else:
                self.status_label.setText(message)
                self.restart_button.setEnabled(True)
                self.update_needed = True
                self.close_button.setText("나중에 재시작")
        else:
            self.status_label.setText(f"업데이트 실패: {message}")
            QMessageBox.warning(self, "업데이트 실패", message)
        
    def restart_app(self):
        if self.update_needed:
            # 현재 프로세스의 경로 확인
            if getattr(sys, 'frozen', False):
                # exe로 실행된 경우
                app_path = sys.executable
            else:
                # 스크립트로 실행된 경우
                app_path = sys.argv[0]
            
            # 새 프로세스 시작 및 현재 프로세스 종료
            subprocess.Popen([app_path])
            self.parent().close() if self.parent() else None
            QApplication.quit()

def check_for_updates(parent=None, silent=False):
    # 설정 파일에서 GitHub 리포지토리 정보 읽기
    config_path = os.path.join(get_executable_dir(), "update_config.json")
    
    if not os.path.exists(config_path):
        # 기본 설정 생성
        default_config = {
            "github_repo": "YourUsername/YourRepo",  # 변경 필요
            "is_private": False,
            "github_token": "",  # 비공개 저장소인 경우 토큰 필요
            "check_on_startup": True
        }
        
        with open(config_path, "w") as f:
            json.dump(default_config, f, indent=4)
        
        if not silent:
            QMessageBox.information(
                parent, 
                "업데이트 설정 필요", 
                "업데이트 설정 파일이 생성되었습니다. 설정을 완료한 후 다시 시도해주세요."
            )
        return False
    
    # 설정 불러오기
    with open(config_path, "r") as f:
        config = json.load(f)
    
    # 설정이 기본값이라면 경고
    if config["github_repo"] == "YourUsername/YourRepo":
        if not silent:
            QMessageBox.warning(
                parent, 
                "업데이트 설정 필요", 
                "GitHub 저장소 정보가 설정되지 않았습니다. update_config.json 파일을 수정해주세요."
            )
        return False
    
    # 업데이트 다이얼로그 표시
    dialog = UpdateDialog(
        config["github_repo"], 
        config["github_token"] if config["is_private"] else None,
        config["is_private"],
        parent
    )
    
    return dialog.exec()

# 독립 실행 테스트용
if __name__ == "__main__":
    app = QApplication(sys.argv)
    check_for_updates()
    sys.exit(app.exec())