class Caller:
    def call_tool(self, name):
        return name


def run(caller):
    return caller.call_tool("create_charge", {"amount": 1})
