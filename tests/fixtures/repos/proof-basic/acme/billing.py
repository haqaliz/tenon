from acme.client import StripeClient

client = StripeClient()


def create_charge(amount):
    return client.charges.create(amount=amount, currency="usd")
