"""Guest coverage is public; private address operations remain authenticated."""
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///:memory:'
import httpx
from fastapi import FastAPI
from app.core.database import get_db
from app.routers.service_area import router


async def main():
    app = FastAPI()
    app.include_router(router)
    async def fake_db():
        yield object()
    app.dependency_overrides[get_db] = fake_db
    fixture = {'id': 1, 'service_area_id': 1, 'name': '未来海岸社区',
               'city': '厦门市', 'district': '海沧区', 'street': '嵩屿街道',
               'estates': ['未来海岸-蓝月湾一期'], 'store_id': 3,
               'store_name': 'internal', 'operator_user_id': 99, 'door_number': 'private'}
    with patch('app.routers.service_area.service.customer_options', new=AsyncMock(return_value=[fixture])) as loader:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/api/v1/service-areas/public-options')
            assert response.status_code == 200
            public = response.json()[0]
            assert set(public) == {'id', 'service_area_id', 'name', 'city', 'district', 'street', 'estates'}
            loader.assert_awaited_once_with(next(iter(loader.await_args.args)), include_order_estates=False)
            for path in ['/api/v1/service-areas/customer-options', '/api/v1/service-areas']:
                assert (await client.get(path)).status_code == 401
            assert (await client.post('/api/v1/service-areas/assignments/bulk', json={})).status_code == 401
    print('PASS: guest coverage excludes private fields and order-derived estates; internal reads and writes still require authentication')


if __name__ == '__main__':
    asyncio.run(main())
