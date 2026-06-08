import pytest

from app.models.user import User


@pytest.mark.asyncio
async def test_password_login_returns_token_for_matching_account(client, test_db):
    async with test_db() as session:
        user = User(
            openid="review_openid_001",
            nickname="ReviewUser",
            phone="13900000001",
            real_name="审核员",
            province="上海",
            company="审核公司",
            profile_verified=True,
            login_username="reviewer",
            login_password="pass1234",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    response = await client.post(
        "/api/auth/login_password",
        json={"username": "reviewer", "password": "pass1234"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["token"]
    assert payload["data"]["user"]["id"] == user_id
    assert payload["data"]["user"]["nickname"] == "ReviewUser"
    assert payload["data"]["user"]["profile_verified"] is True


@pytest.mark.asyncio
async def test_password_login_rejects_wrong_password(client, test_db):
    async with test_db() as session:
        user = User(
            openid="review_openid_002",
            nickname="ReviewUser",
            phone="13900000002",
            profile_verified=True,
            login_username="reviewer2",
            login_password="pass1234",
        )
        session.add(user)
        await session.commit()

    response = await client.post(
        "/api/auth/login_password",
        json={"username": "reviewer2", "password": "wrong"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 1005
    assert not payload.get("data")


@pytest.mark.asyncio
async def test_password_login_accepts_non_ascii_password(client, test_db):
    async with test_db() as session:
        user = User(
            openid="review_openid_003",
            nickname="ReviewUser",
            phone="13900000003",
            profile_verified=True,
            login_username="reviewer3",
            login_password="审核Pass123",
        )
        session.add(user)
        await session.commit()

    response = await client.post(
        "/api/auth/login_password",
        json={"username": "reviewer3", "password": "审核Pass123"},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 0
