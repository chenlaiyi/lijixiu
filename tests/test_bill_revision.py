"""Run with python tests/test_bill_revision.py; uses isolated temporary databases."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///:memory:'
os.environ['PAYMENT_ALLOW_MOCK'] = 'true'

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from fastapi import HTTPException
from app import models
from app.models.base import Base
from app.models.user import User, UserRole
from app.models.region import Region
from app.models.repairer import Repairer
from app.models.order import Order, OrderStatus
from app.models.pay_order import PayOrder, PayStatus, PayProvider
from app.models.order_log import OrderLog
from app.models.service_bill import ServiceBill
from app.schemas.service_bill import ServiceBillCreate
from app.schemas.payment import PayCreateRequest
from app.services.service_bill import submit_bill, get_latest_bill, confirm_bill
from app.services.payment import create_payment, create_payment_intent, mark_payment_paid
from app.routers.order import submit_service_bill
from app.services.wechat_pay import WeChatPayError


class RevisionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_async_engine('sqlite+aiosqlite:///' + Path(self.tmp.name, 'test.db').as_posix())
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.db = self.factory()
        self.customer = User(phone='19900000001', name='customer', role=UserRole.CUSTOMER)
        self.tech = User(phone='19900000002', name='technician', role=UserRole.REPAIRER, business_role='repairer')
        self.region = Region(name='test', level=2)
        self.db.add_all([self.customer, self.tech, self.region])
        await self.db.flush()
        self.repairer = Repairer(user_id=self.tech.id, skills='repair')
        self.db.add(self.repairer)
        await self.db.flush()
        self.order = Order(customer_id=self.customer.id, repairer_id=self.repairer.id,
                           assigned_repairer_id=self.repairer.id, region_id=self.region.id,
                           address='test', description='test', status=OrderStatus.SERVICING,
                           price=0, paid_amount=0, technician_wage_amount=12)
        self.db.add(self.order)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()
        self.tmp.cleanup()

    def data(self, amount, revision=None, **extra):
        return ServiceBillCreate(repairer_id=self.repairer.id, amount=amount,
            items_json=json.dumps([dict(name='repair', quantity=1, unit_price=amount)]),
            expected_revision=revision, **extra)

    async def initial(self):
        return await submit_bill(self.db, self.order, self.data(80))

    async def test_revision_preserves_history_and_wages(self):
        old = await self.initial()
        new = await submit_bill(self.db, self.order, self.data(4, old.revision))
        self.assertEqual((new.revision, self.order.price, self.order.status), (2, 4, OrderStatus.WAIT_PAYMENT))
        self.assertEqual(old.amount, 80)
        self.assertEqual(self.order.technician_wage_amount, 12)
        self.assertIsNone(self.order.store_reviewed_at)
        self.assertEqual((await get_latest_bill(self.db, self.order.id)).id, new.id)
        log = (await self.db.execute(select(OrderLog).order_by(OrderLog.id.desc()))).scalars().first()
        self.assertIn('80.00 -> 4.00', log.remark)
        payment = await create_payment(self.db, PayCreateRequest(order_id=self.order.id,
            user_id=self.customer.id, amount=4, provider='mock'))
        self.assertEqual(payment.amount, 4)

    async def test_paid_or_partially_paid_cannot_edit(self):
        await self.initial()
        self.order.paid_amount = 1
        await self.db.commit()
        with self.assertRaisesRegex(ValueError, '付款'):
            await submit_bill(self.db, self.order, self.data(4, 1))

    async def test_stale_revision_rejected(self):
        await self.initial()
        await submit_bill(self.db, self.order, self.data(4, 1))
        with self.assertRaisesRegex(ValueError, '已更新'):
            await submit_bill(self.db, self.order, self.data(3, 1))
        self.assertEqual(self.order.price, 4)

    async def test_draft_does_not_change_payable_price(self):
        await submit_bill(self.db, self.order, self.data(80, save_as_draft=True))
        self.assertEqual(self.order.price, 0)
        self.assertEqual(self.order.status, OrderStatus.SERVICING)

    async def test_old_mock_payment_invalidated(self):
        await self.initial()
        p = await create_payment(self.db, PayCreateRequest(order_id=self.order.id,
            user_id=self.customer.id, amount=80, provider='mock'))
        await submit_bill(self.db, self.order, self.data(4, 1))
        await self.db.refresh(p)
        self.assertEqual(p.status, PayStatus.FAILED)
        with self.assertRaises(ValueError):
            await create_payment_intent(self.db, p, PayCreateRequest(order_id=self.order.id,
                user_id=self.customer.id, amount=80, provider='mock'))
        with self.assertRaises(ValueError):
            await mark_payment_paid(self.db, p, 'old', 'stale callback')

    async def test_wechat_closed_before_new_price(self):
        await self.initial()
        p = PayOrder(order_id=self.order.id, user_id=self.customer.id, amount=80,
            status=PayStatus.PENDING, provider=PayProvider.WECHAT, prepay_id='old-prepay', out_trade_no='old-trade')
        self.db.add(p)
        await self.db.commit()
        with patch('app.services.wechat_pay.query_transaction', return_value={'trade_state':'NOTPAY'}), \
             patch('app.services.wechat_pay.close_transaction') as close:
            await submit_bill(self.db, self.order, self.data(4, 1))
            close.assert_called_once_with('old-trade')
        self.assertEqual(self.order.price, 4)

    async def test_wechat_success_blocks_revision(self):
        await self.initial()
        self.db.add(PayOrder(order_id=self.order.id, user_id=self.customer.id, amount=80,
            status=PayStatus.PENDING, provider=PayProvider.WECHAT, prepay_id='old', out_trade_no='trade'))
        await self.db.commit()
        with patch('app.services.wechat_pay.query_transaction', return_value={'trade_state':'SUCCESS'}):
            with self.assertRaisesRegex(ValueError, '支付已成功'):
                await submit_bill(self.db, self.order, self.data(4, 1))
        self.assertEqual(self.order.price, 80)
        self.assertEqual((await get_latest_bill(self.db, self.order.id)).revision, 1)

    async def test_customer_cannot_submit_as_technician(self):
        await self.initial()
        with self.assertRaises(HTTPException) as error:
            await submit_service_bill(self.order.id, self.data(4, 1), self.db, self.customer)
        self.assertEqual(error.exception.status_code, 403)

    async def test_old_confirmation_cannot_restore_old_price(self):
        old = await self.initial()
        await submit_bill(self.db, self.order, self.data(4, 1))
        with self.assertRaisesRegex(ValueError, '已更新'):
            await confirm_bill(self.db, self.order, old)
        self.assertEqual(self.order.price, 4)

    async def test_stale_order_in_another_session_cannot_pay_old_price(self):
        await self.initial()
        async with self.factory() as other:
            await other.get(Order, self.order.id)
            await submit_bill(self.db, self.order, self.data(4, 1))
            with self.assertRaisesRegex(ValueError, 'Payment exceeds'):
                await create_payment(other, PayCreateRequest(order_id=self.order.id,
                    user_id=self.customer.id, amount=80, provider='mock'))

    async def test_close_failure_preserves_original_bill(self):
        await self.initial()
        self.db.add(PayOrder(order_id=self.order.id, user_id=self.customer.id, amount=80,
            status=PayStatus.PENDING, provider=PayProvider.WECHAT, prepay_id='old', out_trade_no='trade'))
        await self.db.commit()
        with patch('app.services.wechat_pay.query_transaction', return_value={'trade_state':'NOTPAY'}), \
             patch('app.services.wechat_pay.close_transaction', side_effect=WeChatPayError('unavailable')):
            with self.assertRaisesRegex(ValueError, '旧支付单未能关闭'):
                await submit_bill(self.db, self.order, self.data(4, 1))
        self.assertEqual(self.order.price, 80)
        self.assertEqual((await get_latest_bill(self.db, self.order.id)).revision, 1)

    async def test_revised_payment_still_waits_for_store_wage_review(self):
        await self.initial()
        await submit_bill(self.db, self.order, self.data(4, 1))
        p = await create_payment(self.db, PayCreateRequest(order_id=self.order.id,
            user_id=self.customer.id, amount=4, provider='mock'))
        with patch('app.services.profit.calculate_and_save', new=AsyncMock(return_value=[])):
            await mark_payment_paid(self.db, p, 'new-payment', 'test')
        self.assertEqual(self.order.paid_amount, 4)
        self.assertEqual(self.order.status, OrderStatus.PAID_PENDING_REVIEW)
        self.assertIsNone(self.order.store_reviewed_at)
        with self.assertRaises(ValueError):
            await submit_bill(self.db, self.order, self.data(3, 2))


if __name__ == '__main__':
    unittest.main()
