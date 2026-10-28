import pytest

# Rewrite asserts inside the matcher so scenario failures show a pytest diff.
pytest.register_assert_rewrite("acceptance.semantic")
