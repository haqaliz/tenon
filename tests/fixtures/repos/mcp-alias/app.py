from mcp.client.session import ClientSession


async def run(read, write):
    session = ClientSession(read, write)
    await session.call_tool("create_charge", {"amount": 100})
    await session.call_tool(name="create_charge", arguments={"amount": 100})
    other = session
    await other.call_tool("create_charge", {"amount": 100})
