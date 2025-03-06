import json
import ssl
import certifi
import requests
import threading
import asyncio
import websockets
import auto_updater
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QLineEdit, QPushButton, QLabel, QFrame,
                           QTextEdit, QSplitter, QSizePolicy, QStackedWidget, QTabWidget)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QObject, QTimer, QThread
from PyQt6.QtGui import QPalette, QColor, QFont, QPixmap
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage  # 모듈 경로 변경
from datetime import datetime
import sys,os

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    os.chdir(sys._MEIPASS)

# 색상 상수
LIGHT_PURPLE = "#ffe6ec"  # 전체 배경색
MEDIUM_PURPLE = "#f6cdce"  # 컨테이너 색
BORDER_PURPLE = "#d28688"  # 윤곽선 색
ACCENT_PURPLE = "#f29698"  
TEXT_COLOR = "#374151"     

# 유니코드 및 기타 상수
F = "\x0c"
ESC = "\x1b\t"
SEPARATOR = "+" + "-" * 70 + "+"

def get_executable_dir():
    """실행 파일 또는 스크립트가 있는 디렉토리 경로를 반환합니다."""
    if getattr(sys, 'frozen', False):
        # exe로 실행될 때
        return os.path.dirname(sys.executable)
    else:
        # 스크립트로 실행될 때
        return os.path.dirname(os.path.abspath(__file__))

def create_ssl_context():
    if getattr(sys, 'frozen', False):
        # 번들된 exe로 실행 시 다른 인증서 경로 사용
        # cx_Freeze의 경우 실행 파일과 같은 디렉토리에 certifi의 인증서 파일이 복사됨
        cert_path = os.path.join(os.path.dirname(sys.executable), 'cacert.pem')
        if not os.path.exists(cert_path):
            # 인증서 파일이 없으면 기본 certifi 위치 사용
            cert_path = certifi.where()
    else:
        cert_path = certifi.where()
        
    # 디버깅 정보 출력
    print(f"SSL 인증서 경로: {cert_path}")
    print(f"인증서 파일 존재 여부: {os.path.exists(cert_path)}")
    
    ssl_context = ssl.create_default_context()
    ssl_context.load_verify_locations(cert_path)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    return ssl_context

def calculate_byte_size(string):
    return len(string.encode('utf-8')) + 6

def get_player_live(bno, bid):
    url = 'https://live.afreecatv.com/afreeca/player_live_api.php'
    data = {
        'bid': bid,
        'bno': bno,
        'type': 'live',
        'confirm_adult': 'false',
        'player_type': 'html5',
        'mode': 'landing',
        'from_api': '0',
        'pwd': '',
        'stream_type': 'common',
        'quality': 'HD'
    }

    try:
        response = requests.post(f'{url}?bjid={bid}', data=data)
        response.raise_for_status()
        res = response.json()
        
        # API 응답 확인 및 디버깅
        print(f"API Response Keys: {list(res.keys())}")
        if 'CHANNEL' in res:
            print(f"CHANNEL Keys: {list(res['CHANNEL'].keys())}")
        
        # 필요한 데이터 확인
        if 'CHANNEL' not in res:
            print(f"ERROR: CHANNEL 데이터가 응답에 없습니다.")
            return None
            
        channel_data = res['CHANNEL']
        required_keys = ['CHDOMAIN', 'CHATNO', 'FTK', 'TITLE', 'BJID', 'CHPT']
        missing_keys = [key for key in required_keys if key not in channel_data]
        
        if missing_keys:
            print(f"ERROR: 필요한 데이터가 없습니다: {', '.join(missing_keys)}")
            return None
            
        CHDOMAIN = channel_data["CHDOMAIN"].lower()
        CHATNO = channel_data["CHATNO"]
        FTK = channel_data["FTK"]
        TITLE = channel_data["TITLE"]
        BJID = channel_data["BJID"]
        CHPT = str(int(channel_data["CHPT"]) + 1)

        return CHDOMAIN, CHATNO, FTK, TITLE, BJID, CHPT

    except requests.RequestException as e:
        print(f"ERROR: API 요청 중 오류 발생: {e}")
        return None
    except KeyError as e:
        print(f"ERROR: 응답에서 필요한 데이터를 찾을 수 없습니다: {e}")
        return None
    except ValueError as e:
        print(f"ERROR: JSON 파싱 오류: {e}")
        return None
    except Exception as e:
        print(f"ERROR: 기타 오류: {e}")
        return None

class WebBridge(QObject):
    donationReceived = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.total_amount = 0
        self.donation_count = 0
        self.donations = []
        self.current_roulette = None
        self.pending_roulette_result = False
        self.last_message = None
        self.message_queue = []
        # 킬 수 관련 변수 추가
        self.completed_kills = 0  # 완료 킬수
        self.target_kills = 0    # 목표 킬수
        
        # 데이터 파일 경로
        self.data_file = os.path.join(get_executable_dir(), "kills_data.json")
        # 저장된 데이터 로드
        self.load_data()

    def save_data(self):
        """현재 킬수 데이터를 파일에 저장합니다."""
        try:
            data = {
                'completed_kills': self.completed_kills,
                'target_kills': self.target_kills,
                'total_amount': self.total_amount,
                'donation_count': self.donation_count
            }
            
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            print(f"데이터 저장 완료: {self.data_file}")
        except Exception as e:
            print(f"데이터 저장 오류: {str(e)}")

    def load_data(self):
        """저장된 킬수 데이터를 파일에서 불러옵니다."""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                self.completed_kills = data.get('completed_kills', 0)
                self.target_kills = data.get('target_kills', 0)
                self.total_amount = data.get('total_amount', 0)
                self.donation_count = data.get('donation_count', 0)
                
                print(f"데이터 로드 완료: {self.data_file}")
                print(f"완료 킬수: {self.completed_kills}, 목표 킬수: {self.target_kills}")
        except Exception as e:
            print(f"데이터 로드 오류: {str(e)}")
            # 오류 발생 시 기본값으로 초기화
            self.completed_kills = 0
            self.target_kills = 0
            self.total_amount = 0
            self.donation_count = 0

    def extract_number(self, text):
        text = text.replace(",", "")
        numbers = []
        current_number = ""
        
        for char in text:
            if char.isdigit():
                current_number += char
            else:
                if current_number:
                    numbers.append(int(current_number))
                    current_number = ""
                    
        if current_number:
            numbers.append(int(current_number))
            
        return numbers[0] if numbers else 0

    def handle_message(self, text, message_type="normal"):
        try:
            # HTML5 Audio나 CORS 관련 메시지는 무시
            if "HTML5 Audio" in text or "CORS" in text or "XHR" in text:
                return

            if "룰렛 결과는!" in text:
                parts = text.split("님")
                if parts:
                    nickname = parts[0].strip()
                    amount = self.extract_number(text)
                    self.current_roulette = (nickname, amount)
                    self.donationReceived.emit(f"룰렛 시작: {nickname}님 별풍선 {amount}개 룰렛 결과는!")
                    self.total_amount += amount
                    self.donation_count += 1
                return

            if message_type == "roulette_result":
                # 시간 기록
                current_time = datetime.now().strftime("%H:%M:%S")
                
                # 룰렛 결과에 따른 처리
                if text == "꽝":
                    self.donationReceived.emit(f"[{current_time}] 룰렛 결과: 꽝")
                    return
                
                # 룰렛 결과가 숫자+킬 형식인 경우
                try:
                    if '킬' in text:
                        # 숫자 추출
                        num_str = ''.join(filter(str.isdigit, text))
                        if num_str:
                            num = int(num_str)
                            
                            # '+킬' 형식인 경우 목표 킬수 증가
                            if '+' in text or text.startswith('+'):
                                self.target_kills += num
                                self.donationReceived.emit(f"[{current_time}] 룰렛 결과: {text} (목표 킬수 +{num}, 현재: {self.target_kills}킬)")
                            
                            # '-킬' 형식인 경우 목표 킬수 감소
                            # '-킬' 형식인 경우 완료 킬수 증가 (기존 목표 킬수 감소에서 변경)
                            elif '-' in text or text.startswith('-'):
                                self.completed_kills += num
                                self.donationReceived.emit(f"[{current_time}] 룰렛 결과: {text} (완료 킬수 +{num}, 현재 완료: {self.completed_kills}킬)")
                            
                            # 단순 숫자+킬 형식인 경우도 목표 킬수 증가
                            else:
                                self.target_kills += num
                                self.donationReceived.emit(f"[{current_time}] 룰렛 결과: {text} (목표 킬수 +{num}, 현재: {self.target_kills}킬)")
                        else:
                            self.donationReceived.emit(f"[{current_time}] 룰렛 결과: {text}")
                    else:
                        # 기타 룰렛 결과
                        self.donationReceived.emit(f"[{current_time}] 룰렛 결과: {text}")
                except Exception as e:
                    self.donationReceived.emit(f"[{current_time}] 룰렛 결과 처리 오류: {str(e)} (결과: {text})")
                    
                return

        except Exception as e:
            self.donationReceived.emit(f"Error processing message: {e}")

class DonationWebPage(QWebEnginePage):
    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.loadFinished.connect(self.onLoadFinished)
        self.scan_timer = None
        self.last_processed_id = None
        
    def onLoadFinished(self, ok):
        if ok:
            # 초기화 스크립트 실행 - 모든 결과 요소에 고유 ID 부여
            self.runJavaScript("""
                // 처리된 룰렛 결과 추적용 배열
                window.processedResults = [];
                
                // 룰렛 결과에 ID 부여 함수
                function addIdsToRouletteResults() {
                    const resultElements = document.querySelectorAll('.text.roulette.result:not([data-processed])');
                    resultElements.forEach((el, index) => {
                        if (!el.hasAttribute('data-result-id')) {
                            const id = 'result_' + Date.now() + '_' + index;
                            el.setAttribute('data-result-id', id);
                        }
                    });
                }
                
                // 룰렛 시작 감지 옵저버
                const observer = new MutationObserver(function(mutations) {
                    mutations.forEach(function(mutation) {
                        if (mutation.addedNodes.length) {
                            // 새 노드 추가시 룰렛 시작 메시지 확인
                            mutation.addedNodes.forEach(function(node) {
                                if (node.nodeType === 1) {
                                    const text = node.innerText || node.textContent || '';
                                    if (text && text.includes('룰렛 결과는!')) {
                                        console.log('ROULETTE_START:' + text);
                                    }
                                    
                                    // 새 룰렛 결과 요소면 ID 부여
                                    if (node.classList && node.classList.contains('text') && 
                                        node.classList.contains('roulette') && 
                                        node.classList.contains('result')) {
                                        addIdsToRouletteResults();
                                    }
                                }
                            });
                        }
                    });
                    
                    // 모든 변경 후 ID 부여 확인
                    addIdsToRouletteResults();
                });
                
                // 문서 전체 감시
                observer.observe(document.body, {
                    childList: true,
                    subtree: true
                });
                
                // 초기 실행
                addIdsToRouletteResults();
            """)
            
            # 룰렛 결과 스캔 타이머 설정
            if self.scan_timer is None:
                self.scan_timer = QTimer(self)
                self.scan_timer.timeout.connect(self.check_for_new_roulette_results)
                self.scan_timer.start(300)  # 300ms 간격으로 스캔
    
    def check_for_new_roulette_results(self):
        """미처리된 룰렛 결과 요소 찾기"""
        script = """
        (function() {
            // 미처리된 룰렛 결과 요소 찾기
            const resultElements = document.querySelectorAll('.text.roulette.result:not([data-processed])');
            
            if (resultElements.length > 0) {
                const element = resultElements[0];
                const resultId = element.getAttribute('data-result-id');
                const text = element.innerText || element.textContent || '';
                
                // 요소 처리 표시
                element.setAttribute('data-processed', 'true');
                
                // 결과 반환
                return {
                    id: resultId,
                    text: text.trim()
                };
            }
            
            // 결과 없음
            return { id: null, text: '' };
        })();
        """
        
        self.runJavaScript(script, self.handle_roulette_result)
    
    def handle_roulette_result(self, result):
        """새로운 룰렛 결과 처리"""
        if not result or not isinstance(result, dict):
            return
            
        result_id = result.get('id')
        text = result.get('text', '').strip()
        
        # ID나 텍스트가 없으면 무시
        if not result_id or not text:
            return
            
        # 이미 처리한 결과인지 확인
        if result_id == self.last_processed_id:
            return
            
        # 처리 표시
        self.last_processed_id = result_id
        
        # 결과 처리
        print(f"새 룰렛 결과 처리: {text} (ID: {result_id})")
        self.bridge.handle_message(text, "roulette_result")
    
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        """JavaScript 콘솔 메시지 처리"""
        if not message or not isinstance(message, str):
            return
            
        # 불필요한 메시지 필터링
        if any(text in message for text in ["HTML5 Audio", "CORS", "XHR"]):
            return
            
        # 룰렛 시작 메시지 처리
        if message.startswith("ROULETTE_START:"):
            roulette_text = message.replace("ROULETTE_START:", "").strip()
            self.bridge.handle_message(roulette_text)

class ChatWorker(QThread):
    message_received = pyqtSignal(str)
    connection_status = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.running = True
        self.is_stopping = False  # 종료 플래그 추가
    
    def run(self):
        asyncio.run(self.connect_to_chat())

    async def connect_to_chat(self):
        try:
            # URL에서 BID와 BNO 추출
            parts = self.url.rstrip('/').split('/')
            if len(parts) < 2:
                self.connection_status.emit("잘못된 URL 형식입니다. https://play.sooplive.co.kr/[BJ_ID]/[BNO] 형식이어야 합니다.")
                return
                
            # URL 형식 검증 - play.sooplive.co.kr 도메인 지원
            valid_domains = ["afreecatv.com", "play.sooplive.co.kr", "sooplive.co.kr"]
            if not any(domain in self.url.lower() for domain in valid_domains):
                self.connection_status.emit("지원되지 않는 URL입니다. 아프리카TV(afreecatv.com) 또는 숲라이브(sooplive.co.kr) URL만 지원합니다.")
                return
                
            BID, BNO = parts[-2], parts[-1]
            
            self.connection_status.emit(f"BJ ID: {BID}, 방송번호: {BNO} 정보 로딩 중...")
            
            result = get_player_live(BNO, BID)
            
            if result is None:
                self.connection_status.emit("채팅 정보를 가져오는데 실패했습니다. URL을 확인해주세요.")
                return
                
            CHDOMAIN, CHATNO, FTK, TITLE, BJID, CHPT = result
            
            self.connection_status.emit(
                f"방송 제목: {TITLE}\n"
                f"BJ ID: {BJID}\n"
                f"연결 중..."
            )

            ssl_context = create_ssl_context()
            
            # 웹소켓 연결 시도
            try:
                websocket_url = f"wss://{CHDOMAIN}:{CHPT}/Websocket/{BID}"
                self.connection_status.emit(f"웹소켓 연결 시도: {websocket_url}")
                
                websocket = await websockets.connect(
                    websocket_url,
                    subprotocols=['chat'],
                    ssl=ssl_context,
                    ping_interval=None
                )
                
                self.connection_status.emit("웹소켓 연결 성공!")
                    
                CONNECT_PACKET = f'{ESC}000100000600{F*3}16{F}'
                JOIN_PACKET = f'{ESC}0002{calculate_byte_size(CHATNO):06}00{F}{CHATNO}{F*5}'
                PING_PACKET = f'{ESC}000000000100{F}'

                await websocket.send(CONNECT_PACKET)
                self.connection_status.emit("채팅방 연결 성공!")
                await asyncio.sleep(2)
                await websocket.send(JOIN_PACKET)

                # 핑 전송과 메시지 수신을 위한 태스크 생성
                ping_task = asyncio.create_task(self.send_ping(websocket, PING_PACKET))
                receive_task = asyncio.create_task(self.receive_messages(websocket))
                
                # 종료 감지 태스크 생성
                stop_check_task = asyncio.create_task(self.check_stop())
                
                # 태스크 중 하나라도 완료되면 모든 태스크 취소
                done, pending = await asyncio.wait(
                    [ping_task, receive_task, stop_check_task], 
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # 남은 태스크 취소
                for task in pending:
                    task.cancel()
                    
                # 웹소켓 연결 닫기
                try:
                    await websocket.close()
                except:
                    pass
                    
                self.connection_status.emit("채팅 연결이 종료되었습니다.")
                
            except websockets.exceptions.WebSocketException as e:
                self.connection_status.emit(f"웹소켓 연결 오류: {str(e)}")
            except asyncio.CancelledError:
                self.connection_status.emit("연결이 취소되었습니다.")

        except Exception as e:
            self.connection_status.emit(f"연결 오류: {str(e)}")

    async def check_stop(self):
        """종료 플래그를 주기적으로 확인하는 코루틴"""
        while self.running:
            if self.is_stopping:
                return
            await asyncio.sleep(0.5)  # 0.5초 간격으로 확인
            
    async def send_ping(self, websocket, ping_packet):
        """서버에 주기적으로 핑을 보내는 코루틴"""
        try:
            while self.running and not self.is_stopping:
                await asyncio.sleep(60)
                if self.is_stopping:
                    break
                await websocket.send(ping_packet)
        except:
            pass

    async def receive_messages(self, websocket):
        """채팅 메시지를 수신하는 코루틴"""
        try:
            while self.running and not self.is_stopping:
                data = await websocket.recv()
                self.decode_message(data)
        except websockets.exceptions.ConnectionClosed:
            self.connection_status.emit("서버에서 연결이 종료되었습니다.")
        except Exception as e:
            if not self.is_stopping:  # 의도적인 종료가 아닌 경우에만 에러 메시지 표시
                self.connection_status.emit(f"채팅 수신 오류: {str(e)}")

    def decode_message(self, bytes):
        try:
            parts = bytes.split(b'\x0c')
            messages = [part.decode('utf-8', errors='ignore') for part in parts]  # 디코딩 오류 방지
            
            if len(messages) > 6:
                user_id = messages[2] if len(messages) > 2 else "unknown"
                comment = messages[1] if len(messages) > 1 else "no message"
                user_nickname = messages[6] if len(messages) > 6 else "unknown"
                
                # 특정 ID 파악 로직 개선 - 괄호 형식(예: not15987(2))도 인식하도록 함
                allowed_base_ids = ["not15987", "notjjae919"]
                
                # 괄호와 숫자를 제거한 기본 아이디 추출
                import re
                base_user_id = re.sub(r'\(\d+\)$', '', user_id)
                
                # 허용된 기본 아이디 중 하나로 시작하는지 확인
                is_allowed = any(base_user_id == allowed_id for allowed_id in allowed_base_ids)
                
                # 허용된 ID인 경우에만 메시지 처리
                if is_allowed:
                    if comment not in ['-1', '1'] and '|' not in comment and 'fw=' not in comment:
                        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        chat_message = f"[{current_time}] {user_nickname}[{user_id}] - {comment}"
                        
                        # 명령어 처리 로직
                        try:
                            # !완료 X킬 명령어 처리
                            if "!완료" in comment:
                                kill_text = comment.replace("!완료", "").strip()
                                
                                # 숫자+킬 패턴 추출
                                import re
                                pattern = r'([+\-]?\d+)[\s]*킬'
                                matches = re.findall(pattern, kill_text)
                                
                                if matches:
                                    kill_count = int(matches[0])
                                    kill_command = f"CMD:COMPLETE_KILL:{kill_count}"
                                    self.message_received.emit(chat_message)
                                    self.message_received.emit(kill_command)
                                    return
                            
                            # !추가 X킬 명령어 처리
                            elif "!추가" in comment:
                                kill_text = comment.replace("!추가", "").strip()
                                
                                # 숫자+킬 패턴 추출
                                import re
                                pattern = r'([+\-]?\d+)[\s]*킬'
                                matches = re.findall(pattern, kill_text)
                                
                                if matches:
                                    kill_count = int(matches[0])
                                    kill_command = f"CMD:ADD_TARGET:{kill_count}"
                                    self.message_received.emit(chat_message)
                                    self.message_received.emit(kill_command)
                                    return
                        except Exception as e:
                            error_msg = f"[{current_time}] 명령어 처리 오류: {str(e)} (메시지: {comment})"
                            self.message_received.emit(error_msg)
                            
                        # 일반 메시지 전송
                        self.message_received.emit(chat_message)
        except Exception as e:
            self.connection_status.emit(f"메시지 디코딩 오류: {str(e)}")


    def stop(self):
        """스레드 안전하게 종료하는 메서드"""
        self.is_stopping = True  # 먼저 종료 플래그 설정
        self.running = False


class AfreecaHelperGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.bridge = WebBridge()
        self.bridge.donationReceived.connect(self.add_donation_log)
        self.is_minimized = False
        self.current_url = ""
        self.chat_url = ""
        self.donation_history = ""
        self.summary_content = ""
        self.chat_history = ""
        self.chat_worker = None
        
        # 설정 파일 경로
        self.settings_file = os.path.join(get_executable_dir(), "settings.json")
        self.load_settings()
        
        self.init_ui()
        self.setup_web_view()
        
        timer = QTimer()
        timer.singleShot(1000, lambda: self.check_for_updates(silent=True))
        
    def check_for_updates(self, silent=True):
        """업데이트 확인 및 다운로드"""
        config_path = os.path.join(get_executable_dir(), "updater_config.json")
        check_updater = True
        
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    check_updater = config.get("check_on_startup", True)
            except:
                pass
            
        if check_updater or not silent:
            auto_updater.check_for_updates(self, silent)

    def load_settings(self):
        """저장된 설정을 불러옵니다."""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.current_url = settings.get('donation_url', '')
                    self.chat_url = settings.get('chat_url', '')
            else:
                self.current_url = ''
                self.chat_url = ''
        except Exception as e:
            print(f"설정 불러오기 오류: {e}")
            self.current_url = ''
            self.chat_url = ''

    def save_settings(self):
        """현재 설정을 저장합니다."""
        try:
            settings = {
                'donation_url': self.current_url,
                'chat_url': self.chat_url
            }
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"설정 저장 오류: {e}")

    def setup_web_view(self):
        # PyQt6에서는 페이지에 설정을 적용하는 방식이 변경됨
        self.page = DonationWebPage(self.bridge, self.web_view)
        self.web_view.setPage(self.page)
        
        # QWebEngineSettings를 가져오는 방식 변경
        settings = self.page.settings()
        # PyQt6에서는 WebAttribute enum을 사용
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)

    def init_ui(self):
        self.setWindowTitle('아프리카 도우미')
        self.setGeometry(100, 100, 900, 700)
        self.setMinimumSize(900, 200)
        
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setSpacing(8)
        self.main_layout.setContentsMargins(8, 8, 8, 8)

        self.main_widget.setStyleSheet(f"background-color: {LIGHT_PURPLE};")
        
        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)
        
        self.full_widget = QWidget()
        self.minimized_widget = QWidget()
        
        self.stacked_widget.addWidget(self.full_widget)
        self.stacked_widget.addWidget(self.minimized_widget)
        
        self.create_full_ui()
        self.create_minimized_ui()
        
        self.stacked_widget.setCurrentWidget(self.full_widget)

    def create_full_ui(self):
        full_layout = QVBoxLayout(self.full_widget)
        full_layout.setSpacing(8)
        full_layout.setContentsMargins(8, 8, 8, 8)
        
        # 헤더 영역
        header_layout = self.create_header_layout()
        full_layout.addLayout(header_layout)
        
        # URL 입력 영역들을 탭으로 구성
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 2px solid {BORDER_PURPLE};
                border-radius: 5px;
                background-color: {MEDIUM_PURPLE};
                top: -1px;
                padding: 5px;
            }}
            QTabBar::tab {{
                background-color: {MEDIUM_PURPLE};
                border: 2px solid {BORDER_PURPLE};
                border-bottom: none;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                padding: 8px 15px;
                margin-right: 5px;
                color: {TEXT_COLOR};
            }}
            QTabBar::tab:selected {{
                background-color: {ACCENT_PURPLE};
                color: white;
            }}
            QTabBar::tab:hover:!selected {{
                background-color: #eca1a3;
            }}
        """)
        
        # 후원 알림 탭
        donation_tab = QWidget()
        donation_tab_layout = QVBoxLayout(donation_tab)
        donation_tab_layout.setContentsMargins(10, 10, 10, 10)
        donation_url_layout = self.create_donation_url_layout()
        donation_tab_layout.addLayout(donation_url_layout)
        tabs.addTab(donation_tab, "후원 알림 설정")
        
        # 채팅 기록 탭
        chat_tab = QWidget()
        chat_tab_layout = QVBoxLayout(chat_tab)
        chat_tab_layout.setContentsMargins(10, 10, 10, 10)
        chat_url_layout = self.create_chat_url_layout()
        chat_tab_layout.addLayout(chat_url_layout)
        tabs.addTab(chat_tab, "채팅 기록 설정")
        
        # 메인 레이아웃에 탭 추가
        full_layout.addWidget(tabs)
        
        # 메인 컨텐츠 영역
        content_splitter = self.create_content_area()
        full_layout.addWidget(content_splitter)
    
    def reset_kills(self):
        """완료 킬수와 목표 킬수를 모두 0으로 초기화합니다."""
        # 초기화 전 값 저장
        prev_completed = self.bridge.completed_kills
        prev_target = self.bridge.target_kills
        
        # 킬수 초기화
        self.bridge.completed_kills = 0
        self.bridge.target_kills = 0
        
        # 시간 기록
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 로그 메시지 생성
        reset_message = f"[{current_time}] 킬수 초기화: 완료 킬수 {prev_completed}→0, 목표 킬수 {prev_target}→0"
        
        # 채팅 로그에 추가
        self.chat_log.append(reset_message)
        self.chat_history = self.chat_log.toPlainText()
        
        # 요약 업데이트
        self.update_summary()
        
        # 미니모드일 경우 오버레이 텍스트도 업데이트
        if self.is_minimized:
            self.update_overlay_text()
        
        # 데이터 저장
        self.bridge.save_data()

    def create_header_layout(self):
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        self.minimize_btn = QPushButton("요약")
        self.minimize_btn.setFixedSize(80, 40)
        self.minimize_btn.setStyleSheet(self.get_button_style())
        self.minimize_btn.clicked.connect(self.toggle_ui)

        settings_label = QLabel("설정")
        settings_label.setStyleSheet(self.get_label_style())
        # PyQt6에서는 enum을 사용하여 정렬 방식 지정
        settings_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        settings_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)  # Policy enum 사용
        settings_label.setFixedHeight(40)
        
        # 초기화 버튼
        reset_button = QPushButton("초기화")
        reset_button.setFixedWidth(80)
        reset_button.setFixedHeight(40)
        reset_button.setStyleSheet(self.get_button_style())
        reset_button.clicked.connect(self.reset_kills)
        
        # 업데이트 버튼 추가
        update_button = QPushButton("업데이트")
        update_button.setFixedWidth(80)
        update_button.setFixedHeight(40)
        update_button.setStyleSheet(self.get_button_style())
        update_button.clicked.connect(lambda: self.check_for_updates(silent=False))

        header_layout.addWidget(self.minimize_btn)
        header_layout.addWidget(settings_label)
        header_layout.addWidget(reset_button)
        header_layout.addWidget(update_button)  # 헤더 레이아웃에 업데이트 버튼 추가
        
        return header_layout

    def create_donation_url_layout(self):
        url_layout = QHBoxLayout()
        url_layout.setContentsMargins(5, 5, 5, 5)  # 여백 추가
        url_layout.setSpacing(10)  # 구성 요소 간 간격 설정
        
        url_label = QPushButton("후원 알림 URL")
        url_label.setStyleSheet(self.get_button_style())
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("위플랩 후원 URL을 입력하세요")
        self.url_input.setStyleSheet(self.get_input_style())
        if self.current_url:
            self.url_input.setText(self.current_url)
        
        self.connect_btn = QPushButton("연결")
        self.connect_btn.setStyleSheet(self.get_button_style())
        self.connect_btn.clicked.connect(self.load_overlay)
        
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.connect_btn)
        
        return url_layout

    def create_chat_url_layout(self):
        url_layout = QHBoxLayout()
        url_layout.setContentsMargins(5, 5, 5, 5)  # 여백 추가
        url_layout.setSpacing(10)  # 구성 요소 간 간격 설정
        
        url_label = QPushButton("방송 URL")
        url_label.setStyleSheet(self.get_button_style())
        
        self.chat_url_input = QLineEdit()
        self.chat_url_input.setPlaceholderText("https://play.sooplive.co.kr/으로 시작하는 생방송 링크를 입력하세요")
        self.chat_url_input.setStyleSheet(self.get_input_style())
        if self.chat_url:
            self.chat_url_input.setText(self.chat_url)
        
        self.chat_connect_btn = QPushButton("연결")
        self.chat_connect_btn.setStyleSheet(self.get_button_style())
        self.chat_connect_btn.clicked.connect(self.toggle_chat_connection)
        
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.chat_url_input)
        url_layout.addWidget(self.chat_connect_btn)
        
        return url_layout

    def create_content_area(self):
        # 전체 컨테이너를 담을 그리드 레이아웃 사용
        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(10)
        
        # 상단 영역 (후원 알림, 요약)
        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)
        
        # 후원 알림 영역
        alert_container = self.create_container("후원알림")
        alert_layout = alert_container.layout()
        self.web_view = QWebEngineView()
        alert_layout.addWidget(self.web_view)
        
        # 요약 영역
        summary_container = self.create_container("요약")
        summary_layout = summary_container.layout()
        self.summary_text = QTextEdit()
        self.summary_text.setStyleSheet(self.get_text_edit_style())
        self.summary_text.setReadOnly(True)
        if self.summary_content:
            self.summary_text.setText(self.summary_content)
        summary_layout.addWidget(self.summary_text)
        
        # 상단 두 컨테이너 추가 (2:1 비율)
        top_layout.addWidget(alert_container, 1)
        top_layout.addWidget(summary_container, 1)
        
        # 하단 영역 (후원내역, 채팅내역)
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)
        
        # 후원내역 영역
        history_container = self.create_container("후원내역")
        history_layout = history_container.layout()
        self.donation_log = QTextEdit()
        self.donation_log.setStyleSheet(self.get_text_edit_style())
        self.donation_log.setReadOnly(True)
        if self.donation_history:
            self.donation_log.setText(self.donation_history)
        history_layout.addWidget(self.donation_log)
        
        # 채팅내역 영역
        chat_container = self.create_container("채팅내역")
        chat_layout = chat_container.layout()
        self.chat_log = QTextEdit()
        self.chat_log.setStyleSheet(self.get_text_edit_style())
        self.chat_log.setReadOnly(True)
        if self.chat_history:
            self.chat_log.setText(self.chat_history)
        chat_layout.addWidget(self.chat_log)
        
        # 하단 두 컨테이너 추가 (1:1 비율)
        bottom_layout.addWidget(history_container, 1)
        bottom_layout.addWidget(chat_container, 1)
        
        # 상단과 하단 레이아웃을 메인 레이아웃에 추가 (1:1 비율)
        main_layout.addLayout(top_layout, 1)
        main_layout.addLayout(bottom_layout, 1)
        
        return main_container

    def create_minimized_ui(self):
        if self.minimized_widget.layout():
            self.clear_layout(self.minimized_widget.layout())
            QWidget().setLayout(self.minimized_widget.layout())
            
        minimized_layout = QVBoxLayout(self.minimized_widget)
        minimized_layout.setSpacing(2)
        minimized_layout.setContentsMargins(8, 4, 8, 4)

        # 상단 영역
        top_layout = QHBoxLayout()
        
        self.expand_btn = QPushButton("+")
        self.expand_btn.setFixedSize(40, 40)
        self.expand_btn.setStyleSheet(self.get_button_style())
        self.expand_btn.clicked.connect(self.toggle_ui)

        donation_label = QLabel("후원 내역")
        donation_label.setStyleSheet(self.get_label_style())
        donation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # PyQt6 열거형 사용
        donation_label.setFixedSize(400, 40)  # 너비 400, 높이 40으로 설정

        top_layout.addWidget(self.expand_btn)
        top_layout.addWidget(donation_label)
        minimized_layout.addLayout(top_layout)

        # 이미지 영역
        image_container = self.create_image_container()
        minimized_layout.addWidget(image_container)
        
        # 킬수 수정 영역
        kills_buttons_layout = QHBoxLayout()
        kills_buttons_layout.setSpacing(1)
        
        # 완료 킬수 수정 영역
        complete_kills_layout = QHBoxLayout()
        complete_kills_layout.setSpacing(1)
        
        # 완료 수정 레이블
        complete_kills_label = QLabel("완료 추가")
        complete_kills_label.setStyleSheet(f"""
            QLabel {{
                background-color: {LIGHT_PURPLE};
                border: 2px solid {BORDER_PURPLE};
                border-radius: 15px;
                padding: 5px;
                color: {TEXT_COLOR};
                font-weight: bold;
            }}
        """)
        complete_kills_label.setFixedHeight(40)
        
        # 킬수 입력 필드
        self.complete_kills_input = QLineEdit()
        self.complete_kills_input.setPlaceholderText("추가할 킬 수를 입력해 주세요")
        self.complete_kills_input.setStyleSheet(self.get_input_style())
        
        # 추가 버튼
        complete_kills_btn = QPushButton("추가")
        complete_kills_btn.setStyleSheet(self.get_button_style())
        complete_kills_btn.clicked.connect(self.add_complete_kills)
        
        # 레이아웃에 위젯 추가
        complete_kills_layout.addWidget(complete_kills_label)
        complete_kills_layout.addWidget(self.complete_kills_input)
        complete_kills_layout.addWidget(complete_kills_btn)
        
        # 목표 킬수 수정 영역
        target_kills_layout = QHBoxLayout()
        target_kills_layout.setSpacing(4)
        
        # 목표 수정 레이블
        target_kills_label = QLabel("목표 추가")
        target_kills_label.setStyleSheet(f"""
            QLabel {{
                background-color: {LIGHT_PURPLE};
                border: 2px solid {BORDER_PURPLE};
                border-radius: 15px;
                padding: 5px;
                color: {TEXT_COLOR};
                font-weight: bold;
            }}
        """)
        target_kills_label.setFixedHeight(40)
        
        # 킬수 입력 필드
        self.target_kills_input = QLineEdit()
        self.target_kills_input.setPlaceholderText("추가할 킬 수를 입력해 주세요")
        self.target_kills_input.setStyleSheet(self.get_input_style())
        
        # 추가 버튼
        target_kills_btn = QPushButton("추가")
        target_kills_btn.setStyleSheet(self.get_button_style())
        target_kills_btn.clicked.connect(self.add_target_kills)
        
        # 레이아웃에 위젯 추가
        target_kills_layout.addWidget(target_kills_label)
        target_kills_layout.addWidget(self.target_kills_input)
        target_kills_layout.addWidget(target_kills_btn)
        
        # 메인 레이아웃에 버튼 영역 추가
        minimized_layout.addLayout(complete_kills_layout)
        minimized_layout.addLayout(target_kills_layout)

    def add_complete_kills(self):
        """완료 킬수 조정 버튼 이벤트 핸들러"""
        try:
            # 입력 텍스트 가져오기
            kill_text = self.complete_kills_input.text().strip()
            
            # 비어있는 경우 무시
            if not kill_text:
                return
                
            # 숫자 검증 (+/- 기호 허용)
            if kill_text.startswith('+'):
                kill_count = int(kill_text[1:])
            elif kill_text.startswith('-'):
                kill_count = -int(kill_text[1:])
            else:
                kill_count = int(kill_text)
                
            # 완료 킬수 업데이트
            self.bridge.completed_kills += kill_count
            
            # 음수가 되지 않도록 방지
            if self.bridge.completed_kills < 0:
                self.bridge.completed_kills = 0
                
            # 시간 기록
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 로그 메시지 생성
            if kill_count >= 0:
                log_message = f"[{current_time}] 완료 킬수 {kill_count}킬 추가. 현재 완료: {self.bridge.completed_kills}킬"
            else:
                log_message = f"[{current_time}] 완료 킬수 {abs(kill_count)}킬 감소. 현재 완료: {self.bridge.completed_kills}킬"
                
            # 채팅 로그에 추가
            self.chat_log.append(log_message)
            
            # 입력 필드 초기화
            self.complete_kills_input.clear()
            
            # 요약 업데이트
            self.update_summary()
            
            # 데이터 저장
            self.bridge.save_data()
            
        except ValueError:
            # 숫자가 아닌 입력에 대한 처리
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.chat_log.append(f"[{current_time}] 오류: 유효한 숫자를 입력해주세요.")
            self.complete_kills_input.clear()

    def add_target_kills(self):
        """목표 킬수 조정 버튼 이벤트 핸들러"""
        try:
            # 입력 텍스트 가져오기
            kill_text = self.target_kills_input.text().strip()
            
            # 비어있는 경우 무시
            if not kill_text:
                return
                
            # 숫자 검증 (+/- 기호 허용)
            if kill_text.startswith('+'):
                kill_count = int(kill_text[1:])
            elif kill_text.startswith('-'):
                kill_count = -int(kill_text[1:])
            else:
                kill_count = int(kill_text)
                
            # 목표 킬수 업데이트
            self.bridge.target_kills += kill_count
            
            # 음수가 되지 않도록 방지
            if self.bridge.target_kills < 0:
                self.bridge.target_kills = 0
                
            # 시간 기록
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 로그 메시지 생성
            if kill_count >= 0:
                log_message = f"[{current_time}] 목표 킬수 {kill_count}킬 추가. 현재 목표: {self.bridge.target_kills}킬"
            else:
                log_message = f"[{current_time}] 목표 킬수 {abs(kill_count)}킬 감소. 현재 목표: {self.bridge.target_kills}킬"
                
            # 채팅 로그에 추가
            self.chat_log.append(log_message)
            
            # 입력 필드 초기화
            self.target_kills_input.clear()
            
            # 요약 업데이트
            self.update_summary()
            
            # 데이터 저장
            self.bridge.save_data()
            
        except ValueError:
            # 숫자가 아닌 입력에 대한 처리
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.chat_log.append(f"[{current_time}] 오류: 유효한 숫자를 입력해주세요.")
            self.target_kills_input.clear()

    def create_image_container(self):
        image_container = QWidget()
        image_container.setStyleSheet("""
            QWidget {
                background-color: white;
                border: none;
                border-radius: 15px;
            }
        """)
        image_container.setFixedSize(438, 320)
        
        self.minimized_image = QLabel(image_container)
        
        # 이미지 경로 처리 개선
        # cx_Freeze는 sys.frozen 속성을 설정하지만 sys._MEIPASS는 사용하지 않음
        if getattr(sys, 'frozen', False):
            # exe로 실행될 때 (cx_Freeze로 패키징 된 경우)
            # cx_Freeze는 파일을 exe와 같은 디렉토리에 추출함
            base_dir = os.path.dirname(sys.executable)
            image_path = os.path.join(base_dir, "resources", "damew_roulette.png")
        else:
            # 일반 스크립트로 실행될 때
            image_path = os.path.join(get_executable_dir(), "resources", "damew_roulette.png")
        
        try:
            # 디버깅 정보 출력
            print(f"실행 디렉토리: {get_executable_dir()}")
            print(f"이미지 경로 시도: {image_path}")
            print(f"이미지 파일 존재 여부: {os.path.exists(image_path)}")
            
            if os.path.exists(image_path):
                pixmap = QPixmap(image_path)
                # PyQt6에서는 KeepAspectRatio 등 상수가 다른 위치로 이동
                scaled_pixmap = pixmap.scaled(484, 320, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
                self.minimized_image.setPixmap(scaled_pixmap)
            else:
                print(f"ERROR: 이미지 파일을 찾을 수 없습니다: {image_path}")
                # 대체 텍스트 설정
                self.minimized_image.setText("이미지를 찾을 수 없습니다")
                self.minimized_image.setStyleSheet("QLabel { color: red; font-size: 16px; background: white; }")
                self.minimized_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
                
        except Exception as e:
            print(f"ERROR: 이미지 로딩 중 오류 발생: {str(e)}")
            self.minimized_image.setText("이미지 로딩 오류")
            self.minimized_image.setStyleSheet("QLabel { color: red; font-size: 16px; background: white; }")
            self.minimized_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.minimized_image.setGeometry(0, 0, 484, 320)
        
        # 오버레이 레이블
        self.overlay_labels = {}
        overlay_positions = {
            'label1': (78, 205, 100, 30), #X, Y, 너비, 높이
            'label2': (263, 205, 100, 30),
            'label3': (263, 255, 100, 30)
        }
        
        for label_id, (x, y, w, h) in overlay_positions.items():
            label = QLabel(image_container)
            label.setStyleSheet("""
                QLabel {
                    color: #ffa0a0;
                    font-size: 24px;
                    font-weight: bold;
                    background: transparent;
                    border: none;
                    padding: 2px;
                }
            """)
            label.setGeometry(x, y, w, h)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # PyQt6 열거형 사용
            self.overlay_labels[label_id] = label

        return image_container
        
    def get_button_style(self):
        return f"""
            QPushButton {{
                background-color: {MEDIUM_PURPLE};
                border: 2px solid {BORDER_PURPLE};
                border-radius: 15px;
                padding: 8px;
                color: {TEXT_COLOR};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {ACCENT_PURPLE};
                color: white;
            }}
        """

    def get_label_style(self):
        return f"""
            QLabel {{
                background-color: {MEDIUM_PURPLE};
                border: 2px solid {BORDER_PURPLE};
                border-radius: 15px;
                padding: 5px;
                color: {TEXT_COLOR};
                font-weight: bold;
            }}
        """

    def get_input_style(self):
        return f"""
            QLineEdit {{
                background-color: white;
                border: 2px solid {BORDER_PURPLE};
                border-radius: 15px;
                padding: 8px 15px;
                margin: 2px;
                color: {TEXT_COLOR};
            }}
            QLineEdit:focus {{
                border: 2px solid {ACCENT_PURPLE};
            }}
        """

    def get_text_edit_style(self):
        return """
            QTextEdit {
                background-color: white;
                color: #374151;
                border: none;
                padding: 5px;
                font-family: '맑은 고딕';
            }
        """

    def create_container(self, title):
        container = QWidget()
        container.setStyleSheet(f"""
            QWidget {{
                background-color: {MEDIUM_PURPLE};
                border: 2px solid {BORDER_PURPLE};
                border-radius: 15px;
            }}
        """)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        label = QLabel(title)
        label.setStyleSheet(f"""
            QLabel {{
                background-color: white;
                border: 2px solid {BORDER_PURPLE};
                border-radius: 15px;
                padding: 5px;
                color: {TEXT_COLOR};
                font-weight: bold;
            }}
        """)
        
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # PyQt6 열거형 사용
        label.setFixedHeight(40)
        layout.addWidget(label)
        
        return container
        

    def load_overlay(self):
        url = self.url_input.text().strip()
        if not url:
            return
            
        if not url.startswith('http://') and not url.startswith('https://'):
            url = 'https://' + url
            
        try:
            self.web_view.setUrl(QUrl(url))
            self.add_donation_log("=== URL 로딩 시작 ===")
            self.add_donation_log(url)
            self.current_url = url
            self.save_settings()
            
        except Exception as e:
            error_msg = f"URL 로딩 오류: {str(e)}"
            self.add_donation_log(error_msg)

    def toggle_chat_connection(self):
        if self.chat_worker is None:
            url = self.chat_url_input.text().strip()
            if not url:
                self.add_chat_log("방송 URL을 입력해주세요.")
                return

            if not url.startswith('http://') and not url.startswith('https://'):
                url = 'https://' + url
                
            self.chat_url = url
            self.save_settings()
            
            self.add_chat_log("=== 채팅 연결 시작 ===")
            self.chat_worker = ChatWorker(url)
            self.chat_worker.message_received.connect(self.add_chat_log)
            self.chat_worker.connection_status.connect(self.add_chat_log)
            self.chat_worker.start()
            
            self.chat_connect_btn.setText("연결 종료")
            self.chat_connect_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #e74c3c;
                    border: 2px solid {BORDER_PURPLE};
                    border-radius: 15px;
                    padding: 8px;
                    color: white;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: #c0392b;
                }}
            """)
            
        else:
            self.chat_worker.stop()
            self.chat_worker.quit()  # 스레드 종료 신호 전송
            self.chat_worker.wait(1000)  # 최대 1초 대기
            
            # 시간 초과 후에도 스레드가 실행 중이면 강제 종료 방지
            self.chat_worker = None
            
            self.add_chat_log("=== 채팅 연결 종료 ===")
            self.chat_connect_btn.setText("연결")
            self.chat_connect_btn.setStyleSheet(self.get_button_style())

    def update_overlay_text(self):
        if not hasattr(self, 'overlay_labels'):
            return

        completed_kills = self.bridge.completed_kills
        target_kills = self.bridge.target_kills
        left_kills = target_kills - completed_kills
        
        if 'label1' in self.overlay_labels:
            self.overlay_labels['label1'].setText(f"{completed_kills:,}")
        if 'label2' in self.overlay_labels:
            self.overlay_labels['label2'].setText(f"{target_kills:,}")
        if 'label3' in self.overlay_labels:
            self.overlay_labels['label3'].setText(f"{left_kills:,}")

    def add_donation_log(self, text):
        self.donation_log.append(text)
        self.donation_history = self.donation_log.toPlainText()
        
        # PyQt6에서의 스크롤바 접근 방식은 동일함
        self.donation_log.verticalScrollBar().setValue(
            self.donation_log.verticalScrollBar().maximum()
        )
        
        # 마지막 룰렛 결과 추가
        last_roulette_result = ""
        if text.startswith("[") and "룰렛 결과:" in text:
            last_roulette_result = text.split("룰렛 결과:")[1].strip()
        
        # 요약 업데이트
        self.update_summary()
        
        # 마지막 룰렛 결과가 있으면 요약에 추가
        if last_roulette_result:
            self.summary_text.append(f"\n마지막 룰렛 결과: {last_roulette_result}")
            self.summary_content = self.summary_text.toPlainText()
        
        # 데이터 저장
        self.bridge.save_data()

    def add_chat_log(self, text):
        # 명령어 메시지 처리
        if text.startswith("CMD:"):
            parts = text.split(":")
            if len(parts) >= 3:
                cmd_type = parts[1]
                cmd_value = int(parts[2])
                
                if cmd_type == "COMPLETE_KILL":
                    # 완료 킬수 업데이트
                    self.bridge.completed_kills += cmd_value
                    # 음수가 되지 않도록 방지
                    if self.bridge.completed_kills < 0:
                        self.bridge.completed_kills = 0
                    
                    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    if cmd_value >= 0:
                        log_message = f"[{current_time}] 완료 킬수 {cmd_value}킬 추가. 현재 완료: {self.bridge.completed_kills}킬"
                    else:
                        log_message = f"[{current_time}] 완료 킬수 {abs(cmd_value)}킬 감소. 현재 완료: {self.bridge.completed_kills}킬"
                    
                    # 로그에 추가하고 요약 업데이트
                    self.chat_log.append(log_message)
                    self.update_summary()
                    # 데이터 저장
                    self.bridge.save_data()
                    return
                    
                elif cmd_type == "ADD_TARGET":
                    # 목표 킬수 업데이트
                    self.bridge.target_kills += cmd_value
                    # 음수가 되지 않도록 방지
                    if self.bridge.target_kills < 0:
                        self.bridge.target_kills = 0
                        
                    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    if cmd_value >= 0:
                        log_message = f"[{current_time}] 목표 킬수 {cmd_value}킬 추가. 현재 목표: {self.bridge.target_kills}킬"
                    else:
                        log_message = f"[{current_time}] 목표 킬수 {abs(cmd_value)}킬 감소. 현재 목표: {self.bridge.target_kills}킬"
                    
                    # 로그에 추가하고 요약 업데이트
                    self.chat_log.append(log_message)
                    self.update_summary()
                    # 데이터 저장
                    self.bridge.save_data()
                    return
        
        # 일반 채팅 메시지 처리
        self.chat_log.append(text)
        self.chat_history = self.chat_log.toPlainText()
        
        self.chat_log.verticalScrollBar().setValue(
            self.chat_log.verticalScrollBar().maximum()
        )

    def update_summary(self):
        """요약 정보와 오버레이 텍스트를 업데이트합니다."""
        # 남은 킬수 계산
        remaining_kills = self.bridge.target_kills - self.bridge.completed_kills
        
        # 요약 텍스트 업데이트
        summary = f"""총 후원 횟수: {self.bridge.donation_count:,}회
    총 별풍선: {self.bridge.total_amount:,}개
    완료 킬수: {self.bridge.completed_kills:,}킬
    목표 킬수: {self.bridge.target_kills:,}킬
    남은 킬수: {remaining_kills:,}킬"""

        self.summary_text.setText(summary)
        self.summary_content = summary
        
        # 미니모드일 경우 오버레이 텍스트도 업데이트
        if self.is_minimized:
            self.update_overlay_text()

    def toggle_ui(self):
        self.is_minimized = not self.is_minimized
        if self.is_minimized:
            self.stacked_widget.setCurrentWidget(self.minimized_widget)
            # 축소 모드 창 크기 조정 - 버튼 추가로 세로 길이 증가
            self.setFixedSize(473, 500)  # 세로 길이 기존 400에서 540으로 증가
            self.update_overlay_text()
        else:
            self.setMinimumSize(900, 700)
            self.resize(900, 700)  # 윈도우 크기 복원
            self.stacked_widget.setCurrentWidget(self.full_widget)
            if self.current_url:
                self.url_input.setText(self.current_url)
            if self.chat_url:
                self.chat_url_input.setText(self.chat_url)

    def clear_layout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
                if item.layout():
                    self.clear_layout(item.layout())
                    
    def closeEvent(self, event):
        """프로그램 종료 시 호출되는 이벤트"""
        
        # 채팅 연결이 활성화되어 있다면 종료
        if self.chat_worker is not None:
            self.chat_worker.stop()
            self.chat_worker.quit()
            self.chat_worker.wait(1000)  # 최대 1초 대기
            self.chat_worker = None
        
        # 데이터 저장
        self.bridge.save_data()
        
        # 현재 설정 저장
        self.save_settings()
        
        event.accept()

def main():
    app = QApplication(sys.argv)
    font = QFont("맑은 고딕", 10)
    app.setFont(font)
    window = AfreecaHelperGUI()
    window.show()
    sys.exit(app.exec())  # PyQt6에서는 exec_() 대신 exec()를 사용

if __name__ == '__main__':
    main()