"""One address vocabulary for ordering, store addresses and saved addresses."""

import re


def clean(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def door_number(door: str | None = None, building: str | None = None,
                unit: str | None = None, room: str | None = None) -> str:
    if clean(door):
        return clean(door)
    parts = []
    for value, suffix in ((building, "号楼"), (unit, "单元"), (room, "室")):
        value = clean(value)
        if value:
            parts.append(value + suffix if value.isdigit() else value)
    return "".join(parts)


def full_address(city: str, district: str, estate: str, door: str) -> str:
    values = [clean(city), clean(district), clean(estate), clean(door)]
    if not all(values):
        raise ValueError("请填写城市/区域、小区和门牌号")
    result = " ".join(values)
    if len(result) > 500:
        raise ValueError("地址过长")
    return result
