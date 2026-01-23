import pymysql
import traceback

class RobotReqData:
    """
    t_robot_service_req row model
    """

    # 필드 정의
    #######  Select용 필드 #######
    robot_command = ""
    no  = 0

    ####### Parameter용 필드 #######
    cmd = ""
    rail_pos = ""
    par1 = ""
    par2 = ""
    par3 = ""  
    par4 = ""
    par5 = ""


class RobotServiceReqManager:
    """
    - MySQL DB(t_robot_service_req)에서 로봇 서비스 요청 정보를 로드
    """

    def __init__(
        self,
        host: str = "localhost",
        user: str = "baris",
        password: str = "xyz20190529",
        database: str = "baris_brew",
        table: str = "T_ROBOT_SERVICE_REQ",
    ):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.table = table

    def _connect(self):
        return pymysql.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            charset="utf8mb4",
        )

    def get_rail_pos(self, command : str, no : int):
        conn = None
        column_rail_pos = "rail_pos"
        rail_pos = ""
        try:
            conn = self._connect()
            cursor = conn.cursor()

            condition = {
                "robot_command": command,
                "no": no
            }

            where_clauses = " AND ".join([f"{key} = %s" for key in condition.keys()])
            cursor.execute(f"SELECT {column_rail_pos} FROM {self.table} WHERE {where_clauses}", tuple(condition.values()))
            columns = [desc[0] for desc in cursor.description]
            row = cursor.fetchone()
            if row is None:
                return None

            row_dict = dict(zip(columns, row))
            rail_pos = str(row_dict.get("rail_pos", "")).strip()
            
        except Exception:
            print("[RSR][ERROR] DB load failed:\n", traceback.format_exc())
            return None
        finally:
            if conn:
                conn.close()
            return rail_pos
    def update_rail_pos(self, command : str, no : int, rail_pos : str):
        
        conn = None
        try:
            conn = self._connect()
            cursor = conn.cursor()

            condition = {
                "robot_command": command,
                "no": no
            }

            set_clause = "rail_pos = %s"
            where_clauses = " AND ".join([f"{key} = %s" for key in condition.keys()])
            sql = f"UPDATE {self.table} SET {set_clause} WHERE {where_clauses}"
            params = (rail_pos,) + tuple(condition.values())
            cursor.execute(sql, params)
            conn.commit()
            
        except Exception:
            print("[RSR][ERROR] DB update failed:\n", traceback.format_exc())
        finally:
            if conn:
                conn.close()

    # def load_robot_info_from_db(self):
    #     """
    #     t_robot_info 전체를 로드하여 캐시에 저장.
    #     같은 component_cd가 여러 row면 num이 가장 작은 row를 대표로 유지.
    #     """
    #     conn = None
    #     try:
    #         conn = self._connect()
    #         cursor = conn.cursor()

    #         cursor.execute(f"SELECT * FROM {self.table}")
    #         columns = [desc[0] for desc in cursor.description]
    #         rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    

    #         for row in rows:
    #             component_cd = str(row.get("component_cd", "")).strip()
    #             if not component_cd:
    #                 continue

    #             num = int(row.get("num", 0) or 0)
    #             robot_class = str(row.get("robot_class", "")).strip()
    #             host = str(row.get("host", "")).strip()
    #             port = int(row.get("port", 0) or 0)


    #     except Exception:
    #         print("[RI][ERROR] DB load failed:\n", traceback.format_exc())
    #     finally:
    #         if conn:
    #             conn.close()