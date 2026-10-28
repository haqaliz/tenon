from stripe import Stripe

c = Stripe()
c.charges.delete("ch_1")
