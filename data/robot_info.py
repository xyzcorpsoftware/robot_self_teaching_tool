# app/data/robot_info.py

import traceback
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple

import pymysql


@dataclass
class RobotInfoData:
    """
    t_robot_info row model
    """
    component_cd: str
    num: int
    robot_class: str
    host: str
    port: int
    raw: Dict[str, Any]


class RobotInfoManager:
    """
    - MySQL DB(t_robot_info)에서 로봇/장치 접속 정보를 로드
    - component_cd로 host/port 조회 (num은 호출자가 사용하지 않음)
      * 같은 component_cd가 여러 개면 num이 가장 작은 row를 대표로 사용
      * port가 0이면 default_port 사용
    """

    def __init__(
        self,
        host: str = "localhost",
        user: str = "baris",
        password: str = "xyz20190529",
        database: str = "baris_brew",
        table: str = "T_ROBOT_INFO",
        auto_load: bool = True,
    ):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.table = table

        # component_cd -> RobotInfoData
        self.info_dict: Dict[str, RobotInfoData] = {}

        if auto_load:
            self.load_robot_info_from_db()

    # ─────────────────────────────────────────────
    # DB
    # ─────────────────────────────────────────────
    def _connect(self):
        return pymysql.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            charset="utf8mb4",
        )

    def load_robot_info_from_db(self):
        """
        t_robot_info 전체를 로드하여 캐시에 저장.
        같은 component_cd가 여러 row면 num이 가장 작은 row를 대표로 유지.
        """
        conn = None
        try:
            conn = self._connect()
            cursor = conn.cursor()

            cursor.execute(f"SELECT * FROM {self.table}")
            columns = [desc[0] for desc in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

            self.info_dict.clear()

            for row in rows:
                component_cd = str(row.get("component_cd", "")).strip()
                if not component_cd:
                    continue

                num = int(row.get("num", 0) or 0)
                robot_class = str(row.get("robot_class", "")).strip()
                host = str(row.get("host", "")).strip()
                port = int(row.get("port", 0) or 0)

                existing = self.info_dict.get(component_cd)
                # 대표 row 선택 정책: num이 더 작은 것을 대표로
                if (existing is None) or (num < existing.num):
                    self.info_dict[component_cd] = RobotInfoData(
                        component_cd=component_cd,
                        num=num,
                        robot_class=robot_class,
                        host=host,
                        port=port,
                        raw=row,
                    )

            print(f"[RI] Loaded robot_info: {len(self.info_dict)}")

        except Exception:
            print("[RI][ERROR] DB load failed:\n", traceback.format_exc())
        finally:
            if conn:
                conn.close()

    # ─────────────────────────────────────────────
    # Lookup
    # ─────────────────────────────────────────────
    def get_host(self, component_cd: str, default: Optional[str] = None) -> Optional[str]:
        key = (component_cd or "").strip()
        if not key:
            return default

        info = self.info_dict.get(key)
        if info and info.host:
            return info.host
        return default

    def get_port(self, component_cd: str, default: int = 0) -> int:
        key = (component_cd or "").strip()
        if not key:
            return int(default)

        info = self.info_dict.get(key)
        if info:
            return int(info.port)
        return int(default)

    def get_ip_port(self, component_cd: str, default_port: int = 2001) -> Optional[Tuple[str, int]]:
        """
        component_cd로 (host, port)를 반환.
        - host가 없으면 None
        - port가 0이면 default_port 사용
        """
        key = (component_cd or "").strip()
        if not key:
            return None

        info = self.info_dict.get(key)
        if not info or not info.host:
            return None

        port = int(info.port) if int(info.port) > 0 else int(default_port)
        return info.host, port

    def refresh(self):
        self.load_robot_info_from_db()
