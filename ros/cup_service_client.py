# app/ros/cup_service_client.py
"""
CupServiceClient
- GUI(PyQt)에서 "Cup Extract"를 눌렀을 때 ROS2 service를 비동기로 호출하기 위한 클라이언트

전제:
- message.srv.CupService 가 존재
- Request 필드: seq_no, cmd, channel 을 사용(너가 올려준 테스트 코드 기준)
"""

from __future__ import annotations

import datetime
import threading
from typing import Callable, Optional

try:
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
except Exception:
    rclpy = None
    Node = object
    SingleThreadedExecutor = None


class _CupClientNode(Node):
    def __init__(self, service_name: str):
        super().__init__("fr_gui_cup_client")
        # ✅ 너가 사용 중인 srv 타입
        from ros import CupService
        self._srv_type = CupService

        self.client = self.create_client(CupService, service_name)

    def call_async(self, channel: int, cmd=None, seq_no: Optional[str] = None):
        req = self._srv_type.Request()
        req.seq_no = seq_no or str(datetime.datetime.now())

        # cmd는 프로젝트마다 타입이 다를 수 있어서, 가능한 범위에서 자동 처리
        if cmd is None:
            try:
                DISPENSE = "dispense"
                req.cmd = DISPENSE
            except Exception:
                # fallback
                req.cmd = 0
        else:
            req.cmd = cmd

        req.channel = int(channel)
        return self.client.call_async(req)


class CupServiceClient:
    def __init__(self, service_name: Optional[str] = None):
        if rclpy is None:
            raise RuntimeError("rclpy is not available. Run on ROS2 environment.")

        if service_name is None:
            # 프로젝트에 이미 상수(Service.SERVICE_CUP)가 있으면 그걸 우선 사용
            try:
                SERVICE_CUP = 'cup/service'
                service_name = SERVICE_CUP
            except Exception:
                service_name = "/cup_service"

        if not rclpy.ok():
            rclpy.init(args=None)

        self._node = _CupClientNode(service_name)
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

    def dispense_async(
        self,
        channel: int,
        cmd=None,
        on_done: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
    ):
        """
        on_done(resp), on_error(exception)
        """
        # 서비스 준비 확인(짧게 폴링)
        try:
            if not self._node.client.wait_for_service(timeout_sec=0.2):
                raise RuntimeError("Cup service not available (wait_for_service timeout)")
        except Exception as e:
            if on_error:
                on_error(e)
            else:
                raise
            return

        future = self._node.call_async(channel=channel, cmd=cmd)

        def _cb(fut):
            try:
                resp = fut.result()
                if on_done:
                    on_done(resp)
            except Exception as e:
                if on_error:
                    on_error(e)

        future.add_done_callback(_cb)
        return future
