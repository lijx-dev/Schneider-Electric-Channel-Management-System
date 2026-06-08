from urllib.parse import quote

import pytest


@pytest.mark.asyncio
async def test_update_profile_returns_avatar_fields(client, test_user):
    user, token = test_user
    avatar = (
        "cloud://test-8gwkg5zb84a8b224.7465-test-8gwkg5zb84a8b224-1407839340/"
        f"avatars/{user.id}/avatar.jpg"
    )

    response = await client.post(
        "/api/user/profile",
        json={
            "user_id": user.id,
            "nickname": "UpdatedName",
            "avatar": avatar,
            "real_name": "Test Real Name",
            "province": "上海",
            "company": "Test Company",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["nickname"] == "UpdatedName"
    assert payload["data"]["real_name"] == "Test Real Name"
    assert payload["data"]["province"] == "上海"
    assert payload["data"]["company"] == "Test Company"
    assert payload["data"]["profile_verified"] is True
    assert payload["data"]["avatar_file_id"] == f"avatars/{user.id}/avatar.jpg"
    assert payload["data"]["avatar_url"] == (
        "https://test/api/upload/avatar/view?key="
        f"{quote(f'avatars/{user.id}/avatar.jpg', safe='')}"
    )


@pytest.mark.asyncio
async def test_update_profile_rejects_mismatched_whitelist_info(client, test_user):
    user, token = test_user

    response = await client.post(
        "/api/user/profile",
        json={
            "user_id": user.id,
            "nickname": "UpdatedName",
            "avatar": "",
            "real_name": "Wrong Name",
            "province": "上海",
            "company": "Test Company",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 1003
    assert "不一致" in payload["detail"]
