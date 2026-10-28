from stripe import Stripe

client = Stripe()


def record(amount):
    return amount


record(amount=1)
client.charges.create(amount=1)
