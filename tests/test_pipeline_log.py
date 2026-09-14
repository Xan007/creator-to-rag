from src.pipeline._common import post_step


def test_post_step_includes_id_and_stage():
    assert post_step(1, 3, "DYkvZXHN_zv", "uploading video") == (
        "  [1/3 DYkvZXHN_zv] uploading video"
    )
