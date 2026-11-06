from mcp import ClientSession


async def run(read, write, amount):
    async with ClientSession(read, write) as session:
        await session.call_tool("create_charge", arguments={"amount": amount, "currency": "usd"})


def run_sync(read, write):
    with ClientSession(read, write) as session:
        session.call_tool("other_tool", {"amount": 1})
