import pytest
from cleanshift.providers.mock import MockProvider


@pytest.fixture
def mock_provider() -> MockProvider:
    return MockProvider()


@pytest.fixture
def low_intensity_provider() -> MockProvider:
    """Provider whose intensity is always well below any reasonable threshold."""
    return MockProvider(base_intensity=50.0, amplitude=10.0)


@pytest.fixture
def high_intensity_provider() -> MockProvider:
    """Provider whose intensity is always above typical thresholds."""
    return MockProvider(base_intensity=500.0, amplitude=10.0)
