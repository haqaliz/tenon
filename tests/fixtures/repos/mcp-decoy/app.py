from mcp import ClientSession


class Wrapper:
    def call_tool(self, name, arguments=None):
        return name


async def run(wrapper, read, write):
    await wrapper.call_tool("create_charge", {"amount": 1})
    async with ClientSession(read, write) as session:
        await session.call_tool("create_charge", {"amount": 2})
