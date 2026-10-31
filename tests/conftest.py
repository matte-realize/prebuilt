import pytest

# tests/test_posterior.py runs once per posterior implementation. The NumPy
# class is the reference; the Warp class must pass the same tests unchanged.
POSTERIOR_IMPLS = ["numpy", "warp"]


def warp_gpu_available() -> bool:
    try:
        import warp as wp
    except ImportError:
        return False
    return wp.get_cuda_device_count() > 0


def pytest_generate_tests(metafunc):
    if metafunc.module.__name__.rsplit(".", 1)[-1] == "test_posterior":
        metafunc.fixturenames.append("posterior_impl")
        metafunc.parametrize("posterior_impl", POSTERIOR_IMPLS)


@pytest.fixture(autouse=True)
def _swap_posterior_impl(request, monkeypatch):
    callspec = getattr(request.node, "callspec", None)
    if callspec is None or callspec.params.get("posterior_impl") != "warp":
        return
    if not warp_gpu_available():
        pytest.skip("no Warp or CUDA GPU")
    from model import posterior_warp
    monkeypatch.setattr(request.module, "ParticlePosterior", posterior_warp.ParticlePosterior)
