import socket
from threading import Lock, Thread
import time
from RailLibrary import RailAlarm, RailCheck, RailPacket, RailConstant, RailMotion
import traceback


class RailSocket:
    """
    Docstring for RailSocket
    """

    def __init__(self, ip: str, port: int, timeout: float = 3.0, use_real_robot=False):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.sock = None
        self.sync_no = 0
        self._lock = Lock()
        self.use_real_robot = use_real_robot
        self.socket_buffer_size = 1024
        self.current_position = 0
        self.thread = Thread(target=self.update_position_loop, daemon=True)
    def connect(self):
        """
        소켓 연결
        """ 
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.ip, self.port))
        self.init_sequence()

    def disconnect(self):
        """
        소켓 연결 해제
        """
        if self.sock:
            try:
                self.sock.close()
                self.thread.join(timeout=1.0)
            except Exception:
                pass
            self.sock = None
    def send(self, data: bytes):
        """
        데이터 전송
        """
        with self._lock:
            if not self.sock:
                raise RuntimeError("Socket is not connected.")
            self.sock.sendall(data)
    def receive(self) -> bytes:
        """
        데이터 수신
        """
        with self._lock:
            if not self.sock:
                raise RuntimeError("Socket is not connected.")
            return self.sock.recv(self.socket_buffer_size)
    def send_and_receive(self, data: bytes) -> bytes:
        """
        데이터 전송 후 응답 수신
        """
        with self._lock:
            if not self.sock:
                raise RuntimeError("Socket is not connected.")
            self.sock.sendall(data)
            return self.sock.recv(self.socket_buffer_size)
    def _raise_sync(self) -> int:
        """
        ✅ 원본 raise_sync_number와 동일하게:
        - 255면 0으로 리셋 후 +1 => 1
        - 즉 결과는 1~255만 나옴(0 안 씀)
        """
        if self.sync_no == 0xFF:
            self.sync_no = 0
        self.sync_no += 1
        return self.sync_no

    def _make_packet(self, length, command, set=None, extra=None, init=None):
        """
        기존 make_packet()과 동작/구조 동일:
        - set: [HEADER, length, sync, RESERVED, command, set]
        - extra: [HEADER, length, sync, RESERVED, command] + extra(list[int])
        - init:  [HEADER, length, sync, RESERVED, command] + [init[0]] + init[1](bytes/bytearray)
        - else:  [HEADER, length, sync, RESERVED, command]
        반환: bytearray
        """
        data = None
        try:
            if set is not None:
                data = bytearray([
                    RailPacket.HEADER,
                    length,
                    self._raise_sync_compat(),   # ✅ 아래 함수 참고
                    RailPacket.RESERVED,
                    command,
                    set
                ])

            elif extra is not None:
                base = [RailPacket.HEADER, length, self._raise_sync_compat(), RailPacket.RESERVED, command] + list(extra)
                data = bytearray(base)

            elif init is not None:
                base = [RailPacket.HEADER, length, self._raise_sync_compat(), RailPacket.RESERVED, command]
                base.append(init[0])
                base.extend(bytearray(init[1]))
                data = bytearray(base)

            else:
                data = bytearray([RailPacket.HEADER, length, self._raise_sync_compat(), RailPacket.RESERVED, command])

        except Exception:
            # logger가 없을 수도 있으니 안전하게 처리
            print("[BREW][RAIL][ERR] make_packet failed")
            print(traceback.format_exc())
            data = None
        finally:
            return data
    def _raise_sync_compat(self) -> int:
        """
        기존 raise_sync_number()와 동일:
        - 1씩 증가
        - 256이면 0으로 롤오버 (즉 0~255 사용 가능)
        """
        self.sync_no += 1
        if self.sync_no == 256:
            self.sync_no %= 256
        return self.sync_no

    def _send_and_recv(self, pkt: bytes, min_resp_len: int = 6) -> bytes:
        self.connect(do_init=False)
        with self._lock:
            self.sock.sendall(pkt)

            # ✅ 최소 길이만큼 누적 수신 (TCP 분할 대비)
            buf = bytearray()
            while len(buf) < min_resp_len:
                buf.extend(self._recv_some())
            return bytes(buf)

    def _recv_some(self) -> bytes:
        if not self.sock:
            raise RuntimeError("rail socket is not connected")
        chunk = self.sock.recv(self.socket_buffer_size)
        if not chunk:
            raise ConnectionError("rail socket closed by peer")
        return chunk
    
    def _check_idle_or_raise(self, resp: bytes, label: str):
        if resp is None or len(resp) < 6:
            raise RuntimeError(f"rail response too short ({label}): {list(resp) if resp else resp}")

        idx = 5

        status = resp[idx]
        if status != RailCheck.IDLE:
            print(f"[BREW][RAIL][WARN] rail cmd failed ({label}): status={status}, resp={list(resp)}")
            return status
            # raise RuntimeError(f"rail cmd failed ({label}): status={status}, resp={list(resp)}")
        return status
    
    # -------------------------
    # low-level getters
    # -------------------------
    def get_motion_bits(self) -> int:
        pkt = self._make_packet(length=RailPacket.GET_DATA, command=RailPacket.GET_MOTION)
        resp = self._send_and_recv(pkt, min_resp_len=10)
        self._check_idle_or_raise(resp, "get_motion")
        return int.from_bytes(resp[6:10], "little", signed=False)

    def get_alarm_type_byte(self) -> int:
        pkt = self._make_packet(length=RailPacket.GET_DATA, command=RailPacket.GET_ALARM_TYPE)
        resp = self._send_and_recv(pkt, min_resp_len=7)
        self._check_idle_or_raise(resp, "get_alarm_type")
        return resp[6]

    def get_position_pulse(self) -> int:
        DATA_POS_START = 6
        DATA_POS_END = 10
        pkt = self._make_packet(length=RailPacket.GET_DATA, command=RailPacket.GET_POSITION)
        resp = self._send_and_recv(pkt, min_resp_len=10)
        self._check_idle_or_raise(resp, "get_position")
        return int.from_bytes(resp[DATA_POS_START:DATA_POS_END], "little", signed=False)

    def update_position_loop(self):
        self.thread.start()
        while(self.sock is not None):
            try:
                with self._lock:
                    pos = self.get_position_pulse()
                    self.current_position = pos
                    time.sleep(0.2)
            except Exception:
                time.sleep(0.5)
    # -------------------------
    # init sequence (원본 server_on 흐름과 유사)
    # -------------------------
    def init_sequence(self):
        # 0) EMG_STOP 방지 (원본에서 get_motioning으로 판단하던 부분 보강)
        try:
            bits = self.get_motion_bits()
            if (bits & 0x00010000) == 0x00010000:
                raise RuntimeError("Rail is in EMG_STOP. Release emergency stop then retry.")
        except Exception:
            pass

         # ✅ 1) alarm_type 먼저 확인해서, 알람 있을 때만 reset
        alarm_type = None
        last_err = None
        try:
            alarm_type = self.get_alarm_type_byte()
        except Exception:
            alarm_type = None

        if alarm_type not in (None, 0):
            
            for _ in range(3):
                try:
                    self.alarm_reset()
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    time.sleep(0.2)

            if last_err is not None:
                raise last_err
        else:
            # 알람 없음이면 reset 스킵 (134 뜨는 정상 케이스 방지)
            pass

        # 2) servo on
        self.servo_on(True)
        self.update_position_loop()

    # -------------------------
    # commands
    # -------------------------
    def alarm_reset(self):
        pkt = self._make_packet(length=RailPacket.GET_DATA, command=RailPacket.ALARM_RESET)
        resp = self._send_and_recv(pkt, min_resp_len=6)

        self._check_idle_or_raise(resp, "alarm_reset")
        return resp

    def servo_on(self, on: bool = True):
        pkt = self._make_packet(
            length=RailPacket.SET_DATA,
            command=RailPacket.SERVO_ON,
            set=RailPacket.SET_ON if on else RailPacket.SET_OFF,
        )
        resp = self._send_and_recv(pkt, min_resp_len=6)
        self._check_idle_or_raise(resp, f"servo_on({on})")
        return resp


    def move_pos_velocity(
        self,
        target_pulse: int,
        pps: int,
        acc_time: int = 750,
        dec_time: int = 750,
        acc_on: int = 1,
        dec_on: int = 1,
    ):
        """
        기존 move_position_Velocity()와 payload/packet 구성이 바이트 단위로 동일해야 함.
        - length: 0x2B
        - command: 0x80
        - payload:
            position(4, little) +
            pps(4, little) +
            flag_option(4, little) +
            acc_time(2, little) +
            dec_time(2, little) +
            fill(24, 0x00)
        """

        # 기존과 동일: to_bytes 길이/엔디안
        bytes_position = int(target_pulse).to_bytes(4, "little", signed=False)
        bytes_pps = int(pps).to_bytes(4, "little", signed=False)
        bytes_acc_time = int(acc_time).to_bytes(2, "little", signed=False)
        bytes_dec_time = int(dec_time).to_bytes(2, "little", signed=False)

        # 기존과 동일: flag_option = acc_on*ONE_BIT + dec_on*TWO_BIT
        # ONE_BIT=1<<1, TWO_BIT=1<<2
        flag_option = int(acc_on) * (1 << 1) + int(dec_on) * (1 << 2)
        bytes_flag = int(flag_option).to_bytes(4, "little", signed=False)

        # 기존과 동일: extra_value(list) 구성
        extra_value = (
            list(bytes_position)
            + list(bytes_pps)
            + list(bytes_flag)
            + list(bytes_acc_time)
            + list(bytes_dec_time)
            + list(bytes(RailPacket.FILLBYTE_LEN))  # 24 bytes of 0x00
        )

        payload = bytes(extra_value)

        # ✅ length는 반드시 0x2B 사용 (기존 DataLength.MOVE_DATA_LENGTH와 동일)
        pkt = self._make_packet(
        length=RailPacket.MOVE_DATA_LENGTH,     # 0x2b
        command=RailPacket.MOVE_POS_VELOCITY,
        extra=extra_value,                       # ✅ payload 대신 extra
        )

        resp = self._send_and_recv(pkt, min_resp_len=6)
        self._check_idle_or_raise(resp, "move_pos_velocity")
        return resp

    def move_to_pulse_and_wait(
        self,
        target_pulse: int,
        pps: int = 100000,
        tol: int = 50,
        timeout_s: float = 20.0,
        log_poll: bool = True,
        log_period_s: float = 0.5,
    ):
        """
        - (필요시) init에서 이미 alarm_reset + servo_on 완료
        - move 전송
        - position polling
        - ✅ "이미 목표 위치"인지 / "실제로 변화"가 있었는지 로그로 확인 가능
        """
        start = self.get_position_pulse()
        if abs(start - target_pulse) <= tol:
            if log_poll:
                print(f"[BREW][RAIL][POS] already at target: start={start}, target={target_pulse}, tol={tol}")
            return start

        self.move_pos_velocity(target_pulse, pps)

        t0 = time.time()
        last_log = 0.0
        last = None

        while True:
            with self._lock:
                curr = self.get_position_pulse()

                if log_poll and (time.time() - last_log) >= log_period_s:
                    print(f"[BREW][RAIL][POS] curr={curr}, target={target_pulse}, diff={curr-target_pulse}")
                    last_log = time.time()

                if abs(curr - target_pulse) <= tol:
                    return curr

                if (time.time() - t0) > timeout_s:
                    raise TimeoutError(f"rail move timeout: start={start}, target={target_pulse}, curr={curr}, last={last}")

                last = curr
                time.sleep(0.05)

        
class RailPacket:
    MOVE_DATA_LENGTH = 0x2B
    HEADER = 0xAA
    RESERVED = 0x00

    # commands
    GET_MOTION = 0x40
    GET_ALARM_TYPE = 0x2E
    ALARM_RESET = 0x2B
    SERVO_ON = 0x2A
    GET_POSITION = 0x53
    MOVE_POS_VELOCITY = 0x80

    # set values
    SET_ON = 0x01
    SET_OFF = 0x00

    # lengths (원본 DataLength)
    GET_DATA = 0x03
    SET_DATA = 0x04
    SET_PARAM = 0x08    
    MOVE_DATA_LENGTH = 0x2b    
    FILLBYTE_LEN = 24           # ✅ 원본 RailConstant.FILLBYTE
