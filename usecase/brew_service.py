import sys
from pathlib import Path
import os
import socket
import time
import traceback
from threading import Lock
import re
from robot.Rail import RailSocket
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.robot_info import RobotInfoManager
from data.robot_service_req import RobotServiceReqManager

class BrewService:
    def __init__(self, points_manager=None, use_real_robot=False):
        self.points_manager = points_manager
        self._tcp_cache = {}
        self.DEFAULT_RETURN_VEL = 25
        self.DEFAULT_RETURN_ACC = 25

        self.robot_info = RobotInfoManager(
            host=getattr(self.points_manager, "host", "localhost"),
            user=getattr(self.points_manager, "user", "baris"),
            password=getattr(self.points_manager, "password", "xyz20190529"),
            database=getattr(self.points_manager, "database", "baris_brew"),
            table="T_ROBOT_INFO",
            auto_load=True,
        )
        self.robot_srv_manager = RobotServiceReqManager(
            host=getattr(self.points_manager, "host", "localhost"),
            user=getattr(self.points_manager, "user", "baris"),
            password=getattr(self.points_manager, "password", "xyz20190529"),
            database=getattr(self.points_manager, "database", "baris_brew"),
            table="T_ROBOT_SERVICE_REQ",
        )
        self.use_real_robot = use_real_robot
    
        default_ip = os.getenv("RAIL_IP", "192.168.0.12")
        default_port = int(os.getenv("RAIL_PORT", "2001"))

        if not self.use_real_robot:
            print("[BREW][RAIL] use_real_robot is False: skipping rail connection")
            self.rail = None
        else :

            ip_port = self.robot_info.get_ip_port("RAL", default_port=default_port)
            if ip_port:
                rail_ip, rail_port = ip_port
            else:
                rail_ip, rail_port = default_ip, default_port

            self.rail = RailSocket(rail_ip, rail_port, timeout=3.0, use_real_robot=self.use_real_robot)
            # self.rail.connect(do_init=True)
            print(f"[BREW][RAIL][INFO] connected+servo_on to {rail_ip}:{rail_port}")

        target_list = []
        self.RAIL_TARGET_PULSE = dict()
        
        # 디스펜서 별 레일 위치 맵
        # -> DB 기반으로 변경 필요 (현재 DB에 저장된 값을 로드하도록)
        btn_map = {
            "btn_ice1": "ice1",
            "btn_ice2": "ice2",
            "btn_powder1": "pow1",
            "btn_powder2": "pow2",
            "btn_coffee1": "cof1",
            "btn_coffee2": "cof2",
            "btn_cup1": "cup1",
            "btn_cup2": "cup2",
            "btn_cup3": "cup3",
            "btn_cup4": "cup4",
            "btn_pic12": "pic12",
            "btn_pic61": "pic61",
            "btn_home": "home",
        }
        
        self.RAIL_TARGET_PULSE = self._get_rail_pulse(list(btn_map.values()))
        # self.RAIL_TARGET_PULSE = {
        #     "cup1": 0,
        #     "cup2": 0,
        #     "ice1": 200000,
        #     "ice2": 465000,
        #     "cof1": 705000,
        #     "cof2": 1000000,
        #     "pow1": 1026000,
        #     "pow2": 1300000,
        #     "cup3": 1350000,
        #     "cup4": 1350000,
        #     "pic1": 1260000,
        #     "pic2": 1260000,
        # }

    def _move_rail_before_motion(self, label: str, target_pose: str = None):
        key = (label or "").lower().strip().replace(" ", "").replace("_", "")
        if not key or key == "none":
            print("[BREW][RAIL] skip (empty label)")
            return

        target = self.RAIL_TARGET_PULSE.get(key)
        if target is None:
            if key in getattr(self, "RAIL_REQUIRED", set()):
                raise ValueError(f"Rail target not defined for '{key}'")
            print(f"[BREW][RAIL] skip (no target): {key}")
            return

        try:
            target = int(target_pose) if target_pose is not None else self.RAIL_TARGET_PULSE.get(key)
            # ✅ 폴링/포지션 로그 포함
            final_pos = self.rail.move_to_pulse_and_wait(
                target_pulse=target,
                pps=100000,
                tol=50,
                timeout_s=20.0,
                log_poll=True,          # ✅ 위치 로그
                log_period_s=0.5,       # ✅ 0.5초마다 출력
            ) if self.use_real_robot is True else print("[BREW][RAIL] use_real_robot is False: skipping rail move")
            print(f"[BREW][RAIL][INFO] rail move successed: label={label}, final={final_pos}, target={target}")
        except Exception as e:
            print(f"[BREW][RAIL][WARN] move failed: label={label}, err={e}")
            raise RuntimeError(f"Rail move failed: label={label}, err={e}")

    # --- helpers (SequenceService style) ---
    def _get_point(self, name: str):
        if self.points_manager is None:
            return None
        return self.points_manager.points_dict.get(name)

    def _set_point_cache(self, name: str, pose6):
        if self.points_manager is None:
            return
        self.points_manager.points_dict[name] = list(pose6[:6])

    def _move_joint(self, controller, joints, vel=20, acc=20):
        if controller is None or joints is None:
            return
        if hasattr(controller, "move_joint"):
            print(f"joint : {joints}")
            controller.move_joint(joints, vel=vel, acc=acc)

    def _move_linear(self, controller, pose, vel=20, acc=20, blendR=None):
        if controller is None or pose is None:
            return
        if hasattr(controller, "move_linear"):
            print(f"tcp : {pose}")
            controller.move_linear(pose, vel=vel, acc=acc, blendR=blendR)

    def _move_gripper(self, controller, pos: int):
        if controller is None:
            return
        if hasattr(controller, "move_gripper"):
            controller.move_gripper(pos)

    def _get_actual_tcp_pose(self, controller):
        if controller is None:
            return None
        if hasattr(controller, "get_actual_tcp_pose"):
            return controller.get_actual_tcp_pose()
        return None

    def _resolve_saved_point_name(self, ui_point_name: str) -> str:
        n = (ui_point_name or "").lower().strip()

        if n.startswith("cup"):
            num = n.replace("cup", "")
            return f"CUP{num}_Hold_L"

        if n.startswith("ice"):
            num = n.replace("ice", "")
            return f"ICE{num}_Hold_L"

        if n in ("cof", "coffee") or n.startswith("cof"):
            num = n.replace("cof", "").replace("coffee", "") or "1"
            return f"COF{num}_Place_L"

        if n in ("pow", "powder") or n.startswith("pow"):
            num = n.replace("pow", "").replace("powder", "") or "1"
            return f"POW{num}_Place_L"

        if n.startswith("pic"):
            num = n.replace("pic", "")
            return f"PIC_{num}_Place_L"

        return ui_point_name.strip()

    def _run_pic_motion(self, par2: str, controller):
        if par2 not in ("1", "2"):
            return {"open_jog": True, "jog_target": f"pic{par2}"}

        home = self._get_point("HOME_J")
        app_j = self._get_point(f"PIC{par2}_App_J")
        up_l = self._get_point(f"PIC_{par2}_Up_L")
        place_l = self._get_point(f"PIC_{par2}_Place_L")

        missing = [k for k, v in {
            "HOME_J": home,
            f"PIC{par2}_App_J": app_j,
            f"PIC_{par2}_Up_L": up_l,
            f"PIC_{par2}_Place_L": place_l,
        }.items() if v is None]

        if missing:
            print(f"[BREW][PIC][WARN] missing points: {missing}")
            return {"open_jog": True, "jog_target": f"pic{par2}"}

        # 홈 위치 이동 후 레일 이동 시작
        self._move_joint(controller, home, vel=30, acc=15)

        # Rail
        self._move_rail_before_motion(f"pic{par2}")

        self._move_joint(controller, app_j, vel=30, acc=30)
        self._move_linear(controller, up_l, vel=30, acc=30)
        self._move_linear(controller, place_l, vel=20, acc=20)
        return {"open_jog": True, "jog_target": f"pic{par2}"}

    def _return_motion_after_save(self, saved_point_name: str, controller, vel=45, acc=45):
        if controller is None:
            return
        name = (saved_point_name or "").strip()

        if name.startswith("CUP") and name.endswith("_Hold_L"):
            num = name.replace("CUP", "").replace("_Hold_L", "")
            hold = self._get_point(f"CUP{num}_Hold_L")
            down = self._get_point(f"CUP{num}_Down_L")
            ret = self._get_point(f"CUP{num}_Ret_L")
            app_cup = self._get_point("MAC_App_Cup_L")
            app_j = self._get_point("MAC_App_J")

            missing = [k for k, v in {
                f"CUP{num}_Hold_L": hold,
                f"CUP{num}_Down_L": down,
                f"CUP{num}_Ret_L": ret,
                "MAC_App_Cup_L": app_cup,
                "MAC_App_J": app_j,
            }.items() if v is None]

            if missing:
                print(f"[BREW][RETURN][CUP][WARN] missing points: {missing}")
                return

            self._move_linear(controller, hold, vel=vel, acc=acc)
            self._move_linear(controller, down, vel=vel, acc=acc)
            self._move_linear(controller, ret, vel=vel, acc=acc)
            self._move_linear(controller, app_cup, vel=vel, acc=acc)
            self._move_joint(controller, app_j, vel=vel, acc=acc)
            return

        if name.startswith("ICE") and name.endswith("_Hold_L"):
            num = name.replace("ICE", "").replace("_Hold_L", "")
            hold = self._get_point(f"ICE{num}_Hold_L")
            pre = self._get_point(f"ICE{num}_PreHold_L")
            app_j = self._get_point("MAC_App_J")

            missing = [k for k, v in {
                f"ICE{num}_Hold_L": hold,
                f"ICE{num}_PreHold_L": pre,
                "MAC_App_J": app_j,
            }.items() if v is None]

            if missing:
                print(f"[BREW][RETURN][ICE][WARN] missing points: {missing}")
                return

            self._move_linear(controller, hold, vel=vel, acc=acc)
            self._move_linear(controller, pre, vel=vel, acc=acc)
            self._move_joint(controller, app_j, vel=vel, acc=acc)
            return

        if name.startswith("COF") and name.endswith(("_Up_L", "_Place_L")):
            num = name.replace("COF", "").replace("_Up_L", "").replace("_Place_L", "").strip()
            place = self._get_point(f"COF{num}_Place_L")
            up = self._get_point(f"COF{num}_Up_L")
            app_j = self._get_point("MAC_App_J")

            missing = [k for k, v in {
                f"COF{num}_Place_L": place,
                f"COF{num}_Up_L": up,
                "MAC_App_J": app_j,
            }.items() if v is None]

            if missing:
                print(f"[BREW][RETURN][COF][WARN] missing points: {missing}")
                return

            self._move_linear(controller, place, vel=vel, acc=acc)
            self._move_linear(controller, up, vel=60, acc=60)
            self._move_joint(controller, app_j, vel=vel, acc=acc)
            return

        if name.startswith("POW") and name.endswith(("_Up_L", "_Place_L")):
            num = name.replace("POW", "").replace("_Up_L", "").replace("_Place_L", "").strip()
            place = self._get_point(f"POW{num}_Place_L")
            up = self._get_point(f"POW{num}_Up_L")
            app_j = self._get_point("MAC_App_J")

            missing = [k for k, v in {
                f"POW{num}_Place_L": place,
                f"POW{num}_Up_L": up,
                "MAC_App_J": app_j,
            }.items() if v is None]

            if missing:
                print(f"[BREW][RETURN][POW][WARN] missing points: {missing}")
                return

            self._move_linear(controller, place, vel=vel, acc=acc)
            self._move_linear(controller, up, vel=60, acc=60)
            self._move_joint(controller, app_j, vel=vel, acc=acc)
            return

        if name.startswith("PIC_") and name.endswith(("_Up_L", "_Place_L")):
            num = name.replace("PIC_", "").replace("_Up_L", "").replace("_Place_L", "").strip()
            home = self._get_point("HOME_J")

            if num == "1":
                self._move_joint(controller, [1.7, -101.6, -132.5, -126.6, 21.0, 0], vel=60, acc=60)
                ret_up = self._get_actual_tcp_pose(controller)
                if ret_up:
                    ret_up = list(ret_up)
                    ret_up[2] = ret_up[2] + 70.0
                    self._move_linear(controller, ret_up, vel=60, acc=60)
                if home:
                    self._move_joint(controller, home, vel=60, acc=60)
                return

            if num == "2":
                ret_l = self._get_point("PIC_Ret_2_L")
                ret_up = self._get_point("PIC_Ret_2_Up_L")

                missing = [k for k, v in {
                    "PIC_Ret_2_L": ret_l,
                    "PIC_Ret_2_Up_L": ret_up,
                    "HOME_J": home,
                }.items() if v is None]

                if missing:
                    print(f"[BREW][RETURN][PIC][WARN] missing points: {missing}")
                    return

                self._move_linear(controller, ret_l, vel=60, acc=60)
                self._move_linear(controller, ret_up, vel=60, acc=60)
                self._move_joint(controller, home, vel=60, acc=60)
                return

        print(f"[BREW][RETURN] no rule for {saved_point_name} (skip)")
    def _get_rail_pulse(self, btn_value: list[str]):
        try:
            hold_area = ["cup1", "cup2", "cup3", "cup4", "ice1", "ice2"]
            pick_area = ["cof1", "cof2", "pow1", "pow2", "pic1", "pic2"]
            
            pz_area = ["pic1","pic2"]
            pulse_dict = {}
            
            for v in btn_value:
                pulse = 0
                if v not in pz_area:
                    print(v)
                    name = re.sub(r'\d+', '', v)
                    number = int(re.findall(r'\d+', v)[0])
                    if v in hold_area:
                        cmd = 'hold_' + name
                    if v in pick_area :
                        cmd = 'place_' + name
                    print(cmd, number)
                    pulse = self.robot_srv_manager.get_rail_pos(cmd, number)

                elif v in pz_area:
                    place_cmd = "place_order"
                    if v == "pic1" :
                        pulse = int(self.robot_srv_manager.get_rail_pos(place_cmd,1))
                    elif v == "pic2" :
                        pulse = int(self.robot_srv_manager.get_rail_pos(place_cmd,0))
                print(pulse)
                pulse_dict[v] = int(pulse)
        except Exception as error :
            print(f"_Get Rail Pulse Error : {error}")
        finally:
            return pulse_dict

    # --- public entrypoints ---
    def run(self, component_cd: str, label: str, controller=None):
        """
        main_window에서 호출하는 entrypoint.
        컴포넌트/라벨 기준으로 모션을 실행하고 필요하면 jog를 엽니다.
        """
        if controller is None:
            return {"open_jog": True, "jog_target": label}

        n = (label or "").lower().strip()
        if n.startswith("cup"):
            par2 = n.replace("cup", "")
            if par2 not in ("1", "2"):
                return {"open_jog": True, "jog_target": label}

            app_j = self._get_point("MAC_App_J")
            app_cup = self._get_point("MAC_App_Cup_L")
            cup_app = self._get_point(f"CUP{par2}_App_L")
            cup_hold = self._get_point(f"CUP{par2}_Hold_L")

            missing = [k for k, v in {
                "MAC_App_J": app_j,
                "MAC_App_Cup_L": app_cup,
                f"CUP{par2}_App_L": cup_app,
                f"CUP{par2}_Hold_L": cup_hold,
            }.items() if v is None]

            if missing:
                print(f"[BREW][CUP][WARN] missing points: {missing}")
                return {"open_jog": True, "jog_target": label}
            
            # Rail
            self._move_rail_before_motion(label)

            self._move_gripper(controller, 100)
            self._move_joint(controller, app_j)
            self._move_linear(controller, app_cup)
            self._move_linear(controller, cup_app)
            self._move_linear(controller, cup_hold)
            self._move_gripper(controller, 7)
            return {"open_jog": True, "jog_target": label}

        if n.startswith("ice"):
            par2 = n.replace("ice", "")
            if par2 not in ("1", "2"):
                return {"open_jog": True, "jog_target": label}

            app_j = self._get_point("MAC_App_J")
            pre_hold = self._get_point(f"ICE{par2}_PreHold_L")
            hold = self._get_point(f"ICE{par2}_Hold_L")

            missing = [k for k, v in {
                "MAC_App_J": app_j,
                f"ICE{par2}_PreHold_L": pre_hold,
                f"ICE{par2}_Hold_L": hold,
            }.items() if v is None]

            if missing:
                print(f"[BREW][ICE][WARN] missing points: {missing}")
                return {"open_jog": True, "jog_target": label}
            
             # Rail
            self._move_rail_before_motion(label)

            self._move_joint(controller, app_j)
            self._move_linear(controller, pre_hold)
            self._move_linear(controller, hold)
            return {"open_jog": True, "jog_target": label}

        if n in ("cof", "coffee") or n.startswith("cof"):
            par2 = n.replace("cof", "").replace("coffee", "")
            if not par2:
                par2 = "1"
            if par2 not in ("1", "2"):
                return {"open_jog": True, "jog_target": label}

            app_j = self._get_point("MAC_App_J")
            up_l = self._get_point(f"COF{par2}_Up_L")
            place_l = self._get_point(f"COF{par2}_Place_L")

            missing = [k for k, v in {
                "MAC_App_J": app_j,
                f"COF{par2}_Up_L": up_l,
                f"COF{par2}_Place_L": place_l,
            }.items() if v is None]

            if missing:
                print(f"[BREW][COF][WARN] missing points: {missing}")
                return {"open_jog": True, "jog_target": label}

             # Rail
            self._move_rail_before_motion(label)

            self._move_joint(controller, app_j)
            self._move_linear(controller, up_l)
            self._move_linear(controller, place_l)
            return {"open_jog": True, "jog_target": label}

        if n in ("pow", "powder") or n.startswith("pow"):
            par2 = n.replace("pow", "").replace("powder", "")
            if not par2:
                par2 = "1"
            if par2 not in ("1", "2"):
                return {"open_jog": True, "jog_target": label}

            app_j = self._get_point("MAC_App_J")
            up_l = self._get_point(f"POW{par2}_Up_L")
            place_l = self._get_point(f"POW{par2}_Place_L")

            missing = [k for k, v in {
                "MAC_App_J": app_j,
                f"POW{par2}_Up_L": up_l,
                f"POW{par2}_Place_L": place_l,
            }.items() if v is None]

            if missing:
                print(f"[BREW][POW][WARN] missing points: {missing}")
                return {"open_jog": True, "jog_target": label}
            
             # Rail
            self._move_rail_before_motion(label)

            self._move_joint(controller, app_j)
            self._move_linear(controller, up_l)
            self._move_linear(controller, place_l)
            return {"open_jog": True, "jog_target": label}

        if component_cd == "pic":
            par2 = n.replace("pic", "")
            return self._run_pic_motion(par2, controller)

        # TODO: component_cd/label에 따른 실제 모션 정의를 추가
        return {"open_jog": True, "jog_target": label}
    def rail_move_async(self, target_name, rail_position, controller):
        
        self._move_rail_before_motion(target_name, rail_position)

        # 프로그램이 돌고있다면 저장이 됨
        self.RAIL_TARGET_PULSE[target_name] = int(rail_position)
        
    def save_pulse(self, ui_point_name: str, pulse: str):
        """
            ui_point_name: UI에서 사용하는 포인트 이름 (예: "cup1", "cof", "ice" 등)
            pulse: 저장할 펄스 값 (문자열 형태)
        """
        # Implement pulse saving logic here
        print(f"[BREW] save_pulse called: ui_point_name={ui_point_name}, pulse={pulse}")

        hold_area = ["cup1", "cup2", "cup3", "cup4", "ice1", "ice2"]
        pick_area = ["cof1", "cof2", "pow1", "pow2", "pic1", "pic2"]

        need_change_word = ["cof","pow"]

        if ui_point_name in hold_area:
            go_cmd = "hold_"
            back_cmd = "unhold_"
        elif ui_point_name in pick_area:
            go_cmd = "place_"
            back_cmd = "pickup_"

        # 디스펜서 이름과 인덱스 분리


        name = re.sub(r'\d+', '', ui_point_name)
        # 숫자 부분 추출
        if name in need_change_word:
            if name == 'cof':
                name = name.replace("cof","coffee")
            elif name == 'pow':
                name = name.replace("pow","powder")
        number = int(re.findall(r'\d+', ui_point_name)[0])
        print(f"Seperate : {name}, {number}")
        
        go_cmd += name
        go_no = number
        back_cmd += name
        back_no = number
        print(ui_point_name, pulse, name, number)
        
        self.robot_srv_manager.update_rail_pos(
            command=go_cmd,
            no=go_no,
            rail_pos=pulse
        )
        self.robot_srv_manager.update_rail_pos(
            command=back_cmd,
            no=back_no,
            rail_pos=pulse
        )
        # DB에 저장하는 과정 추가

    

    def save_point(self, ui_point_name: str, controller=None):
        if controller is None:
            return
        saved_point_name = self._resolve_saved_point_name(ui_point_name)
        pose6 = self._tcp_cache.get(saved_point_name)
        if pose6 is None:
            pose6 = self._get_point(saved_point_name)
        if pose6 is None:
            print(f"[BREW] save_point failed: no cached pose for {saved_point_name}")
            return

        pose6 = list(pose6[:6])

        if saved_point_name.startswith("COF") and saved_point_name.endswith("_Place_L"):
            up_name = saved_point_name.replace("_Place_L", "_Up_L")
            up_pose = list(pose6)
            up_pose[2] += 35.0
            self.points_manager.update_point_in_db(up_name, up_pose)
            self._set_point_cache(up_name, up_pose)
            self._return_motion_after_save(up_name, controller,
                                           vel=self.DEFAULT_RETURN_VEL,
                                           acc=self.DEFAULT_RETURN_ACC)
            return

        if saved_point_name.startswith("POW") and saved_point_name.endswith("_Place_L"):
            up_name = saved_point_name.replace("_Place_L", "_Up_L")
            up_pose = list(pose6)
            up_pose[2] += 35.0
            self.points_manager.update_point_in_db(up_name, up_pose)
            self._set_point_cache(up_name, up_pose)
            self._return_motion_after_save(up_name, controller,
                                           vel=self.DEFAULT_RETURN_VEL,
                                           acc=self.DEFAULT_RETURN_ACC)
            return

        if saved_point_name.startswith("PIC_") and saved_point_name.endswith("_Place_L"):
            num = saved_point_name.replace("PIC_", "").replace("_Place_L", "")
            up_name = saved_point_name.replace("_Place_L", "_Up_L")
            up_pose = list(pose6)
            if num == "1":
                up_pose[2] += 100.0
            elif num == "2":
                up_pose[2] += 190.0
            else:
                print(f"[BREW][PIC][WARN] unknown pic number: {num}")
            self.points_manager.update_point_in_db(up_name, up_pose)
            self._set_point_cache(up_name, up_pose)
            self._return_motion_after_save(up_name, controller,
                                           vel=self.DEFAULT_RETURN_VEL,
                                           acc=self.DEFAULT_RETURN_ACC)
            return

        self.points_manager.update_point_in_db(saved_point_name, pose6)
        self._set_point_cache(saved_point_name, pose6)
        self._return_motion_after_save(saved_point_name, controller,
                                       vel=self.DEFAULT_RETURN_VEL,
                                       acc=self.DEFAULT_RETURN_ACC)
        
    def jog_tcp(self, ui_point_name: str, direction: str, step: float, controller=None):
        if controller is None:
            print("[BREW] jog_tcp ignored: controller is None")
            return

        saved_point = self._resolve_saved_point_name(ui_point_name)
        pose = self._tcp_cache.get(saved_point)
        if pose is None:
            pose = self._get_point(saved_point)
            if pose is None:
                print(f"[BREW] jog_tcp failed: base point not found: {saved_point}")
                return
            pose = list(pose[:6])
            self._tcp_cache[saved_point] = pose

        dx = dy = dz = 0.0
        if direction == "x+":
            dx = step
        elif direction == "x-":
            dx = -step
        elif direction == "y+":
            dy = step
        elif direction == "y-":
            dy = -step
        elif direction == "z+":
            dz = step
        elif direction == "z-":
            dz = -step
        else:
            print(f"[BREW] jog_tcp unknown direction: {direction}")
            return

        new_pose = list(pose)
        new_pose[0] += dx
        new_pose[1] += dy
        new_pose[2] += dz

        self._tcp_cache[saved_point] = new_pose
        self._set_point_cache(saved_point, new_pose)
        self._move_linear(controller, new_pose, vel=20, acc=20)


# -------------------------
# Rail low-level
# -------------------------
class _RailConst:

    SOCKET_RECV_BUFFER_SIZE = 1024
    STATUS_INDEX_FALLBACK = 5      # 원본: response[5]
    POS_START = 6
    POS_END = 10


class _RailPacket:
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


class _RailCheck:
    IDLE = 0


class _RailClient:
    """
    ✅ 원본 RailComponent 규칙에 맞춘 BrewService 전용 Rail TCP Client
    - sync_no: 1~255만 사용(0 금지)  ✅ 원본 raise_sync_number와 동일
    - status 인덱스: response[1](length) 기반으로 유동 대응  ✅ 원본 check_move_bytes 대응
    - MOVE payload: 원본 move_position_Velocity 포맷 그대로
    - position poll 로그 옵션 제공
    """

    def __init__(self, ip: str, port: int, timeout: float = 3.0, use_real_robot=False):

        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.sock = None
        self.sync_no = 0
        self._lock = Lock()
        self.use_real_robot = use_real_robot
    # -------------------------
    # socket lifecycle
    # -------------------------
    def connect(self, do_init: bool = True):
        if self.sock:
            return

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 원본은 SO_REUSEPORT 사용 (환경에 따라 없을 수 있어서 try)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except Exception:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        s.connect((self.ip, self.port))
        s.settimeout(self.timeout)
        # 원본: connect 후 timeout 설정(10)했지만, 여기선 timeout 그대로 유지
        self.sock = s

        if do_init:
            self.init_sequence()

    def close(self):
        try:
            if self.sock:
                try:
                    self.sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                self.sock.close()
        finally:
            self.sock = None

    # -------------------------
    # packet helpers
    # -------------------------
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
                    _RailPacket.HEADER,
                    length,
                    self._raise_sync_compat(),   # ✅ 아래 함수 참고
                    _RailPacket.RESERVED,
                    command,
                    set
                ])

            elif extra is not None:
                base = [_RailPacket.HEADER, length, self._raise_sync_compat(), _RailPacket.RESERVED, command] + list(extra)
                data = bytearray(base)

            elif init is not None:
                base = [_RailPacket.HEADER, length, self._raise_sync_compat(), _RailPacket.RESERVED, command]
                base.append(init[0])
                base.extend(bytearray(init[1]))
                data = bytearray(base)

            else:
                data = bytearray([_RailPacket.HEADER, length, self._raise_sync_compat(), _RailPacket.RESERVED, command])

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

    def _recv_some(self) -> bytes:
        if not self.sock:
            raise RuntimeError("rail socket is not connected")
        chunk = self.sock.recv(_RailConst.SOCKET_RECV_BUFFER_SIZE)
        if not chunk:
            raise ConnectionError("rail socket closed by peer")
        return chunk

    def _send_and_recv(self, pkt: bytes, min_resp_len: int = 6) -> bytes:
        # self.connect(do_init=False)
        with self._lock:
            self.sock.sendall(pkt)

            # ✅ 최소 길이만큼 누적 수신 (TCP 분할 대비)
            buf = bytearray()
            while len(buf) < min_resp_len:
                buf.extend(self._recv_some())
            return bytes(buf)

    # -------------------------
    # response check
    # -------------------------
    # def _status_index(self, resp: bytes) -> int:
    #     """
    #     ✅ 원본 check_move_bytes(): data_index = bl[1] + 1
    #     - 일반 응답(길이 0x04)면 5가 됨(=fallback과 동일)
    #     - 혹시 길이가 큰 프레임이 오면 그에 맞춰 status 위치를 맞춤
    #     """
    #     if not resp or len(resp) < 2:
    #         return _RailConst.STATUS_INDEX_FALLBACK
    #     length_field = resp[1]
    #     idx = length_field + 1
    #     if idx < len(resp):
    #         return idx
    #     return _RailConst.STATUS_INDEX_FALLBACK

    def _status_index(self, resp: bytes) -> int:
        return _RailConst.STATUS_INDEX_FALLBACK  # 항상 5
    
    def _check_idle_or_raise(self, resp: bytes, label: str):
        if resp is None or len(resp) < 6:
            raise RuntimeError(f"rail response too short ({label}): {list(resp) if resp else resp}")

        idx = self._status_index(resp)
        if idx >= len(resp):
            idx = _RailConst.STATUS_INDEX_FALLBACK

        status = resp[idx]
        if status != _RailCheck.IDLE:
            print(f"[BREW][RAIL][WARN] rail cmd failed ({label}): status={status}, resp={list(resp)}")
            return status
            # raise RuntimeError(f"rail cmd failed ({label}): status={status}, resp={list(resp)}")
        return status
    
    # -------------------------
    # low-level getters
    # -------------------------
    def get_motion_bits(self) -> int:
        pkt = self._make_packet(length=_RailPacket.GET_DATA, command=_RailPacket.GET_MOTION)
        resp = self._send_and_recv(pkt, min_resp_len=10)
        self._check_idle_or_raise(resp, "get_motion")
        return int.from_bytes(resp[6:10], "little", signed=False)

    def get_alarm_type_byte(self) -> int:
        pkt = self._make_packet(length=_RailPacket.GET_DATA, command=_RailPacket.GET_ALARM_TYPE)
        resp = self._send_and_recv(pkt, min_resp_len=7)
        self._check_idle_or_raise(resp, "get_alarm_type")
        return resp[6]

    def get_position_pulse(self) -> int:
        pkt = self._make_packet(length=_RailPacket.GET_DATA, command=_RailPacket.GET_POSITION)
        resp = self._send_and_recv(pkt, min_resp_len=10)
        self._check_idle_or_raise(resp, "get_position")
        return int.from_bytes(resp[_RailConst.POS_START:_RailConst.POS_END], "little", signed=False)

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

    # -------------------------
    # commands
    # -------------------------
    def alarm_reset(self):
        pkt = self._make_packet(length=_RailPacket.GET_DATA, command=_RailPacket.ALARM_RESET)
        resp = self._send_and_recv(pkt, min_resp_len=6)

        self._check_idle_or_raise(resp, "alarm_reset")
        return resp

    def servo_on(self, on: bool = True):
        pkt = self._make_packet(
            length=_RailPacket.SET_DATA,
            command=_RailPacket.SERVO_ON,
            set=_RailPacket.SET_ON if on else _RailPacket.SET_OFF,
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
            + list(bytes(_RailPacket.FILLBYTE_LEN))  # 24 bytes of 0x00
        )

        payload = bytes(extra_value)

        # ✅ length는 반드시 0x2B 사용 (기존 DataLength.MOVE_DATA_LENGTH와 동일)
        pkt = self._make_packet(
        length=_RailPacket.MOVE_DATA_LENGTH,     # 0x2b
        command=_RailPacket.MOVE_POS_VELOCITY,
        extra=extra_value,                       # ✅ payload 대신 extra
        )

        resp = self._send_and_recv(pkt, min_resp_len=6)
        self._check_idle_or_raise(resp, "move_pos_velocity")
        return resp

    def move_to_pulse_and_wait(
        self,
        target_pulse: int,
        pps: int = 100000,
        pulse_diff: int = 50,
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
        if abs(start - target_pulse) <= pulse_diff:
            if log_poll:
                print(f"[BREW][RAIL][POS] already at target: start={start}, target={target_pulse}, tol={tol}")
            return start

        self.move_pos_velocity(target_pulse, pps)

        t0 = time.time()
        last_log = 0.0
        last = None

        while True:
            curr = self.get_position_pulse()

            if log_poll and (time.time() - last_log) >= log_period_s:
                print(f"[BREW][RAIL][POS] curr={curr}, target={target_pulse}, diff={curr-target_pulse}")
                last_log = time.time()

            if abs(curr - target_pulse) <= pulse_diff:
                return curr

            if (time.time() - t0) > timeout_s:
                raise TimeoutError(f"rail move timeout: start={start}, target={target_pulse}, curr={curr}, last={last}")

            last = curr
            time.sleep(0.05)
