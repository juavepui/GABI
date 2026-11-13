from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from gabi.application.portfolio.investment_cards import InvestmentCards
from gabi_api.schemas.investment_cards import CardCreate, CardMove, CardSave, InvestmentCard, InvestmentCardList

router = APIRouter(prefix="/api/v1/portfolio/cards", tags=["portfolio"])


def service(request: Request) -> InvestmentCards:
    return request.app.state.investment_cards


Cards = Annotated[InvestmentCards, Depends(service)]


@router.get("", response_model=InvestmentCardList)
def list_cards(cards: Cards, symbol: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
               limit: Annotated[int, Query(ge=1, le=200)] = 50) -> InvestmentCardList:
    """Versions of the investment cards, newest first per company; reads only the stored cards."""
    return InvestmentCardList(items=[InvestmentCard.model_validate(row) for row in cards.list(symbol, limit)])


@router.get("/{card_id}", response_model=InvestmentCard)
def get_card(card_id: Annotated[int, Path(ge=1)], cards: Cards) -> InvestmentCard:
    return InvestmentCard.model_validate(cards.get(card_id))


@router.post("", response_model=InvestmentCard, status_code=201)
def create_card(body: CardCreate, cards: Cards) -> InvestmentCard:
    """A new version of the company's card, «incompleta» until it is analysed and published."""
    return InvestmentCard.model_validate(cards.create(body.symbol, body.content.model_dump(mode="json")))


@router.post("/{card_id}/save", response_model=InvestmentCard)
def save_card(card_id: Annotated[int, Path(ge=1)], body: CardSave, cards: Cards) -> InvestmentCard:
    return InvestmentCard.model_validate(cards.save(card_id, body.content.model_dump(mode="json")))


@router.post("/{card_id}/state", response_model=InvestmentCard)
def move_card(card_id: Annotated[int, Path(ge=1)], body: CardMove, cards: Cards) -> InvestmentCard:
    """Analyse, publish (captures the inputs from the local cache) or discard with a reason."""
    return InvestmentCard.model_validate(cards.move(card_id, body.target, body.reason))
