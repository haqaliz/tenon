from stripe import Stripe

client = Stripe()

client.charges.create(amount=amount, currency="usd")
client.charges.delete(charge_id)
