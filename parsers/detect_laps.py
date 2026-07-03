"""赛道计时应用 - 圈标记检测函数（出站圈/进站圈/赛道限制）

从 SwissTimingParser 提取为独立函数，可在不重新上传 CSV 的情况下
对已有数据进行回溯性数据库更新。
"""

import csv


def parse_tlw_file(filepath: str) -> list[dict]:
    """解析 TLWlistMessage CSV 文件

    列格式：Bib;Date & Time;Race time;TL at Turn;Message
    """
    warnings = []

    # 编码检测：优先 UTF-8-sig，回退 Latin-1
    for enc in ("utf-8-sig", "latin-1"):
        try:
            with open(filepath, newline="", encoding=enc) as f:
                rows = list(csv.reader(f, delimiter=";"))
            break
        except UnicodeDecodeError:
            continue
    else:
        return warnings

    for row in rows[1:]:
        if not row or len(row) < 4:
            continue
        bib = row[0].strip()
        if not bib or not bib.isdigit():
            continue
        race_time = _to_seconds(row[2].strip())
        turn = row[3].strip() if len(row) > 3 else ""
        warnings.append({
            "car_number": bib,
            "race_time": race_time,
            "turn": turn,
            "message": row[4].strip() if len(row) > 4 else "",
        })
    return warnings


def _to_seconds(time_str: str) -> float | None:
    """将 Swiss Timing 时间字符串转换为秒数"""
    if not time_str:
        return None
    try:
        parts = time_str.split(":")
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        else:
            return float(time_str)
    except (ValueError, TypeError):
        return None


def detect_out_laps(laps: list[dict]) -> None:
    """检测出站圈：每辆车的第一个 Lap 1 标记为出站圈

    对于重复的 Lap 1 条目（Swiss Timing 数据错误），标记第一个；
    对于单条 Lap 1 条目，标记该条。
    """
    car_groups: dict[str, list[dict]] = {}
    for l in laps:
        car_groups.setdefault(l["car_number"], []).append(l)

    for car_num, car_laps in car_groups.items():
        car_laps.sort(key=lambda x: x["lap_number"])
        for l in car_laps:
            if l["lap_number"] == 1:
                l["out_lap"] = True
                break


def detect_in_laps(laps: list[dict]) -> None:
    """无 PitStopsCsv 时的启发式进站圈检测

    若 lap_time 超过干净圈中位数的 1.2 倍，则标记为进站圈。
    进站圈之后的下一圈标记为出站圈，与分析 API 的进站检测预期模式一致。
    排除第一圈（静止起步）。
    """
    car_groups: dict[str, list[dict]] = {}
    for l in laps:
        car_groups.setdefault(l["car_number"], []).append(l)

    for car_num, car_laps in car_groups.items():
        car_laps.sort(key=lambda x: x["lap_number"])
        clean = sorted([
            l["lap_time"] for l in car_laps
            if l["lap_number"] > 1 and l.get("lap_time") and l["lap_time"] > 0
        ])
        if len(clean) < 2:
            continue
        median = clean[(len(clean) - 1) // 2]
        in_lap_indices: set[int] = set()
        for i, l in enumerate(car_laps):
            if l["lap_number"] > 1 and l.get("lap_time") and l["lap_time"] > median * 1.2:
                l["in_lap"] = True
                in_lap_indices.add(i)
        for i in in_lap_indices:
            if i + 1 < len(car_laps):
                car_laps[i + 1]["out_lap"] = True


def apply_tlw(laps: list[dict], warnings: list[dict]) -> None:
    """将 TLW 赛道限制警告匹配到具体圈数并设置 track_limit 标记

    每条警告的 race_time（累计秒数）与包含该时间的 session_time 范围匹配。
    """
    if not warnings:
        return

    car_warnings: dict[str, list[dict]] = {}
    for w in warnings:
        car_warnings.setdefault(w["car_number"], []).append(w)

    car_laps: dict[str, list[dict]] = {}
    for lap in laps:
        car_laps.setdefault(lap["car_number"], []).append(lap)

    for car_num, car_ws in car_warnings.items():
        c_laps = sorted(car_laps.get(car_num, []), key=lambda x: x["lap_number"])
        if not c_laps:
            continue

        car_ws_sorted = sorted(car_ws, key=lambda w: w["race_time"])

        for w in car_ws_sorted:
            rt = w["race_time"]
            if rt is None:
                continue

            matched = False
            for i, lap in enumerate(c_laps):
                st = lap.get("session_time")
                if st is None:
                    continue

                if i == 0:
                    if rt <= st:
                        lap["track_limit"] = True
                        matched = True
                        break
                else:
                    prev_st = c_laps[i - 1].get("session_time")
                    if prev_st is not None and prev_st < rt <= st:
                        lap["track_limit"] = True
                        matched = True
                        break
                    elif prev_st is None and rt <= st:
                        lap["track_limit"] = True
                        matched = True
                        break

            if not matched and c_laps:
                last = c_laps[-1]
                last_st = last.get("session_time")
                if last_st is not None and rt > last_st:
                    last["track_limit"] = True
