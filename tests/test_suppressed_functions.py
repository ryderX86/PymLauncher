import timeit

from launcher.functions import suppressable


class WrapperTimer:
    @suppressable
    def wrapped_method(self):
        return True

    def non_wrapped_method(self):
        return True


def test_timings():
    # pylint: disable=possibly-unused-variable
    instance = WrapperTimer()

    method_default = timeit.timeit(
        stmt="instance.non_wrapped_method()",
        globals=locals(),
        number=1_000_000,
    )
    method_wrapped = timeit.timeit(
        stmt="instance.wrapped_method()", globals=locals(), number=1_000_000
    )
    overhead_method = method_wrapped - method_default

    def func_default():
        return True

    @suppressable
    def func_wrapped():
        return True

    function_default = timeit.timeit(
        stmt="func_default()", globals=locals(), number=1_000_000
    )
    function_wrapped = timeit.timeit(
        stmt="func_wrapped()", globals=locals(), number=1_000_000
    )
    function_overhead = function_wrapped - function_default

    print(f"Lone method: {method_default}s/1m calls")
    print(f"Wrapped method: {method_wrapped}s/1m calls")
    print(f"Wrapped method overhead: {overhead_method}s/1m calls")
    print(f"Function: {function_default}s/1m calls")
    print(f"Wrapped function: {function_wrapped}s/1m calls")
    print(f"Wrapped function overhead: {function_overhead}s/1m calls")

    if overhead_method > 1.0:
        raise RuntimeError(
            "Wrapped method overhead exceeded 1s "
            f"(full overhead: {overhead_method})"
        )
    if function_overhead > 1.0:
        raise RuntimeError(
            "Wrapped function overhead exceeded 1s "
            f"(full overhead: {function_overhead})"
        )
