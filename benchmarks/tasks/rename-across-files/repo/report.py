import shapes

PLOTS = [(1, 5), (3, 4), (2, 2)]


def largest():
    return max(shapes.calc_area(w, h) for w, h in PLOTS)


if __name__ == "__main__":
    print(f"largest: {largest()}")
