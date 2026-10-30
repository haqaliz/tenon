import stripe


def create():
    return stripe.checkout.Session.create(payment_method_types=["card"])
