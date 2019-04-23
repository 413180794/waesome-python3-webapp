import asyncio

import orm

from models import User,Blog,Comment

async def test():
    await orm.create_pool(loop=loop,user="root",password="012030",database="awesome")
    u = User(name="Test",email="test@example.com",passwd="123412412",image="about:blank")
    await u.save()

loop = asyncio.get_event_loop()
loop.run_until_complete(test())
loop.run_forever()