from os import name
import subprocess

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
    
from ros.cup_service_client import CupServiceClient


class BrewXResult:
    def __init__(self, open_jog=True, jog_target=None, jog_mode="tcp", ui_extras=None):
        self.open_jog = open_jog
        self.jog_target = jog_target
        self.jog_mode = jog_mode
        self.ui_extras = ui_extras or {}


class BrewXService:
    def __init__(self, points_manager=None):
        self.points_manager = points_manager

        self._tcp_cache = {}  # saved_point_name -> [x,y,z,rx,ry,rz]

        try:
            self.cup_client = CupServiceClient()
        except Exception as e:
            print(f"[SEQ][WARN] CupServiceClient init failed: {e}")
            self.cup_client = None

        # ✅ 저장 포인트명 기준으로 복귀 포인트를 만드는 규칙(필요시 계속 추가)
        # key: (starts_with, ends_with) 패턴
        # value: (down_suffix, ret_suffix, appj_name or suffix)
        self.RETURN_RULES = [
            # CUPn_Hold_L -> CUPn_Down_L -> CUPn_Ret_L -> CUPn_App_J
            ("CUP", "_Hold_L", ("_Down_L", "_Ret_L", "_App_J")),
            # ("ICE", "_Hold_L", ("_Hold_L", "_PreHold_L", "_App_J")),  # ICE는 별도 처리 -> App에서 분기가 발생함
            ("COF", "_Place_L", ("_Place_L", "_Up_L", "_Ret_L", "_App_J")),  # 그리퍼 동작 필요
            ("POW", "_Place_L", ("_Place_L", "_Up_L", "_Ret_L", "_App_J")),  # 그리퍼 동작 필요
        ]

        self.DEFAULT_RETURN_VEL = 25
        self.DEFAULT_RETURN_ACC = 25

    def cup_extract_async(self, ui_point_name: str):
        n = (ui_point_name or "").lower().strip()
        if not n.startswith("cup"):
            return

        num = n.replace("cup", "")
        if num not in ("1", "2", "3"):
            return

        ch = int(num)

        # ✅ UI 멈춤 없이 서비스 호출
        self.cup_client.dispense_async(
            channel=ch,
            on_done=lambda resp: print(f"[SEQ][CUP] ok: {resp}"),
            on_error=lambda e: print(f"[SEQ][CUP][ERR] {e}")
        )

    # ───────────── util ─────────────
    def _get_point(self, name: str):
        if self.points_manager is None:
            return None
        return self.points_manager.points_dict.get(name)

    def _set_point_cache(self, name: str, pose6):
        """✅ points_manager 캐시 반영 (DB 저장의 기준이 되는 값)"""
        if self.points_manager is None:
            return
        self.points_manager.points_dict[name] = list(pose6[:6])

    def _run_place_sequence(self, prefix: str, ui_name: str, controller, vel=30, acc=30):
        """
        공통 Place 시퀀스:
        {prefix}_App_J -> {prefix}_Up_L -> {prefix}_Place_L 이동 후
        jog용 캐시/points_dict 세팅
        """
        appj  = self._get_point(f"{prefix}_App_J")
        up    = self._get_point(f"{prefix}_Up_L")
        place = self._get_point(f"{prefix}_Place_L")

        missing = [k for k, v in {
            f"{prefix}_App_J": appj,
            f"{prefix}_Up_L": up,
            f"{prefix}_Place_L": place,
        }.items() if v is None]

        if missing:
            print(f"[SEQ][{prefix}][WARN] missing points: {missing}")
            return {"open_jog": True, "jog_target": ui_name}

        self._move_joint(controller, appj, vel=vel, acc=acc)
        self._move_linear(controller, up,   vel=vel, acc=acc)
        self._move_linear(controller, place,vel=vel, acc=acc)
        

        # ✅ 저장 타겟(Place) 캐시 세팅
        saved_point = f"{prefix}_Place_L"  # coffee/powder는 항상 여기 저장
        self._tcp_cache[saved_point] = list(place[:6])
        self._set_point_cache(saved_point, place[:6])

        return {"open_jog": True, "jog_target": saved_point}

    def _resolve_saved_point_name(self, ui_point_name: str) -> str:
        """
        UI 이름(cup1) -> 실제 저장 포인트(CUP1_Hold_L)
        """
        n = (ui_point_name or "").lower().strip()

        # 이미 포인트 형식이면 그대로(대소문자만 정리)
        if "_" in ui_point_name:
            return ui_point_name.strip()

        if n.startswith("cup"):
            num = n.replace("cup", "")
            return f"CUP{num}_Hold_L"

        if n.startswith("ice"):
            num = n.replace("ice", "")
            return f"ICE{num}_Hold_L"

        if n.startswith("coffee"):
            return "COF_Place_L"

        if n.startswith("pow"):
            return "POW_Place_L"

        if n.startswith("pic") and len(n) == 5:
            par2 = n[3]
            par3 = n[4]
            return f"PIC{par2}_{par3}_Place_L"

        return ui_point_name.strip()

    def _parse_pic(self, ui_name: str):
        """
        UI 입력 'pic12' 형태에서 (par2, par3)를 파싱한다.
        par2: 1~6, par3: 1~2 아니면 (None, None) 반환.
        """
        n = (ui_name or "").lower().strip()
        try:
            if len(n) != 5 or not n.startswith("pic"):
                return None, None
            par2 = n[3]
            par3 = n[4]
            if par2 not in ("1", "2", "3", "4", "5", "6"):
                return None, None
            if par3 not in ("1", "2"):
                return None, None
            return par2, par3
        except Exception as e:
            print(f"[SEQ][WARN] _parse_pic failed: {e}")
            return None, None
    
    def _move_joint(self, controller, joints, vel=20, acc=20):
        if controller is None or joints is None:
            return
        if hasattr(controller, "move_joint"):
            controller.move_joint(joints, vel=vel, acc=acc)

    def _move_linear(self, controller, pose, vel=20, acc=20, blendR=None):
        if controller is None or pose is None:
            return
        if hasattr(controller, "move_linear"):
            controller.move_linear(pose, vel=vel, acc=acc, blendR=blendR)

    def _move_gripper(self, controller, pos: int):
        if controller is None:
            return
        if hasattr(controller, "move_gripper"):
            controller.move_gripper(pos)

    # ───────────── public ─────────────
    def _print_saved_box(self, name: str, pose):
        line = "=" * 50
        print(f"\n{line}")
        print(f"   저장 완료 : {name}")
        print(f"   좌표 : {pose}")
        print(f"{line}\n")

    def save_point(self, ui_point_name: str, controller=None):
        if controller is None:
            return

        saved_point_name = self._resolve_saved_point_name(ui_point_name)

        # 🔥 캐시 우선
        pose6 = self.points_manager.points_dict.get(saved_point_name)

        if pose6 is None:
            print(f"[SEQ] save_point failed: no cached pose for {saved_point_name}")
            return

        pose6 = list(pose6[:6])
        
        # ✅ 2) PIC는 Place를 조그하지만 DB에는 Up를 저장해야 함
        if saved_point_name.startswith("PIC") and saved_point_name.endswith("_Place_L"):
            up_name = saved_point_name.replace("_Place_L", "_Up_L")
            up_pose = list(pose6)
            up_pose[2] += 30  # ✅ Place -> Up (Z + 30)

            print(f"[SEQ][PIC] save Up_L: {up_name} <- Place({saved_point_name}) + z30 -> {up_pose}")

            # DB 저장은 Up로
            self.points_manager.update_point_in_db(up_name, up_pose)

            # 캐시도 Up 반영(다음 동작/복귀에 활용)
            self._set_point_cache(up_name, up_pose)

            # ✅ 저장 후 복귀는 Up 기준으로 호출(내부에서 Place도 같이 사용 가능)
            self._return_motion_after_save(up_name, controller,
                                        vel=self.DEFAULT_RETURN_VEL,
                                        acc=self.DEFAULT_RETURN_ACC)
            self._print_saved_box(up_name, up_pose)
            return

        # ✅ COF/POW: Place 조그 → Up 저장 (Z + 50)
        if (saved_point_name in ("COF_Place_L", "POW_Place_L")):
            up_name = saved_point_name.replace("_Place_L", "_Up_L")
            up_pose = list(pose6)
            up_pose[2] += 50  # ✅ Place -> Up

            print(f"[SEQ][{up_name.split('_')[0]}] save Up_L: {up_name} <- {saved_point_name} + z50 -> {up_pose}")
            self.points_manager.update_point_in_db(up_name, up_pose)
            self._set_point_cache(up_name, up_pose)
            self._return_motion_after_save(up_name, controller, vel=self.DEFAULT_RETURN_VEL, acc=self.DEFAULT_RETURN_ACC)
            self._print_saved_box(up_name, up_pose)
            return

        print(f"[SEQ] save_point: {saved_point_name} -> {pose6}")

        # DB 저장
        self.points_manager.update_point_in_db(saved_point_name, pose6)

        self._return_motion_after_save(
            saved_point_name,
            controller,
            vel=self.DEFAULT_RETURN_VEL,
            acc=self.DEFAULT_RETURN_ACC
        )
        # 저장 후 복귀
        self._print_saved_box(saved_point_name, pose6)
    
    # ───────────── return motion ─────────────
    def _return_motion_after_save(self, saved_point_name: str, controller, vel=45, acc=45):

        if controller is None:
            return

        name = (saved_point_name or "").strip()

        # ✅ PIC: saved는 Up_L로 들어온다
        if name.startswith("PIC") and name.endswith("_Up_L"):
            # 예: PIC6_1_Up_L
            try:
                head = name.split("_")[0]           # "PIC6"
                par3 = name.split("_")[1]           # "1" or "2"
                par2 = head.replace("PIC", "")      # "6"
            except Exception:
                print(f"[SEQ][RETURN][PIC][WARN] cannot parse: {name}")
                return

            up_name = name
            place_name = name.replace("_Up_L", "_Place_L")
            ret_name = f"PIC{par2}_{par3}_Ret_L"
            ret_up_name = f"PIC{par2}_Ret_Up_L"
            pic_app_j = "PIC_App_J"
            home_j = "HOME_J"

            # ✅ Place는 캐시에 남아있을 가능성이 큼(조그 누적값)
            place = self._get_point(place_name)
            if place is None:
                # fallback: Up에서 z-30으로 Place 추정
                up = self._get_point(up_name)
                if up:
                    place = list(up[:6])
                    place[2] -= 30.0

            ret = self._get_point(ret_name)
            ret_up = self._get_point(ret_up_name)
            appj = self._get_point(pic_app_j)
            home = self._get_point(home_j)

            print(f"[SEQ][RETURN][PIC] {place_name} -> {ret_name} -> {ret_up_name} -> ({pic_app_j if par2=='6' else 'skip'}) -> {home_j}")

            if place:  self._move_linear(controller, place, vel=vel, acc=acc)
            if ret:    self._move_linear(controller, ret,   vel=60, acc=60)
            if ret_up: self._move_linear(controller, ret_up,vel=60, acc=60)
            if par2 == "6" and appj:
                self._move_joint(controller, appj, vel=60, acc=60)
            if home:
                self._move_joint(controller, home, vel=60, acc=60)
            return

        # ✅ ICE: ICE{n}_Hold_L -> ICE{n}_PreHold_L -> ICE_App_J
        if name.startswith("ICE") and name.endswith("_Hold_L"):
            num = name.replace("ICE", "").replace("_Hold_L", "")
            hold = self._get_point(f"ICE{num}_Hold_L")
            pre  = self._get_point(f"ICE{num}_PreHold_L")
            appj = self._get_point("ICE_App_J")

            missing = [n for n, p in [
                (f"ICE{num}_Hold_L", hold),
                (f"ICE{num}_PreHold_L", pre),
                ("ICE_App_J", appj),
            ] if p is None]

            if missing:
                print(f"[SEQ][RETURN][ICE][WARN] missing points: {missing}")
                return

            print(f"[SEQ][RETURN][ICE] {name} -> ICE{num}_PreHold_L -> ICE_App_J (vel={vel} acc={acc})")
            self._move_linear(controller, hold, vel=vel, acc=acc)
            self._move_linear(controller, pre,  vel=vel, acc=acc)
            self._move_joint(controller,  appj, vel=vel, acc=acc)
            return

        # ✅ CUP: CUPn_Hold_L -> CUPn_Down_L -> CUPn_Ret_L -> CUPn_App_J
        if name.startswith("CUP") and name.endswith("_Hold_L"):
            base = name[:-len("_Hold_L")]
            step_names = [
                f"{base}_Hold_L",
                f"{base}_Down_L",
                f"{base}_Ret_L",
                f"{base}_App_J",
            ]
            self._do_return(step_names, controller, vel, acc)
            return

        # ✅ COF: COF_Place_L -> COF_Up_L -> COF_Ret_L -> COF_App_L
        if name.startswith("COF"):
            step_names = ["COF_Place_L", "COF_Up_L", "COF_Ret_L", "COF_App_L"]
            self._do_return(step_names, controller, vel, acc)
            return

        # ✅ POW: POW_Place_L -> POW_Up_L -> POW_Ret_L -> POW_App_L
        if name.startswith("POW"):
            step_names = ["POW_Place_L", "POW_Up_L", "POW_Ret_L", "POW_App_L"]
            self._do_return(step_names, controller, vel, acc)
            return

        print(f"[SEQ][RETURN] no rule for {name} (skip)")

    def _do_return(self, step_names, controller, vel, acc):
        points = [self._get_point(n) for n in step_names]
        missing = [n for n, p in zip(step_names, points) if p is None]
        if missing:
            print(f"[SEQ][RETURN][WARN] skipped, missing points: {missing}")
            return

        print(f"[SEQ][RETURN] vel={vel} acc={acc}: " + " -> ".join(step_names))
        for nm, pt in zip(step_names[:-1], points[:-1]):
            self._move_linear(controller, pt, vel=vel, acc=acc)
        last_name, last_pt = step_names[-1], points[-1]
        if last_name.endswith("_J"):
            self._move_joint(controller, last_pt, vel=vel, acc=acc)
        else:
            self._move_linear(controller, last_pt, vel=vel, acc=acc)

    def run(self, ui_name: str, controller=None):
        """
        main_window에서 호출하는 entrypoint.
        cup 버튼이면: App_J -> Ret_L -> Down_L -> Hold_L 이동 후 jog 열기
        """
        if controller is None:
            return {"open_jog": True, "jog_target": ui_name}

        n = (ui_name or "").lower().strip()

        if n.startswith("cup"):
            num = n.replace("cup", "")
            if num not in ("1", "2", "3"):
                return {"open_jog": True, "jog_target": ui_name}

            prefix = f"CUP{num}"
            appj = self._get_point(f"{prefix}_App_J")
            ret  = self._get_point(f"{prefix}_Ret_L")
            down = self._get_point(f"{prefix}_Down_L")
            hold = self._get_point(f"{prefix}_Hold_L")

            missing = [k for k,v in {
                f"{prefix}_App_J": appj,
                f"{prefix}_Ret_L": ret,
                f"{prefix}_Down_L": down,
                f"{prefix}_Hold_L": hold,
            }.items() if not v]

            if missing:
                print(f"[SEQ][CUP][WARN] missing points: {missing}")
                return {"open_jog": True, "jog_target": ui_name}
            
            self._move_gripper(controller, pos=7)  # 그리퍼 닫기
            self._move_joint(controller, appj, vel=20, acc=20)
            self._move_linear(controller, ret,  vel=20, acc=20)
            self._move_linear(controller, down, vel=20, acc=20)
            self._move_linear(controller, hold, vel=20, acc=20)

            # 캐시 초기화(hold 기준)
            self._tcp_cache[f"{prefix}_Hold_L"] = list(hold[:6])

            return {"open_jog": True, "jog_target": ui_name}

        if n.startswith("ice"):
            num = n.replace("ice", "")
            if num not in ("1", "2"):
                return {"open_jog": True, "jog_target": ui_name}

            appj = self._get_point("ICE_App_J")
            prehold = self._get_point(f"ICE{num}_PreHold_L")
            hold = self._get_point(f"ICE{num}_Hold_L")

            missing = [k for k, v in {
                "ICE_App_J": appj,
                f"ICE{num}_PreHold_L": prehold,
                f"ICE{num}_Hold_L": hold,
            }.items() if v is None]

            if missing:
                print(f"[SEQ][ICE][WARN] missing points: {missing}")
                return {"open_jog": True, "jog_target": ui_name}

            # ✅ ICE 시퀀스: App_J -> PreHold_L -> Hold_L
            self._move_joint(controller, appj, vel=60, acc=60)
            self._move_linear(controller, prehold, vel=20, acc=20)
            self._move_linear(controller, hold, vel=20, acc=20)

            # ✅ jog 기준값(hold)을 캐시 + points_dict에 세팅 (누적 조그 저장용)
            saved_point = self._resolve_saved_point_name(ui_name)  # ICE1_Hold_L / ICE2_Hold_L
            self._tcp_cache[saved_point] = list(hold[:6])
            self._set_point_cache(saved_point, hold[:6])

            return {"open_jog": True, "jog_target": ui_name}
        
        if n in ("cof", "coffee") or n.startswith("cof") or n.startswith("coffee"):
            # normalize to "coffee" label for legacy usage
            if n.startswith("cof"):
                num = n.replace("cof", "") or "1"
                ui_name = f"coffee{num}"
            return self._run_place_sequence("COF", ui_name, controller, vel=20, acc=20)

        if n in ("pow", "powder") or n.startswith("pow"):
            # normalize to "pow" label for legacy usage
            if n in ("pow", "powder"):
                ui_name = "pow1"
            return self._run_place_sequence("POW", ui_name, controller, vel=20, acc=20)

        if n.startswith("pic") and len(n) == 5:
            par2, par3 = self._parse_pic(ui_name)
            if par2 is None:
                return {"open_jog": True, "jog_target": ui_name}

            home = self._get_point("HOME_J")
            pic_app_j = self._get_point("PIC_App_J")
            app_l = self._get_point(f"PIC{par2}_App_L")
            up_l = self._get_point(f"PIC{par2}_{par3}_Up_L")
            place_l = self._get_point(f"PIC{par2}_{par3}_Place_L")

            missing = [k for k,v in {
                "HOME_J": home,
                "PIC_App_J": pic_app_j,
                f"PIC{par2}_App_L": app_l,
                f"PIC{par2}_{par3}_Up_L": up_l,
                f"PIC{par2}_{par3}_Place_L": place_l,
            }.items() if v is None]

            if missing:
                print(f"[SEQ][PIC][WARN] missing points: {missing}")
                return {"open_jog": True, "jog_target": ui_name}

            # 원본 속도
            self._move_joint(controller, home,      vel=30, acc=15)
            self._move_joint(controller, pic_app_j, vel=60, acc=60)
            self._move_linear(controller, app_l,    vel=60, acc=60, blendR=30.0)
            self._move_linear(controller, up_l,     vel=60, acc=60)
            self._move_linear(controller, place_l,  vel=20, acc=15)

            # ✅ 조그는 Place를 기준으로 누적
            place_name = f"PIC{par2}_{par3}_Place_L"
            self._tcp_cache[place_name] = list(place_l[:6])
            self._set_point_cache(place_name, place_l[:6])

            # ✅ JogDialog의 target_name을 place_name으로 열어야 jog_tcp가 Place를 움직임
            return {"open_jog": True, "jog_target": place_name}

        return {"open_jog": True, "jog_target": ui_name}

    def jog_tcp(self, ui_point_name: str, direction: str, step: float, controller=None):
        if controller is None:
            print("[SEQ] jog_tcp ignored: controller is None")
            return

        saved_point = self._resolve_saved_point_name(ui_point_name)

        # 1) 기준 pose: _tcp_cache -> points_dict
        pose = self._tcp_cache.get(saved_point)
        if pose is None:
            pose = self._get_point(saved_point)
            if pose is None:
                print(f"[SEQ] jog_tcp failed: base point not found: {saved_point}")
                return
            pose = list(pose[:6])
            self._tcp_cache[saved_point] = pose

        # 2) delta
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
            print(f"[SEQ] jog_tcp unknown direction: {direction}")
            return

        # 3) 누적
        new_pose = list(pose)
        new_pose[0] += dx
        new_pose[1] += dy
        new_pose[2] += dz

        self._tcp_cache[saved_point] = new_pose

        # ✅ 중요: points_manager cache에도 반영 (Saved가 이 값을 저장함)
        self._set_point_cache(saved_point, new_pose)

        # 4) 이동
        self._move_linear(controller, new_pose, vel=20, acc=20)

