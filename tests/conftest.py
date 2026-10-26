from energy.train import MODEL_PATH, main as train


def pytest_configure(config):
    """Train once before tests are collected, because the API module loads the model on import.
    Downloads the real dataset on first run."""
    if not MODEL_PATH.exists():
        train()
