import stripe

client = stripe.Stripe()


def create(**row):
    return client.charges.create(**row)


def delete(*args):
    return getattr(client.charges, "delete")(*args)


c = client
c.charges.delete("ch_1")

client.charges.create({"amount": 1, "currency": "usd"})

resp.amount
