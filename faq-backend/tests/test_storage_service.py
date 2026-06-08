from app.core.config import settings
from app.services.storage import StorageService


def test_normalize_avatar_reference_extracts_object_key_from_cloud_file_id():
    value = "cloud://test-8gwkg5zb84a8b224.7465-test-8gwkg5zb84a8b224-1407839340/avatars/u1/avatar.jpg"

    assert StorageService.normalize_avatar_reference(value) == "avatars/u1/avatar.jpg"


def test_normalize_avatar_reference_handles_malformed_embedded_cloud_url():
    value = (
        "http://faq-backend-test-8gwkg5zb84a8b224-1407839340.ap-shanghai.run.wxcloudrun.com/"
        "cloud://test-8gwkg5zb84a8b224.7465-test-8gwkg5zb84a8b224-1407839340/avatars/u1/avatar.jpg"
    )

    assert StorageService.normalize_avatar_reference(value) == "avatars/u1/avatar.jpg"


def test_build_avatar_access_url_upgrades_public_http_proxy_to_https():
    value = "cloud://test-8gwkg5zb84a8b224.7465-test-8gwkg5zb84a8b224-1407839340/avatars/u1/avatar.jpg"
    base_url = "http://faq-backend-test-8gwkg5zb84a8b224-1407839340.ap-shanghai.run.wxcloudrun.com"

    assert (
        StorageService.build_avatar_access_url(value, base_url)
        == "https://faq-backend-test-8gwkg5zb84a8b224-1407839340.ap-shanghai.run.wxcloudrun.com"
        "/api/upload/avatar/view?key=avatars%2Fu1%2Favatar.jpg"
    )


def test_build_avatar_access_url_keeps_localhost_http():
    value = "/static/avatars/avatar.jpg"
    base_url = "http://127.0.0.1:8000"

    assert StorageService.build_avatar_access_url(value, base_url) == "http://127.0.0.1:8000/static/avatars/avatar.jpg"


def test_extract_cos_object_key_from_cos_public_url():
    url = f"https://{settings.COS_BUCKET}.cos.{settings.COS_REGION}.myqcloud.com/avatars/u1/avatar.jpg?sign=123"

    assert StorageService.extract_cos_object_key(url) == "avatars/u1/avatar.jpg"
