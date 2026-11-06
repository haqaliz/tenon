from mcp import ClientSession


async def create_charge(read, write):
    async with ClientSession(read, write) as session:
        return await session.call_tool(
            "create_charge", arguments={"amount": 100}
        )
