"""Cup motions, copied from production (baris-brew-station-v3 FairinoRobotSuperFastComponent):
hold_motion / unhold_motion ('CUP', 'CUP_FAST') and Brew/BrewXPointsManager.relative_defs (offsets from Hold, mm).
Developer-owned model definition: ops staff only change the DB points (Hold) and rail pulse.
"""

APP = {1: [0, -100, 0], 2: [0, -130, 0], 3: [0, -130, 0], 4: [0, -130, 0]}
DOWN = [0, 0, -70]
RET = {1: [0, -80, -70], 2: [0, -100, -70], 3: [0, -100, -70], 4: [0, -100, -70]}
FAST_APP = {1: [0, -100, 0], 2: [0, -130, 0], 3: [0, 0, 0], 4: [0, 0, 0]}
# BREWX (BrewXPointsManager). Only CUP1~3 have CUP{n}_App_J in the DB, so BREWX has 3 slots.
X_DOWN, X_RET, X_FAST_APP = [0, 0, -70], [-100, 0, -70], [-150, 0, 0]
SLOTS = {"BREW": 4, "BREWX": 3}


def db(name):
    return lambda store: store.point(name)


def off(base, o):
    return lambda store: [v + d for v, d in zip(store.point(base), list(o) + [0, 0, 0])]


def step(title, kind, **kw):
    return {"title": title, "kind": kind, **kw}


def cup(hw, mode, n):
    """→ dict(hold_point, rail_cmd, phases=[(id, name, [steps])]). A 'move' step may send several moves."""
    rail = step("레일 이동", "rail")
    open_ = step("그리퍼 열기", "grip", grip="open")
    close = step("그리퍼 닫기", "grip", grip="close")
    if hw == "BREWX":
        return _cup_brewx(mode, n, open_, close)
    if mode == "FAST":
        hold = f"CUP{n}_FAST_HOLD_L"
        app = off(hold, FAST_APP[n])
        return {"hold_point": hold, "rail_cmd": "hold_cup_fast", "phases": [
            ("hold", "① HOLD", [rail, open_,
                                step("준비 자세", "move", moves=[("J", db("READY_CUP_J"))]),
                                step("컵 DP 앞 대기", "move", moves=[("L", db("READY_APP_CUP_L"))]),
                                step("컵 입구 접근", "move", moves=[("L", app)]),
                                step("컵 잡는 위치", "move", moves=[("L", db(hold))], teach=True),
                                close]),
            ("unhold", "② UNHOLD", [step("입구로 빼기", "move", moves=[("L", app)]),
                                    step("컵 DP 앞 대기", "move", moves=[("L", db("READY_APP_CUP_L"))]),
                                    step("준비 자세", "move", moves=[("J", db("READY_CUP_J"))]),
                                    step("기본 자세", "move", moves=[("J", db("MAC_App_J"))])]),
        ]}
    hold = f"CUP{n}_Hold_L"
    return {"hold_point": hold, "rail_cmd": "hold_cup", "phases": [
        ("hold", "① HOLD", [rail, open_,
                            # MAC_App_J and MAC_App_Cup_L are the same pose (J then L) → one step for the user
                            step("컵 DP 앞 대기", "move", moves=[("J", db("MAC_App_J")), ("L", db("MAC_App_Cup_L"))]),
                            step("컵 입구 접근", "move", moves=[("L", off(hold, APP[n]))]),
                            step("컵 잡는 위치", "move", moves=[("L", db(hold))], teach=True),
                            close]),
        ("unhold", "② UNHOLD", [step("아래로 빼기", "move", moves=[("L", off(hold, DOWN))]),
                                step("뒤로 빼기", "move", moves=[("L", off(hold, RET[n]))]),
                                step("컵 DP 앞 대기", "move", moves=[("L", db("MAC_App_Cup_L")), ("J", db("MAC_App_J"))])]),
    ]}


def _cup_brewx(mode, n, open_, close):
    app_j = db(f"CUP{n}_App_J")
    if mode == "FAST":
        hold = f"CUP{n}_FAST_HOLD_L"
        app = off(hold, X_FAST_APP)
        return {"hold_point": hold, "rail_cmd": None, "phases": [
            ("hold", "① HOLD", [step("컵 DP 앞 대기", "move", moves=[("J", app_j)]), open_,
                                step("컵 입구 접근", "move", moves=[("L", app)]),
                                step("컵 잡는 위치", "move", moves=[("L", db(hold))], teach=True),
                                close]),
            ("unhold", "② UNHOLD", [step("입구로 빼기", "move", moves=[("L", app)]),
                                    step("컵 DP 앞 대기", "move", moves=[("J", app_j)])]),
        ]}
    # NORMAL: production closes the gripper first, then comes up under the cup (Ret → Down → Hold)
    hold = f"CUP{n}_Hold_L"
    return {"hold_point": hold, "rail_cmd": None, "phases": [
        ("hold", "① HOLD", [close,
                            step("컵 DP 앞 대기", "move", moves=[("J", app_j)]),
                            step("컵 아래로 접근", "move", moves=[("L", off(hold, X_RET))]),
                            step("컵 바로 아래", "move", moves=[("L", off(hold, X_DOWN))]),
                            step("컵 잡는 위치", "move", moves=[("L", db(hold))], teach=True)]),
        ("unhold", "② UNHOLD", [step("아래로 빼기", "move", moves=[("L", off(hold, X_DOWN))]),
                                step("뒤로 빼기", "move", moves=[("L", off(hold, X_RET))]),
                                step("컵 DP 앞 대기", "move", moves=[("J", app_j)])]),
    ]}


# ── "동작 보기": the production cup motion as the store runs it (order, vel, acc, blend, gripper blocking, waits).
# FRRobotConstants (SuperFast): BREW_CUP_HOLD_UNHOLD_VEL / BREWX_CUP_(UN)HOLD_VEL 90, BREW_VEL 100, BREW_ACC 100,
# BLEND_T -1, BLEND_R 0, BREW_BLEND_CUP_PIC_ZONE_R 50; send_move_* defaults acc 75, blend -1.
# Gripper block: 0 = wait for the gripper, 1 = keep moving while it runs (GRIPPER_NON_BLOCKING).
RAIL_PPS = 340000   # RailComponentConstant.RAIL_NORMAL_SPEED


def J(title, where, vel, acc=75, blend=-1):
    return ("J", title, where, vel, acc, blend)


def L(title, where, vel, acc=75, blend=-1):
    return ("L", title, where, vel, acc, blend)


def grip(title, which, block):
    return ("grip", title, which, block)


def play(hw, mode, n):
    """→ list of actions: ('J'|'L', title, where, vel, acc, blend) / ('grip', title, 'open'|'close', block) /
    ('sleep', title, sec) / ('rail', title). HOLD then UNHOLD, exactly like production hold_motion + unhold_motion."""
    if hw == "BREWX":
        app_j = db(f"CUP{n}_App_J")
        if mode == "FAST":
            h = f"CUP{n}_FAST_HOLD_L"
            app = off(h, X_FAST_APP)
            return [J("컵 DP 앞 대기", app_j, 100, blend=-1), grip("그리퍼 열기", "open", 1),
                    L("컵 입구 접근", app, 100, 70, 50), L("컵 잡는 위치", db(h), 100, 100, 50),
                    grip("그리퍼 닫기", "close", 1),
                    L("컵 잡는 위치", db(h), 100, 100, 50), L("입구로 빼기", app, 100, 100, 50),
                    J("컵 DP 앞 대기", app_j, 100, 100, -1)]
        h = f"CUP{n}_Hold_L"
        return [grip("그리퍼 닫기", "close", 0), J("컵 DP 앞 대기", app_j, 90),
                L("컵 아래로 접근", off(h, X_RET), 90), L("컵 바로 아래", off(h, X_DOWN), 90),
                L("컵 잡는 위치", db(h), 90), ("sleep", "컵 기다리기", 1.0),
                L("컵 잡는 위치", db(h), 90), L("아래로 빼기", off(h, X_DOWN), 90),
                L("뒤로 빼기", off(h, X_RET), 90), J("컵 DP 앞 대기", app_j, 90)]
    if mode == "FAST":
        h = f"CUP{n}_FAST_HOLD_L"
        app = off(h, FAST_APP[n])
        return [("rail", "레일 이동"), grip("그리퍼 열기", "open", 0),
                J("준비 자세", db("READY_CUP_J"), 90), L("컵 DP 앞 대기", db("READY_APP_CUP_L"), 90),
                L("컵 입구 접근", app, 90), L("컵 잡는 위치", db(h), 90),
                grip("그리퍼 닫기", "close", 0), ("sleep", "컵 기다리기", 1.0),
                L("컵 잡는 위치", db(h), 90), L("입구로 빼기", app, 90),
                L("컵 DP 앞 대기", db("READY_APP_CUP_L"), 90), J("준비 자세", db("READY_CUP_J"), 90),
                J("기본 자세", db("MAC_App_J"), 90)]
    h = f"CUP{n}_Hold_L"
    return [("rail", "레일 이동"), J("컵 DP 앞 대기", db("MAC_App_J"), 90, blend=-1), grip("그리퍼 열기", "open", 1),
            L("컵 DP 앞 대기", db("MAC_App_Cup_L"), 90, blend=0), L("컵 입구 접근", off(h, APP[n]), 90, blend=0),
            L("컵 잡는 위치", db(h), 90, blend=0), grip("그리퍼 닫기", "close", 1), ("sleep", "컵 기다리기", 1.0),
            L("컵 잡는 위치", db(h), 90), L("아래로 빼기", off(h, DOWN), 90), L("뒤로 빼기", off(h, RET[n]), 90),
            L("컵 DP 앞 대기", db("MAC_App_Cup_L"), 90), J("기본 자세", db("MAC_App_J"), 90)]


if __name__ == "__main__":
    # self-check against production values
    from devices import FakeStore
    s = FakeStore("BREW")
    h = s.point("CUP1_Hold_L")
    m = cup("BREW", "NORMAL", 1)
    app_step = m["phases"][0][2][3]
    assert app_step["moves"][0][1](s) == [h[0], h[1] - 100, h[2], *h[3:]]
    ret_step = m["phases"][1][2][1]
    assert ret_step["moves"][0][1](s)[:3] == [h[0], h[1] - 80, h[2] - 70]
    assert cup("BREW", "NORMAL", 2)["phases"][0][2][3]["moves"][0][1](s)[1] == s.point("CUP2_Hold_L")[1] - 130
    assert cup("BREW", "FAST", 3)["hold_point"] == "CUP3_FAST_HOLD_L"
    x = FakeStore("BREWX")
    assert x.point("CUP1_Hold_L") == [745, 243, 80, 90, 0, 114]          # from the bx001 dump
    ret = cup("BREWX", "NORMAL", 1)["phases"][0][2][2]["moves"][0][1](x)
    assert ret == [645, 243, 10, 90, 0, 114]                              # Hold + [-100, 0, -70]
    fast = cup("BREWX", "FAST", 2)
    assert fast["phases"][0][2][2]["moves"][0][1](x)[:3] == [744 - 150, 51, 35]
    for mode in ("NORMAL", "FAST"):                                       # every point the motion needs exists
        for n in range(1, SLOTS["BREWX"] + 1):
            for _, _, steps in cup("BREWX", mode, n)["phases"]:
                for st in steps:
                    for _, where in st.get("moves", []):
                        where(x)
    for hw, st_ in (("BREWX", x), ("BREW", s)):                         # play: every point exists, ends where it began
        for mode in ("NORMAL", "FAST"):
            for n in range(1, SLOTS[hw] + 1):
                acts = play(hw, mode, n)
                for a in acts:
                    if a[0] in ("J", "L"):
                        a[2](st_)
                assert acts[-1][0] == "J"
    assert play("BREWX", "FAST", 1)[2][3:] == (100, 70, 50)              # FAST_APP: BREW_VEL, acc 70, CUP_PIC_ZONE_R
    print("motions ok")
