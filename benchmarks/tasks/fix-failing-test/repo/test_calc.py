import calc

assert calc.add(2, 3) == 5
assert calc.subtract(5, 3) == 2
assert calc.multiply(4, 3) == 12
assert calc.divide(6, 3) == 2
assert calc.divide(7, 2) == 3.5
try:
    calc.divide(1, 0)
except ZeroDivisionError:
    pass
else:
    raise AssertionError("divide by zero should raise")
print("ok")
