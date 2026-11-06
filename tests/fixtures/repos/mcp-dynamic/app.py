from mcp import ClientSession


async def run(read, write, name, payload):
    async with ClientSession(read, write) as session:
        await session.call_tool(name, {"amount": 1})
        await session.call_tool("create_charge", payload)
        await session.call_tool("create_charge", dict(amount=1))
        await session.call_tool("create_charge", **payload)
        await session.call_tool(
            "create_charge",
            arguments={"amount": {"nested": 1}, "currency": "usd"},
        )
        await session.call_tool("create_charge", arguments={**payload})
