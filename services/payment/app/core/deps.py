"""Request dependencies: services kept on the application state."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.providers.click import ClickShop
from app.providers.payme import PaymeMerchant
from app.services.orders import OrderClient


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    sessions: async_sessionmaker[AsyncSession] = request.app.state.sessions
    return sessions


def get_orders(request: Request) -> OrderClient:
    orders: OrderClient = request.app.state.orders
    return orders


def get_payme(request: Request) -> PaymeMerchant:
    payme: PaymeMerchant = request.app.state.payme
    return payme


def get_click(request: Request) -> ClickShop:
    click: ClickShop = request.app.state.click
    return click


SettingsDep = Annotated[Settings, Depends(get_settings)]
Sessions = Annotated[async_sessionmaker[AsyncSession], Depends(get_sessions)]
Orders = Annotated[OrderClient, Depends(get_orders)]
Payme = Annotated[PaymeMerchant, Depends(get_payme)]
Click = Annotated[ClickShop, Depends(get_click)]
