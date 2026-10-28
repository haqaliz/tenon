from stripe import Stripe

client = Stripe()
note = "café"; client.charges.delete("ch_1")
