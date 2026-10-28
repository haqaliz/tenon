from stripe import Stripe

client = Stripe()

client.customers.get(cid)
client.customers.retrieve(cid)
