"""API v1 router registry."""

from fastapi import APIRouter

from app.api.v1 import admin, auth, bidding, certificates, chat, daily, distributor_data, energy, guides, knowledge, leaderboard, lottery, monthly_leaderboard, questions, rewards, upload, users

router = APIRouter()

router.include_router(auth.router)
router.include_router(admin.router)
router.include_router(questions.router)
router.include_router(daily.router)
router.include_router(users.router)
router.include_router(energy.router)
router.include_router(leaderboard.router)
router.include_router(monthly_leaderboard.router)
router.include_router(lottery.router)
router.include_router(rewards.router)
router.include_router(chat.router)
router.include_router(guides.router)
router.include_router(knowledge.router)
router.include_router(certificates.router)
router.include_router(distributor_data.router)
router.include_router(upload.router)
router.include_router(bidding.router)
