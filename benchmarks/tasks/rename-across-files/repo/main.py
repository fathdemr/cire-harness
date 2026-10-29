from shapes import calc_area

ROOMS = [(2, 4), (3, 4)]

total = sum(calc_area(w, h) for w, h in ROOMS)
print(f"total area: {total}")
