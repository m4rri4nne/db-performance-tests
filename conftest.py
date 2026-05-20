import pytest
from sqlalchemy import create_engine as _create_engine
from config import DB_URL


@pytest.fixture(scope="session")
def engine():
    return _create_engine(DB_URL)


@pytest.fixture
def instrumented_engine():
    from analysis.n_plus_one_detector import attach_logger, reset_log

    eng = _create_engine(DB_URL)
    attach_logger(eng)
    reset_log()
    return eng
