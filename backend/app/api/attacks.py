from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Attack

router = APIRouter(prefix="/api/attacks", tags=["attacks"])


class AttackResponse(BaseModel):
    id: int
    name: str
    category: str
    prompt: str
    description: Optional[str] = None
    severity: str

    model_config = {"from_attributes": True}


class AttacksByCategory(BaseModel):
    categories: Dict[str, List[AttackResponse]]
    total: int


@router.get("", response_model=AttacksByCategory)
async def list_attacks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Attack).order_by(Attack.category, Attack.name)
    )
    attacks = result.scalars().all()

    categories: Dict[str, List[AttackResponse]] = {}
    for attack in attacks:
        resp = AttackResponse.model_validate(attack)
        categories.setdefault(attack.category, []).append(resp)

    return AttacksByCategory(categories=categories, total=len(attacks))


@router.get("/{attack_id}", response_model=AttackResponse)
async def get_attack(attack_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Attack).where(Attack.id == attack_id))
    attack = result.scalar_one_or_none()
    if attack is None:
        raise HTTPException(status_code=404, detail=f"Attack {attack_id} not found")
    return AttackResponse.model_validate(attack)
