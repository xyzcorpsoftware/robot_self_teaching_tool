"""BREW cup motions, copied from production (baris-brew-station-v3 FairinoRobotSuperFastComponent):
hold_motion / unhold_motion ('CUP', 'CUP_FAST') and BrewPointsManager.relative_defs (offsets from Hold, mm).
Developer-owned model definition: ops staff only change the DB points (Hold) and rail pulse.
"""

APP = {1: [0, -100, 0], 2: [0, -130, 0], 3: [0, -130, 0], 4: [0, -130, 0]}
DOWN = [0, 0, -70]
RET = {1: [0, -80, -70], 2: [0, -100, -70], 3: [0, -100, -70], 4: [0, -100, -70]}
FAST_APP = {1: [0, -100, 0], 2: [0, -130, 0], 3: [0, 0, 0], 4: [0, 0, 0]}


def db(name):
    return lambda store: store.point(name)


def off(base, o):
    return lambda store: [v + d for v, d in zip(store.point(base), list(o) + [0, 0, 0])]


def step(title, kind, **kw):
    return {"title": title, "kind": kind, **kw}


def cup(mode, n):
    """→ dict(hold_point, rail_cmd, phases=[(id, name, [steps])]). A 'move' step may send several moves."""
    rail = step("레일 이동", "rail")
    open_ = step("그리퍼 열기", "grip", grip="open")
    close = step("그리퍼 닫기", "grip", grip="close")
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


if __name__ == "__main__":
    # self-check against production values
    from devices import FakeStore
    s = FakeStore()
    h = s.point("CUP1_Hold_L")
    m = cup("NORMAL", 1)
    app_step = m["phases"][0][2][3]
    assert app_step["moves"][0][1](s) == [h[0], h[1] - 100, h[2], *h[3:]]
    ret_step = m["phases"][1][2][1]
    assert ret_step["moves"][0][1](s)[:3] == [h[0], h[1] - 80, h[2] - 70]
    assert cup("NORMAL", 2)["phases"][0][2][3]["moves"][0][1](s)[1] == s.point("CUP2_Hold_L")[1] - 130
    assert cup("FAST", 3)["hold_point"] == "CUP3_FAST_HOLD_L"
    print("motions ok")
