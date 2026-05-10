from selfheal import Result


def test_result_ok_accessors():
    result = Result.ok(2)

    assert result.is_ok() is True
    assert result.is_err() is False
    assert result.value == 2
    try:
        _ = result.error
    except ValueError as exc:
        assert "cannot access error" in str(exc)
    else:
        raise AssertionError("error access on ok Result did not raise")


def test_result_err_accessors():
    result = Result.err("failed")

    assert result.is_ok() is False
    assert result.is_err() is True
    assert result.error == "failed"
    try:
        _ = result.value
    except ValueError as exc:
        assert "cannot access value" in str(exc)
    else:
        raise AssertionError("value access on error Result did not raise")


def test_result_map_transforms_ok_and_preserves_err():
    assert Result.ok(2).map(lambda value: value + 1).value == 3
    assert Result.err("failed").map(lambda value: value + 1).error == "failed"


def test_result_flat_map_chains_ok_and_preserves_err():
    assert Result.ok(2).flat_map(lambda value: Result.ok(value + 1)).value == 3
    assert Result.err("failed").flat_map(lambda value: Result.ok(value + 1)).error == "failed"
