def hm_to_min(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)

def min_to_hm(value: int) -> str:
    value = max(0, value)
    return f"{value // 60:02d}:{value % 60:02d}"
