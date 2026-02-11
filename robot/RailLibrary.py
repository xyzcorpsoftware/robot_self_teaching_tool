from enum import Enum, IntFlag, IntEnum
class RailConstant:
    SET_ORIGIN_SPEED = 14
    BASE_SPEED = 30000
    TWO_LENGTH = 2
    THREE_LEGNTH =3
    FOUR_LENGTH = 4
    TEN_BYTES = 1024
    RESPONSE_ONE = 6
    RESPONSE_TWO = 7
    RESPONSE_THREE = 8
    RESPONSE_FOUR = 9
    FRONT_FIRST = 'little'
    RAIL_NORMAL_SPEED = 310000
    RAIL_ACCEL_TIME = 750
    RAIL_DECEL_TIME = 750
    RAIL_NORMAL_DISTANCE = 0
    RAIL_MOVE_TIMEOUT = 150
    FILLBYTE = 24
    CLOCK = 0.1
    ZERO = 0
    BITS_FULL = 255
    ZERO_BIT =  1 << 0
    ONE_BIT =   1 << 1
    TWO_BIT =   1 << 2
    THREE_BIT = 1 << 3
    FOUR_BIT =  1 << 4
    FIVE_BIT =  1 << 5
    SIX_BIT =   1 << 6
    SEVEN_BIT = 1 << 7 
    # 0b 0000 0001
    ONE_BYTE = 1
    
    # 0b 0000 0001 0000 0000
    TWO_BYTES = 256
    
    # 0b 0000 0001 0000 0000 0000 0000
    THREE_BYTES = 65536
    
    # 0b 0000 0001 0000 0000 0000 0000 0000 0000
    FOUR_BYTES = 16777216

    

class RailCheck(IntEnum):
    IDLE = 0

    # Frame type 에러
    FRAME_ERROR = 128
    # 데이터 에러, ROM 데이터 읽기, 쓰기 에러
    DATA_ERROR = 129
    # 수신 Frame 에러
    RECV_FRAME_ERROR = 130
    
    # 운전 명령 실패 
    DRIVE_COMM_ERROR = 133

    # Reset 실패
    RESET_FAIL = 134

    #(1) 알람 발생중에 Servo On 명령을 실행하려고 했습니다."
    SERVO_ON_FAIL = 135
    
    #(2) 비상 정지중에 Servo On 명령을 실행하려고 했습니다.
    SERVO_ON_FAIL2 = 136
    
    #(3) 외부 입력 신호에 'Servo ON'이 설정되어 있습니다."
    SERVO_ON_FAIL3 = 137

class DataLength:
    GET_DATA = 0x03
    SET_DATA = 0x04
    SET_PARAM = 0x08
    MOVE_DATA_LENGTH = 0x2b
    FILLBYTE_LEN = 24

class RailPacket:
    SET_ON = 0x01
    SET_OFF = 0x00
    HEADER = 0xaa
    RESERVED = 0x00
    GET_MOTION = 0x40
    MOVE_POS_VELOCITY = 0x80
    MOVE_ORIGIN = 0x33
    CLEAR_POSITION = 0x56
    SET_PARAM = 0x12
    MOVE_JOG = 0x37
    SERVO_ON = 0x2a
    GET_POSITION = 0x53
    EMG_STOP = 0x32
    SLOW_STOP = 0x31
    GET_ALARM_TYPE = 0x2E
    MAKE_PAUSE = 0x58
    ALARM_RESET = 0x2b

class RailAlarm(IntEnum):
    """
        제어기 쪽 알람
    """
    NO_ALARM = 0
    OVER_CURRNET = 1
    OVER_SPEED = 2
    POS_TRACKING_ERROR =3
    
    #과부하 이상"
    OVER_LOAD = 4
    OVER_HEAT = 5
    EMF_ERROR = 6
    MOTOR_ERROR = 7
    ENCODER_ERROR = 8
    INPOSITION = 10
    SYSTEM_ERROR = 11
    
    # 저장장치
    ROM_ERROR = 12
    # 위치 초과 오차 이상
    POS_OVER_ERROR = 15
    INNER_COMM_ERROR = 50
    SERVO_ON_FAIL1 = 51
    SERVO_ON_FAIL2 = 60
    IP_SET_ERROR = 201
    IP_CONFLICT = 202

class ErrorState(IntFlag):
    # 여러 에러 중 하나 이상의 에러 발생
    ERRORALL = 0X00000001
    # 방향 센서 리미티 초과
    HW_POSILMT = 0X00000002
    HW_NEGALMT =0X00000004
    # 방향 프로그램 리미트 초과
    SW_POGILMT = 0X00000008
    SW_NEGALMT = 0X00000010


    ERR_POSOVERFLOW = 0X00000080
    ERR_OVERCURRENT = 0X00000100
    ERR_OVERSPEED = 0X00000200
    ERR_POSTRACKING = 0X00000400
    ERR_OVERLOAD = 0X00000800
    ERR_OVERHEAT = 0X00001000
    ERR_BACKEMF = 0X00002000
    ERR_MOTORPOWER = 0X00004000
    ERR_INPOSITION = 0X00008000

   
    
class RailMotion(IntFlag):
     # initialize 필요
    EMG_STOP = 0X00010000
    SLOW_STOP = 0X00020000
    ORIGIN_RETURNING = 0X00040000
    IN_POSITION = 0X00080000
    
    SERVO_ON = 0X00100000
    ALARM_RESET = 0X00200000
    PT_STOPED =0X00400000
    ORIGINSENSOR = 0X00800000
    
    ZPULSE = 0X01000000
    ORIGINRETOK = 0X02000000
    MOTORDIR = 0x04000000
    MOTIONING = 0X08000000

    PAUSING = 0x10000000
    ACCELING = 0x20000000
    DECELING = 0x40000000
    CONST_DRIVE = 0x80000000


