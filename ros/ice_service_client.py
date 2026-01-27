import datetime
import threading
import re
try:
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
except Exception:
    rclpy = None
    Node = object
    SingleThreadedExecutor = None

class _IceClientNode(Node):
    def __init__(self, service_name: str):
        super().__init__("fr_gui_Ice_client")
        # ✅ 너가 사용 중인 srv 타입
        from ros.srv import IceService
        self._srv_type = IceService
        """
        string  seq_no
        string  cmd
        uint16  ice_qty
        uint16  water_qty
        uint8   channel       
        """
        self.client = self.create_client(IceService, service_name)

    def call_async(self, channel: int, cmd:str = None, seq_no: str = None):
        req = self._srv_type.Request()
        req.seq_no = seq_no or str(datetime.datetime.now())

        # cmd는 프로젝트마다 타입이 다를 수 있어서, 가능한 범위에서 자동 처리
        if cmd is None:
            try:
                EXTRACT = "extract"
                req.cmd = EXTRACT
                req.ice_qty = 100
                req.water_qty = 100
                req.channel = int(channel)
            except Exception:
                # fallback
                req.cmd = ""
        else:
            req.cmd = cmd
            req.ice_qty = 100
            req.water_qty = 100
            req.channel = int(channel)
        req.channel = int(channel)
        return self.client.call_async(req)
    

class IceServiceClient:
    def __init__(self, service_name: Optional[str] = None):
        if rclpy is None:
            raise RuntimeError("rclpy is not available. Run on ROS2 environment.")

        if service_name is None:
            # 프로젝트에 이미 상수(Service.SERVICE_CUP)가 있으면 그걸 우선 사용
            try:
                SERVICE_ICE = 'ice/service'
                service_name = SERVICE_ICE
            except Exception:
                service_name = "/ice/service"

        if not rclpy.ok():
            rclpy.init(args=None)

        self._node = _IceClientNode(service_name)
        self._exec = SingleThreadedExecutor()
        self._exec.add_node(self._node)

        self._spin_thread = threading.Thread(target=self._exec.spin, daemon=True)
        self._spin_thread.start()

    def dispose(self):
        try:
            if self._exec is not None and self._node is not None:
                self._exec.remove_node(self._node)
                self._node.destroy_node()
        except Exception:
            pass

    def ice_extract_async(
        self,
        point_name : str
    ):
        """
        on_done(resp), on_error(exception)
        """
        # 서비스 준비 확인(짧게 폴링)
    
        if not self._node.client.wait_for_service(timeout_sec=0.2):
            raise RuntimeError("Cup service not available (wait_for_service timeout)")
        name = re.sub(r'\d+', '', point_name)
        # 숫자 부분 추출
        number = int(re.findall(r'\d+', point_name)[0])
        channel = number-1

        
        future = self._node.call_async(channel=channel, cmd='extract')

        def _cb(fut):
            try:
                resp = fut.result()
                print(resp.response_cd)
            except Exception as e:
                print(e)

        future.add_done_callback(_cb)
        return future
