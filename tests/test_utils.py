# tests/test_utils.py


def validate_422_error_structure(response, expected_loc: tuple):
    """
    Helper function to validate FastAPI 422 Validation Error structure.
    Checks if the response contains proper validation error details
    pointing to the expected location.

    Args:
        response: The response object from TestClient
        expected_loc: Tuple representing the expected error location (e.g. ("query", "param_name"))
    """
    error_body = response.json()
    assert "detail" in error_body, "Error response missing 'detail' field"

    detail = error_body["detail"]
    assert isinstance(detail, list), "'detail' should be a list"
    assert len(detail) > 0, "'detail' list is empty"

    # Validate structure of ALL error items
    for i, e in enumerate(detail):
        assert isinstance(e, dict), f"Error item {i} should be a dict"
        assert "loc" in e, f"Error item {i} missing 'loc' field"
        # Validate that 'loc' itself is a list (JSON spec) or tuple
        assert isinstance(
            e["loc"], (list, tuple)
        ), f"Error item {i} 'loc' should be a list or tuple"

    # Verify exact location match
    error_locs = [tuple(e["loc"]) for e in detail]
    assert (
        expected_loc in error_locs
    ), f"Expected error at {expected_loc}, found locations: {error_locs}"
