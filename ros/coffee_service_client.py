import datetime

try:
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
except Exception:
    rclpy = None
    Node = object
    SingleThreadedExecutor = None

class _CoffeeClientNode(Node):
    def __init__(self, service_name: str):
        super().__init__("fr_gui_Coffee_client")
        # ✅ 너가 사용 중인 srv 타입
        from ros.srv import CoffeeService
        self._srv_type = CoffeeService
        """
            string seq_no
            string cmd
            uint8 protocol_id
            uint8 device_id
            float32 delay_time        
        """
        self.client = self.create_client(CoffeeService, service_name)

    def call_async(self, channel: int, cmd:str = None, seq_no: str = None):
        req = self._srv_type.Request()
        req.seq_no = seq_no or str(datetime.datetime.now())

        # cmd는 프로젝트마다 타입이 다를 수 있어서, 가능한 범위에서 자동 처리
        if cmd is None:
            try:
                EXTRACT = "extract"
                req.cmd = EXTRACT
                req.protocol_id = 11
                req.device_id = 0
                req.delay_time = 0.0
                
            except Exception:
                # fallback
                req.cmd = ""
        else:
            req.cmd = cmd
            req.protocol_id = 21 if cmd == "extract" else 0
            req.device_id = channel
            req.delay_time = 0.0
            req.channel = int(channel)
        return self.client.call_async(req)