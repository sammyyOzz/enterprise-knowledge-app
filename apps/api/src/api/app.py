from fastapi import FastAPI, Request
import time
from contextlib import asynccontextmanager

from api.routers.documents import router as documents_router
from api.routers.versions import router as versions_router
from api.utils.storage import ensure_bucket

import logging


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    for attempt in range(15):
        try:
            ensure_bucket()
            break
        except Exception:
            if attempt == 14:
                raise
            time.sleep(2)
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(documents_router)
app.include_router(versions_router)