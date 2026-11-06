"""Access dependencies shared by the RFQ and offer routers (no Operator: B3-D11)."""

from datetime import datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine

from nautical_deliverance.api.inquiries import _allow, get_now
from nautical_deliverance.api.users import get_users_engine
from nautical_deliverance.domain.identity import Principal, Role

Reader = Annotated[Principal, Depends(_allow(Role.ADMIN, Role.BUNKER_BUYER, Role.VIEWER))]
Writer = Annotated[Principal, Depends(_allow(Role.ADMIN, Role.BUNKER_BUYER))]
Eng = Annotated[Engine, Depends(get_users_engine)]
Now = Annotated[datetime, Depends(get_now)]
