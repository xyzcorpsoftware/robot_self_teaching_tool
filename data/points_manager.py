import math
import traceback
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

import pymysql


@dataclass
class RobotSequenceData:
    def __init__(self, name, j1, j2, j3, j4, j5, j6, x, y, z, rx, ry, rz):
        self.name = name
        self.joint = [j1, j2, j3, j4, j5, j6] if None not in (j1, j2, j3, j4, j5, j6) else None
        self.tcp = [x, y, z, rx, ry, rz] if None not in (x, y, z, rx, ry, rz) else None


class RobotPointsManager:
    """
    - MySQL DB(T_ROBOT_POINTS)에서 포인트 로드
    - update_point_in_db로 x,y,z,rx,ry,rz 저장
    - add_relative_points / add_pic_relative_points로 상대 포인트 생성
    """

    def __init__(
        self,
        host: str = "localhost",
        user: str = "baris",
        password: str = "xyz20190529",
        database: str = "baris_brew",
        table: str = "T_ROBOT_POINTS",
    ):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.table = table

        self.points_dict: Dict[str, List[float]] = {}

        # 로드 + 계산 포인트 추가
        self.load_points_from_db()
        self.add_relative_points()
        self.add_pic_relative_points()

        print(f"[PM] Initialized with {len(self.points_dict)} points.")

    # ─────────────────────────────────────────────
    # DB
    # ─────────────────────────────────────────────
    def _connect(self):
        try:
            return pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                charset="utf8mb4",
            )
        except Exception as error:
            print("[PointDB][ERROR] Connection failed:\n", traceback.format_exc())

    def load_points_from_db(self):
        """
        DB에서 포인트 로드
        - j1~j6이 있으면: joint 포인트로 저장
        - x~rz가 있으면: tcp 포인트로 저장
        """
        conn = None
        try:
            conn = self._connect()
            cursor = conn.cursor()

            cursor.execute(f"SELECT * FROM {self.table}")
            columns = [desc[0] for desc in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

            data_list: List[RobotSequenceData] = []

            # ✅ dict에 바로 반영
            self.points_dict.clear()

            for row in rows:
                name = row.get("name")
                if not name:
                    continue

                j_fields = [row.get("j1"), row.get("j2"), row.get("j3"), row.get("j4"), row.get("j5"), row.get("j6")]
                t_fields = [row.get("x"), row.get("y"), row.get("z"), row.get("rx"), row.get("ry"), row.get("rz")]

                joint = [float(v) for v in j_fields] if None not in j_fields else None
                tcp = [float(v) for v in t_fields] if None not in t_fields else None

                # joint 우선 저장, 없으면 tcp 저장
                if joint and len(joint) == 6:
                    self.points_dict[name] = joint
                elif tcp and len(tcp) == 6:
                    self.points_dict[name] = tcp

            print(f"[PM] Loaded points: {len(self.points_dict)}")

        except Exception:
            print("[PM][ERROR] DB load failed:\n", traceback.format_exc())
        finally:
            if conn:
                conn.close()

    def update_point_in_db(self, name: str, new_pos: List[float]):
        """
        name 포인트의 x,y,z,rx,ry,rz만 업데이트
        """
        if len(new_pos) != 6:
            print(f"[PM][ERROR] {name} save failed (len!=6): {new_pos}")
            return

        conn = None
        try:
            conn = self._connect()
            cursor = conn.cursor()

            sql = f"""
                UPDATE {self.table}
                SET x=%s, y=%s, z=%s, rx=%s, ry=%s, rz=%s
                WHERE name=%s
            """
            cursor.execute(sql, (*new_pos, name))
            conn.commit()

            if cursor.rowcount == 0:
                print(f"[PM][WARN] UPDATE 0 row: {name} not found or No change.")
            else:
                print(f"[PM] Saved to DB: {name} -> {new_pos}")

            # 캐시도 업데이트
            self.points_dict[name] = list(new_pos)

        except Exception:
            print("[PM][ERROR] DB update failed:\n", traceback.format_exc())
        finally:
            if conn:
                conn.close()

    def reload(self):
        """
        DB 재로딩 + 상대포인트 재계산.
        변경점 비교해서 리스트로 반환.
        """
        old = dict(self.points_dict)

        self.load_points_from_db()
        self.add_relative_points()
        self.add_pic_relative_points()

        changed = []
        for k, v in self.points_dict.items():
            if k in old and old[k] != v:
                changed.append((k, old[k], v))
        return changed

    def get_points_by_name(self, name: str) -> Optional[List[float]]:
        return self.points_dict.get(name)

    # ─────────────────────────────────────────────
    # Relative points
    # ─────────────────────────────────────────────
    def add_relative_points(self):
        """
        DB에 저장되지 않은 상대 좌표를 포인트로 저장
        """
        def apply_offset(base_point: List[float], offset: List[float]):
            return [base_point[i] + offset[i] for i in range(6)]

        def cos_deg(deg):
            return math.cos(math.radians(deg))

        def sin_deg(deg):
            return math.sin(math.radians(deg))

        x_offset = y_offset = x_offset_ret = y_offset_ret = 0.0

        base = self.points_dict.get("COF_Up_L")
        if base and len(base) == 6:
            rz = base[5]
            angle_deg = rz - 90
            x_offset = round(-240 * cos_deg(angle_deg), 1)
            y_offset = round(-240 * sin_deg(angle_deg), 1)
            x_offset_ret = round(-210 * cos_deg(angle_deg), 1)
            y_offset_ret = round(-210 * sin_deg(angle_deg), 1)

        relative_defs = [
            ("CUP3_Hold_L", "CUP3_Down_L", [0, 0, -70, 0, 0, 0]),
            ("CUP3_Hold_L", "CUP3_Ret_L",  [-100, 0, -70, 0, 0, 0]),
            ("CUP2_Hold_L", "CUP2_Down_L", [0, 0, -70, 0, 0, 0]),
            ("CUP2_Hold_L", "CUP2_Ret_L",  [-100, 0, -70, 0, 0, 0]),
            ("CUP1_Hold_L", "CUP1_Down_L", [0, 0, -70, 0, 0, 0]),
            ("CUP1_Hold_L", "CUP1_Ret_L",  [-100, 0, -70, 0, 0, 0]),
            ("COF_Up_L", "COF_Place_L", [0, 0, -50, 0, 0, 0]),
            ("COF_Up_L", "COF_Ret_L",   [x_offset_ret, y_offset_ret, -50, 0, 0, 0]),
            ("COF_Up_L", "COF_App_L",   [x_offset, y_offset, 0, 0, 0, 0]),
            ("POW_Up_L", "POW_Place_L", [0, 0, -50, 0, 0, 0]),
            ("POW_Up_L", "POW_App_L",   [0, -140, 0, 0, 0, 0]),
            ("POW_Up_L", "POW_Ret_L",   [0, -140, -50, 0, 0, 0]),
            ("ICE2_Hold_L", "ICE2_PreHold_L", [0, -50, 0, 0, 0, 0]),
            ("ICE1_Hold_L", "ICE1_PreHold_L", [0, -50, 0, 0, 0, 0]),
        ]

        for base_name, new_name, offset in relative_defs:
            base = self.points_dict.get(base_name)
            if base and len(base) == 6:
                self.points_dict[new_name] = apply_offset(base, offset)
            else:
                # 상대 포인트는 기준이 없으면 생성 못하니 skip
                pass

    def add_pic_relative_points(self):
        """
        초기 4개 포인트 기준으로 PIC1~PIC6 관련 포인트 계산
        """
        def round6(values):
            return [round(v, 1) for v in values]

        p1_1 = self.points_dict.get("PIC1_1_Up_L")
        p1_2 = self.points_dict.get("PIC1_2_Up_L")
        p6_1 = self.points_dict.get("PIC6_1_Up_L")
        p6_2 = self.points_dict.get("PIC6_2_Up_L")

        if not all([p1_1, p1_2, p6_1, p6_2]):
            return

        a1, B1, C = p1_1[0], p1_1[1], p1_1[2]
        a2 = p6_1[0]
        B2 = p1_2[1]
        rx, ry = 90.0, 0.0

        rz_1_2 = p1_2[5]
        rz_6_2 = p6_2[5]

        for i in range(1, 7):
            if i == 1:
                xi = a1
            elif i == 6:
                xi = a2
            else:
                xi = ((6 - i) * a1 + (i - 1) * a2) / 5

            yi = B1
            zi = C

            point_defs = {
                f"PIC{i}_App_L": [xi, yi + 30, zi + 130],
                f"PIC{i}_1_Up_L": [xi, yi, zi],
                f"PIC{i}_1_Place_L": [xi, yi, zi - 30],
                f"PIC{i}_1_Ret_L": [xi, yi + 60, zi - 30],
                f"PIC{i}_2_Up_L": [xi, B2, zi],
                f"PIC{i}_2_Place_L": [xi, B2, zi - 30],
                f"PIC{i}_2_Ret_L": [xi, yi + 60, zi - 30],
                f"PIC{i}_Ret_Up_L": [xi, yi + 100, zi + 130],
            }

            for name, pos in point_defs.items():
                if name.startswith("PIC1_2_"):
                    rz_i = rz_1_2
                elif name.startswith("PIC6_2_"):
                    rz_i = rz_6_2
                else:
                    rz_i = 0.0

                if name not in self.points_dict:
                    self.points_dict[name] = round6(pos + [rx, ry, rz_i])

        # 특수 Ret 보정
        cos_80 = 0.173648
        sin_80 = 0.984807
        cos_100 = -0.173648

        self.points_dict["PIC1_2_Ret_L"] = round6([
            a1 - 60 * cos_80,
            B2 + 60 * sin_80,
            C - 30, rx, ry, rz_1_2
        ])
        self.points_dict["PIC6_2_Ret_L"] = round6([
            a2 - 60 * cos_100,
            B2 + 60 * sin_80,
            C - 30, rx, ry, rz_6_2
        ])


class BrewPointsManager:
    """
    - MySQL DB(T_ROBOT_POINTS)에서 포인트 로드
    - update_point_in_db로 x,y,z,rx,ry,rz 저장
    - add_relative_points / add_pic_relative_points로 상대 포인트 생성
    """
    def __init__(
        self,
        host: str = "localhost",
        user: str = "baris",
        password: str = "xyz20190529",
        database: str = "baris_brew",
        table: str = "T_ROBOT_POINTS",
    ):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.table = table

        self.points_dict: Dict[str, List[float]] = {}

        self.load_points_from_db()

        self.add_relative_points()

    # ─────────────────────────────────────────────
    # DB
    # ─────────────────────────────────────────────
    def _connect(self):
        try:
            return pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                charset="utf8mb4",
            )
        except Exception as error:
            print("[PointDB][ERROR] Connection failed:\n", traceback.format_exc())
    
    def load_points_from_db(self):
        conn = None
        try:
            conn = self._connect()
            cursor = conn.cursor()

            cursor.execute(f"SELECT * FROM {self.table}")
            columns = [desc[0] for desc in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

            data_list = []
            for row in rows:
                j_fields = [row.get("j1"), row.get("j2"), row.get("j3"), row.get("j4"), row.get("j5"), row.get("j6")]
                t_fields = [row.get("x"), row.get("y"), row.get("z"), row.get("rx"), row.get("ry"), row.get("rz")]

                joint = [float(v) for v in j_fields] if None not in j_fields else None
                tcp = [float(v) for v in t_fields] if None not in t_fields else None

                # joint 우선 저장, 없으면 tcp 저장
                if joint and len(joint) == 6:
                    self.points_dict[row["name"]] = joint
                elif tcp and len(tcp) == 6:
                    self.points_dict[row["name"]] = tcp

            print(f"[PM] Loaded points: {len(self.points_dict)}")

        except Exception:
            print("[PM][ERROR] DB load failed:\n", traceback.format_exc())
        finally:
            if conn:
                conn.close()


    def add_relative_points(self):
        '''
        db에 저장되지 않은 상대 좌표를 포인트로 저장
        '''

        def apply_offset(base_point, offset):
            return [base_point[i] + offset[i] for i in range(6)]

        # 각 항목: 기준 이름, 새 포인트 이름, 오프셋 값 [x, y, z, rx, ry, rz]
        relative_defs = [
            ("CUP4_Hold_L", "CUP4_Down_L", [0, 0, -70, 0, 0, 0]),
            ("CUP4_Hold_L", "CUP4_Ret_L", [0, -100, -70, 0, 0, 0]),
            ("CUP4_Hold_L", "CUP4_App_L", [0, -130, 0, 0, 0, 0]),
            ("CUP3_Hold_L", "CUP3_Down_L", [0, 0, -70, 0, 0, 0]),
            ("CUP3_Hold_L", "CUP3_Ret_L", [0, -100, -70, 0, 0, 0]),
            ("CUP3_Hold_L", "CUP3_App_L", [0, -130, 0, 0, 0, 0]),
            ("CUP2_Hold_L", "CUP2_Down_L", [0, 0, -70, 0, 0, 0]),
            ("CUP2_Hold_L", "CUP2_Ret_L", [0, -100, -70, 0, 0, 0]),
            ("CUP2_Hold_L", "CUP2_App_L", [0, -130, 0, 0, 0, 0]),
            ("CUP1_Hold_L", "CUP1_Down_L", [0, 0, -70, 0, 0, 0]),
            ("CUP1_Hold_L", "CUP1_Ret_L", [0, -100, -70, 0, 0, 0]),
            ("CUP1_Hold_L", "CUP1_App_L", [0, -130, 0, 0, 0, 0]),
            ("COF1_Up_L", "COF1_Place_L", [0, 0, -35, 0, 0, 0]),
            ("COF1_Up_L", "COF1_Ret_L", [0, -90, -60, 0, 0, 0]),
            ("COF1_Up_L", "COF1_App_L", [0, -140, 0, 0, 0, 0]),
            ("COF2_Up_L", "COF2_Place_L", [0, 0, -50, 0, 0, 0]),
            ("COF2_Up_L", "COF2_Ret_L", [0, -90, -60, 0, 0, 0]),
            ("COF2_Up_L", "COF2_App_L", [0, -160, 0, 0, 0, 0]),
            ("POW1_Up_L", "POW1_Place_L", [0, 0, -35, 0, 0, 0]),
            ("POW1_Up_L", "POW1_App_L", [0, -120, 0, 0, 0, 0]),
            ("POW1_Up_L", "POW1_Ret_L", [0, -160, 0, 0, 0, 0]),
            ("POW2_Up_L", "POW2_Place_L", [0, 0, -60, 0, 0, 0]),
            ("POW2_Up_L", "POW2_App_L", [0, -120, 0, 0, 0, 0]),
            ("POW2_Up_L", "POW2_Ret_L", [0, -160, 0, 0, 0, 0]),
            ("ICE2_Hold_L", "ICE2_PreHold_L", [0, -40, 0, 0, 0, 0]),
            ("ICE1_Hold_L", "ICE1_PreHold_L", [0, -40, 0, 0, 0, 0]),
            ("BAK1_Hold_L", "BAK1_App_L", [0, -120, 0, 0, 0, 0]),
            ("BAK2_Hold_L", "BAK2_App_L", [0, -120, 0, 0, 0, 0]),
            ("BAK3_Hold_L", "BAK3_App_L", [0, -120, 0, 0, 0, 0]),
            ("PIC_1_Up_L", "PIC_1_Place_L", [0, 0, -100, 0, 0, 0]),
            ("PIC_1_Up_L", "PIC_3_Up_L", [0, -20, 0, 10, 0, 0]),
            ("PIC_1_Up_L", "PIC_3_Place_L", [0, -20, -110, 10, 0, 0]),
            ("PIC_2_Up_L", "PIC_Ret_2_L", [0, 100, -190, 0, 0, 0]),
            ("PIC_2_Up_L", "PIC_Ret_2_Up_L", [0, 100, -120, 0, 0, 0]),
            ("PIC_2_Up_L", "PIC_2_Place_L", [0, 0, -190, 0, 0, 0]),
            ("PIC_2_Up_L", "PIC_4_Up_L", [0, -20, 0, 10, 0, 0]),
            ("PIC_2_Up_L", "PIC_4_Place_L", [0, -20, -180, 10, 0, 0]),
        ]

        for base_name, new_name, offset in relative_defs:
            base = self.points_dict.get(base_name)
            if base and len(base) == 6:
                self.points_dict[new_name] = apply_offset(base, offset)
            else:

                print(f"[SKIP] 기준 포인트 {base_name}이 존재하지 않음 또는 값이 잘못됨")

    def get_points_by_name(self, name):
        """
        저장된 포인트 중 name에 해당하는 값 리턴
        """
        return self.points_dict.get(name, None)
    
    def update_point_in_db(self, name: str, new_pos: List[float]):
        """
        name 포인트의 x,y,z,rx,ry,rz만 업데이트
        """
        if len(new_pos) != 6:
            print(f"[PM][ERROR] {name} save failed (len!=6): {new_pos}")
            return

        conn = None
        try:
            conn = self._connect()
            cursor = conn.cursor()

            sql = f"""
                UPDATE {self.table}
                SET x=%s, y=%s, z=%s, rx=%s, ry=%s, rz=%s
                WHERE name=%s
            """
            cursor.execute(sql, (*new_pos, name))
            conn.commit()

            if cursor.rowcount == 0:
                print(f"[PM][WARN] UPDATE 0 row: {name} not found or No change.")
            else:
                print(f"[PM] Saved to DB: {name} -> {new_pos}")

            # 캐시도 업데이트
            self.points_dict[name] = list(new_pos)

        except Exception:
            print("[PM][ERROR] DB update failed:\n", traceback.format_exc())
        finally:
            if conn:
                conn.close()

    def reload(self):
        """
        DB 재로딩 + 상대포인트 재계산.
        변경점 비교해서 리스트로 반환.
        """
        old = dict(self.points_dict)

        self.load_points_from_db()
        self.add_relative_points()

        changed = []
        for k, v in self.points_dict.items():
            if k in old and old[k] != v:
                changed.append((k, old[k], v))
        return changed
    