import datetime
import threading
try:
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
except Exception:
    rclpy = None
    Node = object
    SingleThreadedExecutor = None

class _PowderClientNode(Node):
    def __init__(self, service_name: str):
        super().__init__("fr_gui_Powder_client")
        # ✅ 너가 사용 중인 srv 타입
        from ros.srv import PowderService
        self._srv_type = PowderService
        """
            string seq_no
            string cmd
            uint16 part_no
            string menu_id
            string opt_id
            uint8 channel
            uint8 req_value       
        """
        self.client = self.create_client(PowderService, service_name)

    def call_async(self, channel: int, cmd:str = None, seq_no: str = None):
        req = self._srv_type.Request()
        req.seq_no = seq_no or str(datetime.datetime.now())

        # cmd는 프로젝트마다 타입이 다를 수 있어서, 가능한 범위에서 자동 처리
        if cmd is None:
            try:
                DISPENSE = "dispense"
                req.cmd = DISPENSE
                req.channel = int(channel)
            except Exception:
                # fallback
                req.cmd = ""
        else:
            req.cmd = cmd
            req.channel = int(channel)
        req.channel = int(channel)
        return self.client.call_async(req)