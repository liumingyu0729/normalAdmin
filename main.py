# -*- coding: utf-8 -*-

import uvicorn

from settings import settings
from handlers.app import app


if __name__ == '__main__':
        uvicorn.run(app=app, host=settings.web.host, port=settings.web.port)

